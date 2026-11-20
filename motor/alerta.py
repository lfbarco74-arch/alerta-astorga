"""Rodada do sistema: coleta, avalia, publica status.json e avisa no Telegram.

Uso:  python -m motor.alerta            (rodada normal)
      python -m motor.alerta --sem-telegram
"""
from __future__ import annotations

import csv
import json
import sys
import traceback
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from . import fontes, indice, telegram

RAIZ = Path(__file__).resolve().parent.parent
CFG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
ARQ_ESTADO = RAIZ / "data" / "estado.json"
ARQ_ENS = RAIZ / "data" / "ensemble_cache.json"
ARQ_HIST = RAIZ / "data" / "historico.csv"
ARQ_STATUS = RAIZ / "docs" / "data" / "status.json"
LIM = CFG["limiares"]


def _ler(p: Path, padrao):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return padrao


def _gravar(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _vigente(aviso: dict, agora: datetime) -> bool:
    """O feed do INMET mantém avisos vencidos por dias; só interessam os que ainda não acabaram."""
    try:
        return datetime.fromisoformat(aviso["fim"]) >= agora
    except (KeyError, ValueError):
        return False


def pontos_a_montante(anel_pts, direcao_vento, abertura):
    if direcao_vento is None:
        return [p["id"] for p in anel_pts]  # sem direção: usa o anel todo
    return [p["id"] for p in anel_pts if indice.angulo_entre(p["rumo"], direcao_vento) <= abertura]


def direcao_janela(series_sede: dict, ini: int, fim: int):
    dirs = []
    for s in series_sede.values():
        dirs += [s.valor("d700", i) for i in range(ini, fim)]
    return indice.direcao_media(dirs)


def carregar_ensemble(agora_utc: datetime, sede: dict, horas_det: list[str]):
    """Busca o ensemble a cada N horas; no intervalo, reaproveita o cache."""
    cache = _ler(ARQ_ENS, {})
    idade_h = 999
    if cache.get("obtido_em"):
        idade_h = (agora_utc - datetime.fromisoformat(cache["obtido_em"])).total_seconds() / 3600
    if idade_h >= CFG["ensemble_a_cada_horas"] - 0.25:
        try:
            horas, membros = fontes.ensemble(sede, CFG["ensemble_modelo"], CFG["fuso"])
            cache = {"obtido_em": agora_utc.isoformat(), "horas": horas,
                     "membros": [{k: getattr(m, k) for k in ("cape", "v10", "d10", "v500", "d500")} for m in membros]}
            _gravar(ARQ_ENS, cache)
        except Exception as e:  # noqa: BLE001
            print(f"[ensemble] falhou, usando cache: {e}")
    if not cache.get("membros"):
        return None
    # realinha as horas do cache com as horas atuais
    desloc = cache["horas"].index(horas_det[0]) if horas_det[0] in cache["horas"] else None
    if desloc is None:
        return None
    membros = []
    for m in cache["membros"]:
        membros.append(indice.SerieModelo(cape=m["cape"][desloc:], v10=m["v10"][desloc:], d10=m["d10"][desloc:],
                                          v500=m["v500"][desloc:], d500=m["d500"][desloc:], precip=[], wcode=[]))
    return membros


def serie_horaria(local, horas, i0, n, regional_ids, det):
    """Para o gráfico: mediana entre modelos do WMAXSHEAR (pior localidade) e se há gatilho."""
    saida = []
    modelos = sorted({m for por in local.values() for m in por})
    for k in range(i0, min(i0 + n, len(horas))):
        ws_mod, gat = [], False
        for m in modelos:
            melhor = 0
            for por in local.values():
                s = por.get(m)
                if not s:
                    continue
                sh = indice.cisalhamento_ms(s.valor("v500", k), s.valor("d500", k), s.valor("v10", k), s.valor("d10", k))
                ws = indice.wmaxshear(s.valor("cape", k), sh)
                if ws is not None and (s.valor("cape", k) or 0) >= LIM["cape_minimo"]:
                    melhor = max(melhor, ws)
                gat = gat or indice.gatilho_na_janela(s, k, k + 1, LIM)
            ws_mod.append(melhor)
        for pid in regional_ids:
            for s in det.get(pid, {}).values():
                gat = gat or indice.gatilho_na_janela(s, k, k + 1, LIM)
        saida.append({"hora": horas[k], "wmaxshear": round(median(ws_mod)) if ws_mod else None, "gatilho": gat})
    return saida


DIR_ARQUIVO = RAIZ / "data" / "arquivo"
DIR_RELATOS = RAIZ / "data" / "relatos"
URL_RELATOS = CFG["pagina_url"].rstrip("/") + "/api/relatos?horas=6"


ARQ_ANTERIOR = RAIZ / "data" / "status_anterior.json"


def manter_anterior(status: dict, agora: datetime, max_horas: float = 12) -> dict:
    """Se os modelos não responderam nesta rodada, mantém os níveis da última rodada boa (até 12 h),
    com os avisos do INMET e os erros desta rodada. Nunca troca dados bons por 'Sem dados'."""
    ant = _ler(ARQ_ANTERIOR, {})
    base = ant.get("modelos_de") or ant.get("gerado_em")
    if not ant.get("janelas") or not base:
        return status
    try:
        idade = (agora - datetime.fromisoformat(base)).total_seconds() / 3600
    except ValueError:
        return status
    if idade > max_horas:
        return status
    novo = dict(ant)
    novo.update(gerado_em=status["gerado_em"], modelos_de=base, erros=status["erros"],
                avisos_inmet=status["avisos_inmet"], avisos_estado=status.get("avisos_estado", []))
    print(f"[status] modelos indisponíveis: mantendo os níveis da rodada de {base}")
    return novo


def arquivar(status: dict, agora: datetime) -> None:
    """Uma linha por rodada em data/arquivo/AAAA-MM-DD.jsonl: o que o sistema previu, com os ingredientes.
    É a base para medir acertos e recalibrar os limiares mais adiante."""
    reg = {
        "gerado_em": status["gerado_em"],
        "direcao": status.get("direcao_graus"),
        "janelas": [{
            "rotulo": j["rotulo"], "inicio": j["inicio"], "fim": j["fim"], "nivel": j["nivel"],
            "nivel_modelos": j["nivel_modelos"], "pico": j.get("hora_pico_iso"), "ingredientes": j["ingredientes"],
            "perigos": j.get("perigos_nivel", {}), "prob_ensemble": j.get("prob_ensemble"),
            "inmet": (j.get("inmet") or {}).get("severidade"),
            "modelos": {m: [v["nivel"], v["wmaxshear"], int(v["gatilho_local"]), int(v["gatilho_regional"])]
                        for m, v in j["por_modelo"].items()},
        } for j in status["janelas"]],
        "serie": [[p["hora"], p["wmaxshear"], int(p["gatilho"])] for p in status["serie_horaria"]],
        "avisos_inmet": [[a["id"], a["severidade"]] for a in status["avisos_inmet"]],
        "erros": status["erros"],
    }
    DIR_ARQUIVO.mkdir(parents=True, exist_ok=True)
    with (DIR_ARQUIVO / f"{agora:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False, separators=(",", ":")) + "\n")


def coletar_relatos(agora: datetime) -> int:
    """Copia os relatos de campo das últimas horas (enviados pela página) para data/relatos/AAAA-MM.jsonl."""
    req = urllib.request.Request(URL_RELATOS, headers={"User-Agent": "alerta-tempo-astorga/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        relatos = json.loads(r.read()).get("relatos", [])
    DIR_RELATOS.mkdir(parents=True, exist_ok=True)
    arq = DIR_RELATOS / f"{agora:%Y-%m}.jsonl"
    vistos = set()
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                vistos.add(json.loads(linha)["id"])
            except (ValueError, KeyError):
                pass
    novos = [x for x in relatos if x.get("id") and x["id"] not in vistos]
    with arq.open("a", encoding="utf-8") as f:
        for x in sorted(novos, key=lambda x: x["id"]):
            f.write(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(novos)


def rodar(enviar_telegram: bool = True) -> dict:
    fuso = ZoneInfo(CFG["fuso"])
    agora = datetime.now(fuso)
    agora_utc = datetime.now(ZoneInfo("UTC"))
    estado = _ler(ARQ_ESTADO, {})
    locs = CFG["localidades"]
    sede = locs[0]
    ac = CFG["anel_regional"]
    anel_pts = fontes.anel(sede["lat"], sede["lon"], ac["raio_km"], ac["pontos"])
    erros = []

    # 1) modelos determinísticos
    horas, det = [], {}
    try:
        horas, det, falhas = fontes.modelos_deterministicos(locs + anel_pts, CFG["modelos"], CFG["fuso"])
        erros += [f"modelo {f}" for f in falhas]
    except Exception as e:  # noqa: BLE001
        erros.append(f"modelos: {e}")

    # 2) avisos INMET
    avisos, avisos_estado = [], []
    try:
        estado.pop("cache_inmet", None)  # formato antigo
        cache_inmet = estado.setdefault("cache_inmet_v2", {})
        avisos, avisos_estado = fontes.avisos_inmet(CFG["ibge_municipio"], cache_inmet)
        avisos = sorted((a for a in avisos if _vigente(a, agora)), key=lambda a: a["inicio"])
        avisos_estado = [a for a in avisos_estado if _vigente(a, agora)]
    except Exception as e:  # noqa: BLE001
        erros.append(f"INMET: {e}")

    janelas, serie, direcao_24h, locs_status, anel_status = [], [], None, [], []
    if horas:
        hora_atual = agora.strftime("%Y-%m-%dT%H:00")
        i0 = horas.index(hora_atual) if hora_atual in horas else 0
        local = {l["id"]: det.get(l["id"], {}) for l in locs}
        membros = None
        try:
            membros = carregar_ensemble(agora_utc, sede, horas[i0:])
        except Exception as e:  # noqa: BLE001
            erros.append(f"ensemble: {e}")

        direcao_24h = direcao_janela(local[sede["id"]], i0, i0 + 24)
        for a, b, rotulo in CFG["janelas_horas"]:
            ini, fim = i0 + a, min(i0 + b, len(horas))
            if ini >= fim:
                continue
            dirj = direcao_janela(local[sede["id"]], ini, fim)
            reg_ids = pontos_a_montante(anel_pts, dirj, ac["abertura_graus"])
            regional = {pid: det.get(pid, {}) for pid in reg_ids}
            prob = indice.prob_ensemble_janela(membros, a, b, LIM) if membros else None
            t_ini = datetime.fromisoformat(horas[ini]).replace(tzinfo=fuso)
            t_fim = datetime.fromisoformat(horas[fim - 1]).replace(tzinfo=fuso) + timedelta(hours=1)
            aviso = fontes.aviso_na_janela(avisos, t_ini, t_fim)
            r = indice.avaliar_janela(local, regional, ini, fim, LIM, prob,
                                      {"severidade": aviso["severidade"], "id": aviso["id"]} if aviso else None)
            horas_pico = [v["hora_pico"] for v in r["por_modelo"].values() if v["hora_pico"] is not None]
            r.update(rotulo=rotulo, inicio=horas[ini], fim=horas[fim - 1],
                     hora_pico_local=horas[int(median(horas_pico))][11:16] if horas_pico else None,
                     hora_pico_iso=horas[int(median(horas_pico))] if horas_pico else None,
                     direcao_chegada=indice.rosa(dirj), pontos_regionais=reg_ids)
            janelas.append(r)

        serie = serie_horaria(local, horas, i0, 48,
                              pontos_a_montante(anel_pts, direcao_24h, ac["abertura_graus"]), det)

        # status por localidade (próximas 24 h), para separar urbano e rural
        ids24 = pontos_a_montante(anel_pts, direcao_24h, ac["abertura_graus"])
        reg24 = {pid: det.get(pid, {}) for pid in ids24}
        fim24 = min(i0 + 24, len(horas))
        for p in anel_pts:  # para o mapa
            anel_status.append({**p, "a_montante": p["id"] in ids24,
                                "tempestade_simulada": any(indice.gatilho_na_janela(s, i0, fim24, LIM)
                                                           for s in det.get(p["id"], {}).values())})
        for l in locs:
            r = indice.avaliar_janela({l["id"]: local[l["id"]]}, reg24, i0, min(i0 + 24, len(horas)), LIM)
            locs_status.append({"id": l["id"], "nome": l["nome"], "perfil": l["perfil"],
                                "nivel_modelos": r["nivel_modelos"], "wmaxshear": r["ingredientes"]["wmaxshear"],
                                "perigos": r["perigos"]})

    j24 = [j for j in janelas if j["rotulo"] != CFG["janelas_horas"][-1][2]] or janelas
    # destaque: o maior nível; empatando, a janela mais próxima
    pior = next((j for j in j24 if j["nivel"] == max(x["nivel"] for x in j24)), None) if j24 else None
    status = {
        "versao": "0.1",
        "gerado_em": agora.isoformat(timespec="minutes"),
        "pagina_url": CFG["pagina_url"],
        "resumo": {
            "nivel_24h": pior["nivel"] if pior else 0,
            "nome_24h": pior["nome"] if pior else "Sem dados",
            "wmaxshear_24h": pior["ingredientes"]["wmaxshear"] if pior else None,
            "janela_pior": pior or {"rotulo": "—", "perigos": [], "motivos": []},
        },
        "janelas": janelas,
        "localidades": [{**s, "lat": l["lat"], "lon": l["lon"]} for s, l in zip(locs_status, locs)],
        "anel": anel_status,
        "serie_horaria": serie,
        "direcao_chegada": indice.rosa(direcao_24h) if direcao_24h is not None else None,
        "direcao_graus": round(direcao_24h) if direcao_24h is not None else None,
        "avisos_inmet": avisos,
        "avisos_estado": avisos_estado,
        "limiares": LIM,
        "modelos": CFG["modelos"],
        "ensemble_modelo": CFG["ensemble_modelo"],
        "anel_regional": {k: ac[k] for k in ("raio_km", "pontos", "abertura_graus")},
        "erros": erros,
        "fontes": ["Open-Meteo (CC-BY 4.0): ECMWF IFS, GFS, ICON, GEM e ensemble ECMWF",
                   "INMET — avisos meteorológicos (RSS/CAP)"],
    }
    if not horas:
        status = manter_anterior(status, agora)
    _gravar(ARQ_STATUS, status)
    try:
        if horas:
            arquivar(status, agora)
    except Exception as e:  # noqa: BLE001
        print(f"[arquivo] falhou: {e}")
    try:
        n = coletar_relatos(agora)
        print(f"[relatos] {n} novo(s)")
    except Exception as e:  # noqa: BLE001
        print(f"[relatos] falhou: {e}")

    novo = not ARQ_HIST.exists()
    with ARQ_HIST.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["gerado_em", "nivel_0_6h", "nivel_6_24h", "nivel_24_48h", "wmaxshear_24h",
                        "p_alerta_ens", "aviso_inmet", "erros"])
        nv = [str(j["nivel"]) for j in janelas] + [""] * (3 - len(janelas))
        p = (janelas[0].get("prob_ensemble") or {}).get("p_alerta") if janelas else None
        w.writerow([status["gerado_em"], *nv[:3], status["resumo"]["wmaxshear_24h"] or "",
                    f"{p:.2f}" if p is not None else "", "|".join(a["severidade"] for a in avisos), "; ".join(erros)])

    if horas and CFG["telegram"].get("ativo", True):  # sem modelos ou Telegram desligado: não mexe nos alertas
        msgs = telegram.decidir(status, estado, CFG["telegram"], agora.hour)
        for tipo, texto, silencioso in msgs:
            if enviar_telegram:
                try:
                    telegram.enviar(texto, silencioso)
                except Exception as e:  # noqa: BLE001
                    print(f"[telegram] erro ({tipo}): {e}")
            else:
                print(f"--- [{tipo}{' silencioso' if silencioso else ''}]\n{texto}")
    _gravar(ARQ_ESTADO, estado)
    print(f"Nível 24 h: {status['resumo']['nome_24h']} | janelas: "
          + ", ".join(f"{j['rotulo']}={j['nivel']}" for j in janelas) + (f" | erros: {erros}" if erros else ""))
    return status


if __name__ == "__main__":
    try:
        rodar(enviar_telegram="--sem-telegram" not in sys.argv)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
