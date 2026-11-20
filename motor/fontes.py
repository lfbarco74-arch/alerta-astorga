"""Coleta de dados: Open-Meteo (modelos e ensemble) e avisos do INMET (RSS + CAP)."""
from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from .indice import SerieModelo

UA = {"User-Agent": "alerta-tempo-astorga/0.1 (projeto pessoal, uso nao comercial)"}

VARS_DET = ["cape", "precipitation", "weather_code", "wind_gusts_10m", "freezing_level_height",
            "wind_speed_10m", "wind_direction_10m", "wind_speed_500hPa", "wind_direction_500hPa",
            "wind_direction_700hPa"]
VARS_ENS = ["cape", "wind_speed_10m", "wind_direction_10m", "wind_speed_500hPa", "wind_direction_500hPa"]


def _get(url: str, tentativas: int = 3, timeout: int = 40) -> bytes:
    erro = None
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            erro = e
            time.sleep(3 * (t + 1))
    raise RuntimeError(f"falha ao acessar {url[:90]}...: {erro}")


def anel(lat: float, lon: float, raio_km: float, n: int) -> list[dict]:
    """Pontos em círculo ao redor da sede. 'rumo' = direção do ponto vista da sede."""
    pts = []
    for k in range(n):
        rumo = 360 * k / n
        dlat = raio_km / 111.0 * math.cos(math.radians(rumo))
        dlon = raio_km / (111.0 * math.cos(math.radians(lat))) * math.sin(math.radians(rumo))
        pts.append({"id": f"anel{int(rumo):03d}", "rumo": rumo,
                    "lat": round(lat + dlat, 4), "lon": round(lon + dlon, 4)})
    return pts


def _serie(h: dict, sufixo: str) -> SerieModelo:
    g = lambda v: h.get(v + sufixo, [])  # noqa: E731
    return SerieModelo(cape=g("cape"), v10=g("wind_speed_10m"), d10=g("wind_direction_10m"),
                       v500=g("wind_speed_500hPa"), d500=g("wind_direction_500hPa"),
                       precip=g("precipitation"), wcode=g("weather_code"), rajada=g("wind_gusts_10m"),
                       isoterma0=g("freezing_level_height"), d700=g("wind_direction_700hPa"))


def modelos_deterministicos(pontos: list[dict], modelos: list[str], fuso: str, dias: int = 3):
    """Retorna (horas, {ponto_id: {modelo: SerieModelo}}). Uma só chamada para todos os pontos."""
    q = {
        "latitude": ",".join(str(p["lat"]) for p in pontos),
        "longitude": ",".join(str(p["lon"]) for p in pontos),
        "hourly": ",".join(VARS_DET),
        "models": ",".join(modelos),
        "forecast_days": dias,
        "timezone": fuso,
    }
    dados = json.loads(_get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)))
    if isinstance(dados, dict):
        if dados.get("error"):
            raise RuntimeError(dados.get("reason"))
        dados = [dados]
    horas, saida = None, {}
    for p, d in zip(pontos, dados):
        h = d["hourly"]
        horas = h["time"]
        saida[p["id"]] = {}
        for m in modelos:
            s = _serie(h, "_" + m if len(modelos) > 1 else "")
            if any(x is not None for x in s.cape) and any(x is not None for x in s.v500):
                saida[p["id"]][m] = s
    return horas, saida


def ensemble(ponto: dict, modelo: str, fuso: str, dias: int = 3):
    """Retorna (horas, [SerieModelo por membro]) do ensemble."""
    q = {"latitude": ponto["lat"], "longitude": ponto["lon"], "hourly": ",".join(VARS_ENS),
         "models": modelo, "forecast_days": dias, "timezone": fuso}
    d = json.loads(_get("https://ensemble-api.open-meteo.com/v1/ensemble?" + urllib.parse.urlencode(q)))
    if d.get("error"):
        raise RuntimeError(d.get("reason"))
    h = d["hourly"]
    sufixos = [""] + sorted({k.split("_member")[1] for k in h if "_member" in k})
    membros = []
    for suf in sufixos:
        s = suf if suf == "" else "_member" + suf
        serie = SerieModelo(cape=h.get("cape" + s, []), v10=h.get("wind_speed_10m" + s, []),
                            d10=h.get("wind_direction_10m" + s, []), v500=h.get("wind_speed_500hPa" + s, []),
                            d500=h.get("wind_direction_500hPa" + s, []), precip=[], wcode=[])
        if any(x is not None for x in serie.cape) and any(x is not None for x in serie.v500):
            membros.append(serie)
    return h["time"], membros


# ---------------------------------------------------------------- INMET
RSS_INMET = "https://apiprevmet3.inmet.gov.br/avisos/rss"
_NS = re.compile(r"\{.*?\}")


def _txt(el, nome):
    for e in el.iter():
        if _NS.sub("", e.tag) == nome:
            return (e.text or "").strip()
    return ""


def _poligonos(cap, max_pontos: int = 400) -> list[list[list[float]]]:
    """Áreas do aviso no CAP ("lat,lon lat,lon ..."), simplificadas para caber na página."""
    saida = []
    for el in cap.iter():
        if _NS.sub("", el.tag) != "polygon" or not (el.text or "").strip():
            continue
        pts = []
        for par in el.text.split():
            try:
                la, lo = par.split(",")
                pts.append([round(float(la), 3), round(float(lo), 3)])
            except ValueError:
                continue
        if len(pts) > max_pontos:
            passo = math.ceil(len(pts) / max_pontos)
            pts = pts[::passo]
        if len(pts) >= 3:
            saida.append(pts)
    return saida


def avisos_inmet(cod_ibge: str, cache: dict | None = None, filtro_area: str = "Paran",
                 estado: str = "Paraná") -> tuple[list[dict], list[dict]]:
    """Avisos ativos do INMET.

    Retorna (avisos que incluem o município pelo código IBGE, avisos do estado com as áreas desenhadas).
    Para poupar o servidor do INMET, só abre o CAP de avisos cuja área cita o Paraná e guarda em
    `cache` ({id: None ou {"aviso", "inclui", "poligonos"}}) o que já foi verificado.
    """
    cache = {} if cache is None else cache
    raiz = ET.fromstring(_get(RSS_INMET))
    do_municipio, do_estado, vistos = [], [], set()
    for item in raiz.iter("item"):
        link = (item.findtext("link") or "").strip()
        titulo = (item.findtext("title") or "").strip()
        desc = item.findtext("description") or ""
        if not link:
            continue
        aid = link.rstrip("/").split("/")[-1]
        vistos.add(aid)
        if aid not in cache:
            if filtro_area and filtro_area not in desc:
                cache[aid] = None
                continue
            try:
                cap = ET.fromstring(_get(link, tentativas=2, timeout=30))
            except Exception:  # noqa: BLE001
                continue
            municipios, estados = "", ""
            for par in cap.iter():
                if _NS.sub("", par.tag) == "parameter":
                    nome = _txt(par, "valueName")
                    if nome == "Municipios":
                        municipios = _txt(par, "value")
                    elif nome == "Estados":
                        estados = _txt(par, "value")
            if estado and estado not in estados:
                cache[aid] = None
                continue
            cache[aid] = {
                "aviso": {
                    "id": aid,
                    "titulo": titulo,
                    "evento": _txt(cap, "event"),
                    "severidade": _txt(cap, "severity"),
                    "inicio": _txt(cap, "onset"),
                    "fim": _txt(cap, "expires"),
                    "descricao": _txt(cap, "description")[:400],
                    "link": f"https://avisos.inmet.gov.br/{aid}",
                },
                "inclui": f"({cod_ibge})" in municipios,
                "poligonos": _poligonos(cap),
            }
        entrada = cache[aid]
        if not entrada:
            continue
        if entrada["inclui"]:
            do_municipio.append(entrada["aviso"])
        do_estado.append({**entrada["aviso"], "poligonos": entrada["poligonos"]})
    for aid in list(cache):  # esquece avisos que saíram do feed
        if aid not in vistos:
            del cache[aid]
    return do_municipio, do_estado


def aviso_na_janela(avisos: list[dict], ini: datetime, fim: datetime) -> dict | None:
    """O aviso mais severo cuja vigência cruza a janela."""
    ordem = {"Moderate": 1, "Severe": 2, "Extreme": 3}
    melhor = None
    for a in avisos:
        try:
            a_ini = datetime.fromisoformat(a["inicio"])
            a_fim = datetime.fromisoformat(a["fim"])
        except ValueError:
            continue
        if a_ini < fim and a_fim > ini:
            if melhor is None or ordem.get(a["severidade"], 0) > ordem.get(melhor["severidade"], 0):
                melhor = a
    return melhor
