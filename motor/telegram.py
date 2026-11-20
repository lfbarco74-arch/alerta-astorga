"""Envio para o Telegram e regras anti-spam."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}


def enviar(texto: str, silencioso: bool = False) -> bool:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram] sem TELEGRAM_TOKEN/TELEGRAM_CHAT_ID — mensagem não enviada (modo teste):\n" + texto)
        return False
    dados = urllib.parse.urlencode({
        "chat_id": chat, "text": texto, "parse_mode": "HTML",
        "disable_web_page_preview": "true", "disable_notification": "true" if silencioso else "false",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=dados)
    with urllib.request.urlopen(req, timeout=30) as r:
        ok = json.loads(r.read()).get("ok", False)
    print(f"[telegram] enviado={ok}")
    return ok


def decidir(status: dict, estado: dict, cfg_tg: dict, hora_local: int) -> list[tuple[str, str, bool]]:
    """Decide o que enviar. Retorna [(tipo, texto, silencioso)] e atualiza `estado` in-place.

    Regras:
      * sobe de nível (pior janela até 24 h)          -> envia (nível 1 em silêncio)
      * mesmo nível >= 2 mas pico 25% maior            -> envia atualização
      * novo aviso do INMET para Astorga              -> envia
      * cai de >= 2 para <= 1                          -> envia "risco diminuiu" uma vez
      * boletim diário às 6 h                          -> envia resumo curto, em silêncio
    """
    msgs = []
    atual = status["resumo"]["nivel_24h"]
    pico = status["resumo"]["wmaxshear_24h"] or 0
    ultimo = estado.get("ultimo_nivel_enviado", 0)
    ultimo_pico = estado.get("ultimo_pico_enviado", 0)

    if atual > ultimo:
        msgs.append(("subiu", texto_alerta(status), atual == 1 and cfg_tg.get("nivel1_silencioso", True)))
        estado["ultimo_nivel_enviado"], estado["ultimo_pico_enviado"] = atual, pico
    elif atual >= 2 and atual == ultimo and pico >= ultimo_pico * cfg_tg.get("reenvio_se_pico_aumentar", 1.25):
        msgs.append(("piorou", "⬆️ <b>Atualização: ambiente ficou mais intenso</b>\n" + texto_alerta(status), False))
        estado["ultimo_pico_enviado"] = pico
    elif atual < ultimo:
        if ultimo >= 2 and atual <= 1:
            msgs.append(("baixou", texto_baixou(status), True))
        estado["ultimo_nivel_enviado"], estado["ultimo_pico_enviado"] = atual, pico

    avisos_enviados = set(estado.get("avisos_inmet_enviados", []))
    for a in status.get("avisos_inmet", []):
        if a["id"] not in avisos_enviados:
            msgs.append(("inmet", texto_inmet(a, status), a["severidade"] == "Moderate"))
            avisos_enviados.add(a["id"])
    ativos = {a["id"] for a in status.get("avisos_inmet", [])}
    estado["avisos_inmet_enviados"] = sorted(avisos_enviados & ativos)

    hoje = status["gerado_em"][:10]
    if hora_local == cfg_tg.get("boletim_diario_hora", 6) and estado.get("ultimo_boletim") != hoje:
        msgs.append(("boletim", texto_boletim(status), True))
        estado["ultimo_boletim"] = hoje
    return msgs


def _rodape(status):
    return (f"\n\n🔗 <a href=\"{status['pagina_url']}\">Painel completo</a>"
            "\n<i>Projeto pessoal, não oficial. Alertas oficiais: SMS com seu CEP para 40199 (Defesa Civil).</i>")


def texto_alerta(status: dict) -> str:
    r = status["resumo"]
    j = r["janela_pior"]
    linhas = [f"{EMOJI[r['nivel_24h']]} <b>{r['nome_24h'].upper()} — Astorga</b>",
              f"Quando: {j['rotulo'].lower()} (pico perto das {j.get('hora_pico_local') or '—'})"]
    if j["perigos"]:
        linhas.append("Possível: " + ", ".join(j["perigos"]))
    if j["motivos"]:
        linhas.append("Por quê: " + "; ".join(j["motivos"]))
    if status.get("direcao_chegada"):
        linhas.append(f"Se as tempestades se formarem, tendem a chegar pelo {status['direcao_chegada']}.")
    return "\n".join(linhas) + _rodape(status)


def texto_baixou(status: dict) -> str:
    return (f"{EMOJI[status['resumo']['nivel_24h']]} <b>Risco diminuiu em Astorga</b>\n"
            f"Nível atual: {status['resumo']['nome_24h']}." + _rodape(status))


def texto_inmet(a: dict, status: dict) -> str:
    cor = {"Moderate": "🟡", "Severe": "🟠", "Extreme": "🔴"}.get(a["severidade"], "⚠️")
    return (f"{cor} <b>INMET: {a['titulo']}</b>\nInclui Astorga. Vigência: {a['inicio'][:16].replace('T', ' ')} "
            f"até {a['fim'][:16].replace('T', ' ')}.\n{a['descricao'][:250]}\n<a href=\"{a['link']}\">Aviso oficial</a>"
            + _rodape(status))


def texto_boletim(status: dict) -> str:
    linhas = ["☀️ <b>Boletim da manhã — Astorga</b>"]
    for j in status["janelas"]:
        p = (" — " + ", ".join(j["perigos"])) if j["perigos"] and j["nivel"] >= 1 else ""
        linhas.append(f"{EMOJI[j['nivel']]} {j['rotulo']}: {j['nome']}{p}")
    return "\n".join(linhas) + _rodape(status)
