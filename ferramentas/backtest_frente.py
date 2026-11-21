"""Backtest do aviso de entrada de ar frio (frente fria ou frente de rajada) em Astorga, 01-21/11/2026.
Testa variantes de critério e lista, por dia, as horas em que >=2 de 4 modelos disparam.
Referência conhecida: 02/11 madrugada (temporal), 05-07/11 (ciclone e frente fria), 20/11 ~19h (frente de rajada)."""
import json, time, urllib.parse, urllib.request
from collections import defaultdict

LAT, LON = -23.2325, -51.6656
MODELOS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless"]
SETOR_SUL = (110, 250)

def baixar(m):
    q = urllib.parse.urlencode({"latitude": LAT, "longitude": LON, "start_date": "2026-11-01", "end_date": "2026-11-21",
        "hourly": "temperature_2m,pressure_msl,wind_direction_10m,wind_speed_10m", "models": m, "timezone": "America/Sao_Paulo"})
    for e in (0, 10, 30):
        time.sleep(e)
        try:
            with urllib.request.urlopen("https://historical-forecast-api.open-meteo.com/v1/forecast?" + q, timeout=60) as r:
                return json.load(r)["hourly"]
        except Exception as err:
            ult = err
    raise ult

sul = lambda d: d is not None and SETOR_SUL[0] <= d <= SETOR_SUL[1]
VARIANTES = {
    "A: queda>=3C/3h, pressao>=+1, vento sul depois": lambda T, P, D, k: T[k] - T[k+3] >= 3 and P[k+3] - P[k] >= 1 and sul(D[k+3]),
    "B: queda>=4C/3h, pressao>=+1, vento sul depois": lambda T, P, D, k: T[k] - T[k+3] >= 4 and P[k+3] - P[k] >= 1 and sul(D[k+3]),
    "C: queda>=3C/2h, pressao>=+1": lambda T, P, D, k: T[k] - T[k+2] >= 3 and P[k+2] - P[k] >= 1,
    "D: queda>=3C/3h, pressao>=+1, virada para sul": lambda T, P, D, k: T[k] - T[k+3] >= 3 and P[k+3] - P[k] >= 1 and sul(D[k+3]) and not sul(D[k]),
    "E: queda>=2.5C/1h": lambda T, P, D, k: T[k] - T[k+1] >= 2.5,
}
dados = {}
for m in MODELOS:
    try:
        dados[m] = baixar(m)
    except Exception as e:
        print(f"{m}: falhou {e}")
    time.sleep(2)
horas = next(iter(dados.values()))["time"]
for nome, f in VARIANTES.items():
    porhora = defaultdict(set)
    for m, h in dados.items():
        T, P, D = h["temperature_2m"], h["pressure_msl"], h["wind_direction_10m"]
        for k in range(len(horas) - 3):
            try:
                if f(T, P, D, k):
                    porhora[horas[k][:13]].add(m)
            except TypeError:
                pass
    # agrupa em dias: dia -> horas com >=2 modelos (considerando +-1 h de tolerância entre modelos)
    dias = defaultdict(list)
    chaves = sorted(porhora)
    for c in chaves:
        viz = set().union(*(porhora.get(x, set()) for x in chaves if abs(int(x[11:13]) - int(c[11:13])) <= 1 and x[:10] == c[:10]))
        if len(viz) >= 2:
            dias[c[:10]].append(f"{c[11:13]}h({len(viz)})")
    print(f"\n### {nome}")
    for d in sorted(dias):
        print(f"- {d}: {', '.join(dias[d][:8])}")
    if not dias:
        print("- nenhum dia")
