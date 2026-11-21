"""Backtest da direção de chegada: vento em 700 hPa (atual) x vetores de Corfidi (2003).

Corfidi: vento médio da camada de nuvem (850-300 hPa) = Vcl; jato de baixos níveis = V850.
  vetor "upshear" (retroalimentação)  Vup   = Vcl - V850
  vetor "downshear" (linhas que avançam) Vdown = Vcl + Vup = 2*Vcl - V850
Os vetores indicam para onde o sistema se move; a chegada vem do lado oposto.
Também imprime sinais de frente fria à superfície (temperatura, vento a 10 m, pressão).
Uso: python ferramentas/backtest_direcao.py   (roda no GitHub Actions; o Open-Meteo é público)
"""
import json, math, sys, time, urllib.request, urllib.parse

LAT, LON = -23.2325, -51.6656
MODELOS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless"]
NIVEIS = [850, 700, 500, 300]
VARS = ["temperature_2m", "pressure_msl", "wind_speed_10m", "wind_direction_10m"] + \
       [f"wind_{t}_{n}hPa" for n in NIVEIS for t in ("speed", "direction")]
CASOS = [  # (rótulo, API, data inicial, data final, horas de interesse, direção observada)
    ("02/11 madrugada (vendaval, mesmo sistema do tornado de Maringá)", "hist", "2026-11-01", "2026-11-02", ("2026-11-01T22", "2026-11-02T06"), "não registrada"),
    ("07/11 tarde (frente fria, vendavais no PR)", "hist", "2026-11-07", "2026-11-07", ("2026-11-07T10", "2026-11-07T21"), "não registrada"),
    ("20/11 tarde/noite (frente de rajada às 19h)", "hist", "2026-11-20", "2026-11-20", ("2026-11-20T13", "2026-11-20T23"), "sudoeste (relato direto)"),
    ("21/11 madrugada (janela Severo 23h-05h)", "hist", "2026-11-20", "2026-11-21", ("2026-11-20T21", "2026-11-21T09"), "a confirmar"),
]
ROSA = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
rosa = lambda g: ROSA[int(((g + 22.5) % 360) // 45)]

def uv(s, d):
    r = math.radians(d); return -s * math.sin(r), -s * math.cos(r)

def de_onde(u, v):
    """direção de onde o sistema vem (graus) a partir do vetor de deslocamento (u, v)."""
    para = math.degrees(math.atan2(u, v)) % 360
    return (para + 180) % 360

def baixar(api, ini, fim, modelo):
    base = "https://historical-forecast-api.open-meteo.com/v1/forecast" if api == "hist" else "https://api.open-meteo.com/v1/forecast"
    q = urllib.parse.urlencode({"latitude": LAT, "longitude": LON, "start_date": ini, "end_date": fim,
                                "hourly": ",".join(VARS), "models": modelo, "timezone": "America/Sao_Paulo",
                                "wind_speed_unit": "ms"})
    for espera in (0, 10, 30):
        time.sleep(espera)
        try:
            with urllib.request.urlopen(base + "?" + q, timeout=60) as r:
                return json.load(r)["hourly"]
        except Exception as e:
            erro = e
    raise erro

def media_circ(gs):
    gs = [g for g in gs if g is not None]
    if not gs: return None
    s = sum(math.sin(math.radians(g)) for g in gs); c = sum(math.cos(math.radians(g)) for g in gs)
    return math.degrees(math.atan2(s, c)) % 360

def main():
    out = []
    p = lambda *a: (print(*a), out.append(" ".join(str(x) for x in a)))
    for rot, api, ini, fim, (h0, h1), obs in CASOS:
        p(f"\n## {rot}\nDireção observada: **{obs}**\n")
        resumo = {}
        for m in MODELOS:
            try:
                h = baixar(api, ini, fim, m)
            except Exception as e:
                p(f"- {m}: falhou ({e})"); continue
            p(f"\n**{m}**\n\n| hora | T2m | p (hPa) | vento 10 m | 700 hPa (de) | Corfidi down (de) | Corfidi up (de) | |Vdown| m/s |\n|---|---|---|---|---|---|---|---|")
            d700s, downs, ups = [], [], []
            for i, t in enumerate(h["time"]):
                if not (h0 <= t[:13] <= h1): continue
                try:
                    comp = {n: uv(h[f"wind_speed_{n}hPa"][i], h[f"wind_direction_{n}hPa"][i]) for n in NIVEIS}
                except TypeError:
                    continue
                ucl = sum(c[0] for c in comp.values()) / 4; vcl = sum(c[1] for c in comp.values()) / 4
                uup, vup = ucl - comp[850][0], vcl - comp[850][1]
                udn, vdn = ucl + uup, vcl + vup
                d700 = h["wind_direction_700hPa"][i]; ddn = de_onde(udn, vdn); dup = de_onde(uup, vup)
                d700s.append(d700); downs.append(ddn); ups.append(dup)
                d10 = h["wind_direction_10m"][i]; s10 = h["wind_speed_10m"][i]
                p(f"| {t[5:16]} | {h['temperature_2m'][i]:.1f} | {h['pressure_msl'][i]:.0f} | {rosa(d10)} {s10*3.6:.0f} km/h | {d700:.0f}° {rosa(d700)} | {ddn:.0f}° {rosa(ddn)} | {dup:.0f}° {rosa(dup)} | {math.hypot(udn, vdn):.0f} |")
            if d700s:
                resumo[m] = (media_circ(d700s), media_circ(downs), media_circ(ups))
        p("\n**Resumo (média circular na janela)**\n\n| modelo | 700 hPa | Corfidi down | Corfidi up |\n|---|---|---|---|")
        for m, (a, b, c) in resumo.items():
            p(f"| {m} | {a:.0f}° {rosa(a)} | {b:.0f}° {rosa(b)} | {c:.0f}° {rosa(c)} |")
    return out

if __name__ == "__main__":
    main()
