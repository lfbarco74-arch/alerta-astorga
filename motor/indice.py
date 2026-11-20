"""Índice de risco convectivo para Astorga — lógica pura, sem rede.

Princípio: AMBIENTE LOCAL + GATILHO REGIONAL.
  * Ambiente: WMAXSHEAR = raiz(2*CAPE) x cisalhamento 0-6 km, calculado nas
    localidades de Astorga. Mede se uma tempestade, se existir, tem combustível
    e organização para ficar severa.
  * Gatilho: algum modelo produz convecção (trovoada ou chuva forte) nas
    localidades OU nos pontos regionais a montante do vento. Tempestades
    noturnas que chegam de oeste/noroeste (caso de 02/11/2026) quase nunca
    aparecem sobre o ponto exato no modelo, mas aparecem na região.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

NOMES_NIVEL = {0: "Normal", 1: "Atenção", 2: "Alerta", 3: "Severo"}
SEVERIDADE_INMET = {"Moderate": 1, "Severe": 2, "Extreme": 3}
ROTULO_INMET = {"Moderate": "Perigo Potencial (amarelo)", "Severe": "Perigo (laranja)",
                "Extreme": "Grande Perigo (vermelho)"}


def _vetor(vel_kmh: float, dir_graus: float) -> tuple[float, float]:
    r = math.radians(dir_graus)
    return vel_kmh * math.sin(r), vel_kmh * math.cos(r)


def cisalhamento_ms(v500, d500, v10, d10) -> float | None:
    """Diferença vetorial entre o vento em 500 hPa (~5,5 km) e em 10 m, em m/s."""
    if None in (v500, d500, v10, d10):
        return None
    a, b = _vetor(v500, d500), _vetor(v10, d10)
    return math.hypot(a[0] - b[0], a[1] - b[1]) / 3.6


def wmaxshear(cape, shear) -> float | None:
    if cape is None or shear is None:
        return None
    return math.sqrt(2 * max(cape, 0.0)) * shear


def direcao_media(direcoes: list[float]) -> float | None:
    """Média circular de direções (de onde o vento sopra)."""
    ds = [d for d in direcoes if d is not None]
    if not ds:
        return None
    x = sum(math.sin(math.radians(d)) for d in ds)
    y = sum(math.cos(math.radians(d)) for d in ds)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def rosa(graus: float | None) -> str:
    if graus is None:
        return "—"
    nomes = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
    return nomes[int(((graus + 22.5) % 360) // 45)]


def angulo_entre(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


@dataclass
class SerieModelo:
    """Série horária de um modelo numa localidade. Listas alinhadas por hora; None = ausente."""
    cape: list
    v10: list
    d10: list
    v500: list
    d500: list
    precip: list
    wcode: list
    rajada: list = field(default_factory=list)
    isoterma0: list = field(default_factory=list)
    d700: list = field(default_factory=list)

    def valor(self, nome, i):
        lst = getattr(self, nome)
        return lst[i] if i < len(lst) else None


def gatilho_na_janela(serie: SerieModelo, ini: int, fim: int, lim: dict) -> bool:
    for i in range(ini, fim):
        wc, pr = serie.valor("wcode", i), serie.valor("precip", i)
        if wc is not None and wc >= lim["gatilho_weather_code"]:
            return True
        if pr is not None and pr >= lim["gatilho_precip_mm_h"]:
            return True
    return False


def ambiente_na_janela(serie: SerieModelo, ini: int, fim: int, lim: dict) -> dict:
    """Pico de WMAXSHEAR e ingredientes associados numa janela de horas."""
    melhor = {"ws": 0.0, "cape": 0.0, "shear": 0.0, "hora": None}
    precip_max, raj_max, iso_min = 0.0, 0.0, None
    for i in range(ini, fim):
        cape = serie.valor("cape", i)
        sh = cisalhamento_ms(serie.valor("v500", i), serie.valor("d500", i),
                             serie.valor("v10", i), serie.valor("d10", i))
        ws = wmaxshear(cape, sh)
        if ws is not None and cape >= lim["cape_minimo"] and ws > melhor["ws"]:
            melhor = {"ws": ws, "cape": cape, "shear": sh, "hora": i}
        pr = serie.valor("precip", i)
        if pr is not None:
            precip_max = max(precip_max, pr)
        rj = serie.valor("rajada", i)
        if rj is not None:
            raj_max = max(raj_max, rj)
        iz = serie.valor("isoterma0", i)
        if iz is not None:
            iso_min = iz if iso_min is None else min(iso_min, iz)
    melhor.update(precip_max=precip_max, rajada_max=raj_max, isoterma0_min=iso_min)
    return melhor


def nivel_do_modelo(ws: float, gatilho: bool, lim: dict) -> int:
    if gatilho and ws >= lim["wmaxshear_severo"]:
        return 3
    if gatilho and ws >= lim["wmaxshear_alerta"]:
        return 2
    if (gatilho and ws >= lim["wmaxshear_atencao"]) or ws >= lim["wmaxshear_sem_gatilho"]:
        return 1
    return 0


def consenso(niveis: list[int]) -> int:
    """Nível alcançado por pelo menos 2 modelos (ou o único, se só houver um)."""
    if not niveis:
        return 0
    ordenado = sorted(niveis, reverse=True)
    return ordenado[1] if len(ordenado) >= 2 else ordenado[0]


def avaliar_janela(local: dict[str, dict[str, SerieModelo]],
                   regional: dict[str, dict[str, SerieModelo]],
                   ini: int, fim: int, lim: dict,
                   prob_ensemble: dict | None = None,
                   inmet: dict | None = None) -> dict:
    """
    local:    {localidade_id: {modelo: SerieModelo}}
    regional: {ponto_id: {modelo: SerieModelo}} — só os pontos a montante.
    prob_ensemble: {"p_alerta": 0..1, "p_severo": 0..1} ou None.
    inmet: {"severidade": "Moderate|Severe|Extreme", ...} ou None.
    """
    modelos = sorted({m for por_mod in local.values() for m in por_mod})
    por_modelo = {}
    for m in modelos:
        # ambiente: pior localidade de Astorga
        avaliacoes = []
        gat_local = False
        for loc_id, por_mod in local.items():
            s = por_mod.get(m)
            if s is None:
                continue
            a = ambiente_na_janela(s, ini, fim, lim)
            a["localidade"] = loc_id
            avaliacoes.append(a)
            gat_local = gat_local or gatilho_na_janela(s, ini, fim, lim)
        if not avaliacoes:
            continue
        amb = dict(max(avaliacoes, key=lambda a: a["ws"]))
        amb["precip_max"] = max(a["precip_max"] for a in avaliacoes)
        amb["rajada_max"] = max(a["rajada_max"] for a in avaliacoes)
        isos = [a["isoterma0_min"] for a in avaliacoes if a["isoterma0_min"] is not None]
        amb["isoterma0_min"] = min(isos) if isos else None
        gat_reg = any(gatilho_na_janela(por_mod[m], ini, fim, lim)
                      for por_mod in regional.values() if m in por_mod)
        gat = gat_local or gat_reg
        por_modelo[m] = {**amb, "gatilho_local": gat_local, "gatilho_regional": gat_reg,
                         "nivel": nivel_do_modelo(amb["ws"], gat, lim)}

    niveis = [v["nivel"] for v in por_modelo.values()]
    nivel_modelos = consenso(niveis)
    motivos = []
    if por_modelo:
        n_ok = sum(1 for n in niveis if n >= max(nivel_modelos, 1))
        if nivel_modelos >= 1:
            motivos.append(f"{n_ok} de {len(niveis)} modelos indicam nível {nivel_modelos} ou mais")

    nivel = nivel_modelos
    if prob_ensemble:
        pa, ps = prob_ensemble.get("p_alerta", 0), prob_ensemble.get("p_severo", 0)
        if nivel >= 1 and pa >= lim["prob_ensemble_eleva"] and nivel < 2:
            nivel = 2
            motivos.append(f"{pa:.0%} dos 51 cenários do ECMWF com ambiente de alerta")
        if nivel >= 2 and ps >= lim["prob_ensemble_eleva"] and nivel < 3:
            nivel = 3
            motivos.append(f"{ps:.0%} dos 51 cenários do ECMWF com ambiente severo")

    if inmet:
        piso = SEVERIDADE_INMET.get(inmet.get("severidade"), 0)
        if piso > nivel:
            nivel = piso
            motivos.append(f"Aviso oficial do INMET: {ROTULO_INMET.get(inmet['severidade'], '')}")

    # ingredientes medianos entre modelos (para exibir e para os perigos)
    def mediana(chave):
        vals = sorted(v[chave] for v in por_modelo.values() if v.get(chave) is not None)
        if not vals:
            return None
        k = len(vals) // 2
        return vals[k] if len(vals) % 2 else (vals[k - 1] + vals[k]) / 2

    ws_med, cape_med, sh_med = mediana("ws"), mediana("cape"), mediana("shear")
    precip_max = max((v["precip_max"] for v in por_modelo.values()), default=0)
    iso_vals = [v["isoterma0_min"] for v in por_modelo.values() if v.get("isoterma0_min")]
    iso_min = min(iso_vals) if iso_vals else None
    gatilho_qualquer = any(v["gatilho_local"] or v["gatilho_regional"] for v in por_modelo.values())

    perigos = []
    if nivel >= 1 and gatilho_qualquer:
        perigos.append("raios")
    if (ws_med or 0) >= lim["wmaxshear_alerta"] and (sh_med or 0) >= lim["cisalhamento_organizado_ms"] and gatilho_qualquer:
        perigos.append("rajadas fortes / vendaval")
    if (cape_med or 0) >= lim["cape_granizo"] and (sh_med or 0) >= lim["cisalhamento_organizado_ms"] and gatilho_qualquer:
        if iso_min is not None and iso_min < lim["isoterma_zero_granizo_grande_m"]:
            perigos.append("granizo (inclusive de maior porte)")
        else:
            perigos.append("granizo")
    if precip_max >= lim["chuva_intensa_mm_h"] or (nivel >= 2 and gatilho_qualquer):
        perigos.append("chuva intensa em pouco tempo")

    return {
        "nivel": nivel,
        "nome": NOMES_NIVEL[nivel],
        "nivel_modelos": nivel_modelos,
        "motivos": motivos,
        "perigos": perigos,
        "ingredientes": {
            "wmaxshear": round(ws_med) if ws_med is not None else None,
            "cape": round(cape_med) if cape_med is not None else None,
            "cisalhamento_ms": round(sh_med, 1) if sh_med is not None else None,
            "precip_max_mm_h": round(precip_max, 1),
            "isoterma0_min_m": round(iso_min) if iso_min else None,
        },
        "por_modelo": {m: {"nivel": v["nivel"], "wmaxshear": round(v["ws"]),
                           "gatilho_local": v["gatilho_local"], "gatilho_regional": v["gatilho_regional"],
                           "hora_pico": v["hora"], "localidade_pico": v.get("localidade")}
                       for m, v in por_modelo.items()},
        "prob_ensemble": prob_ensemble,
        "inmet": inmet,
    }


def prob_ensemble_janela(membros: list[SerieModelo], ini: int, fim: int, lim: dict) -> dict | None:
    """Fração de membros do ensemble cujo pico de WMAXSHEAR na janela passa dos limiares.
    O ensemble não tem 'gatilho' confiável por membro, então mede só o AMBIENTE."""
    if not membros:
        return None
    picos = [ambiente_na_janela(m, ini, fim, lim)["ws"] for m in membros]
    n = len(picos)
    return {
        "membros": n,
        "p_alerta": sum(p >= lim["wmaxshear_alerta"] for p in picos) / n,
        "p_severo": sum(p >= lim["wmaxshear_severo"] for p in picos) / n,
    }
