"""Rodada completa SEM rede: substitui as fontes por dados do evento de 02/11/2026.
Serve para testar a integração e gerar um status.json de exemplo para a página.
Uso: python tests/simular_rodada.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
from motor import alerta, fontes, indice  # noqa: E402
from test_indice import NOV02, serie, calmo  # noqa: E402

agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(minute=0, second=0, microsecond=0)
N = 72
HORAS = [(agora + timedelta(hours=h - 2)).strftime("%Y-%m-%dT%H:00") for h in range(N)]


def esticar(d):
    """Repete o evento de 02/11 começando 4 h à frente."""
    pad = 6
    return {k: ([v[0]] * pad + v + [v[-1]] * N)[:N] for k, v in d.items()}


def fake_det(pontos, modelos, fuso, dias=3):
    out = {}
    for p in pontos:
        out[p["id"]] = {}
        for i, m in enumerate(modelos):
            if p["id"].startswith("anel"):
                s = calmo(N)
                if p["id"] in ("anel270", "anel315"):
                    s.wcode = [95 if 10 <= k <= 13 else 3 for k in range(N)]
            else:
                s = serie(esticar(NOV02)) if i < 3 else calmo(N)
            s.d700 = [300] * N
            s.rajada = [30] * N
            s.isoterma0 = [4200] * N
            out[p["id"]][m] = s
    return HORAS, out, []


def fake_perfil(ponto, modelos, fuso, horas_ref, dias=3):
    """Perfil parecido com o de 20/11: jato de norte em 850 hPa, oeste acima; queda de 3 °C na hora 12."""
    p = {"v850": [30] * N, "d850": [350] * N, "v700": [40] * N, "d700": [270] * N,
         "v500": [60] * N, "d500": [270] * N, "v300": [90] * N, "d300": [260] * N,
         "t2m": [29 if k < 12 else 26 for k in range(N)], "d10": [330 if k < 12 else 200 for k in range(N)]}
    return {m: p for m in modelos}


def fake_ens(ponto, modelo, fuso, dias=3):
    return HORAS, [serie(esticar(NOV02))] * 35 + [calmo(N)] * 16


def fake_inmet(cod, cache=None, filtro_area="Paran", estado="Paraná"):
    ini = agora - timedelta(hours=3)
    av = [{"id": "56999", "titulo": "Aviso de Tempestade. Severidade Grau: Perigo Potencial",
             "evento": "Tempestade", "severidade": "Moderate", "inicio": ini.isoformat(),
             "fim": (ini + timedelta(hours=20)).isoformat(),
             "descricao": "Chuva entre 20 e 30 mm/h ou até 50 mm/dia, ventos intensos (40-60 km/h), e queda de granizo.",
             "link": "https://avisos.inmet.gov.br/56999"}]
    poli = [[[-22.8, -52.3], [-22.8, -51.0], [-23.8, -51.0], [-23.8, -52.3]]]
    return av, [{**av[0], "poligonos": poli}]


alerta.coletar_relatos = lambda agora: 0
alerta.DIR_ARQUIVO = RAIZ / "tests" / "_arquivo"
fontes.modelos_deterministicos = fake_det
fontes.ensemble = fake_ens
fontes.perfil_vertical = fake_perfil
alerta.time.sleep = lambda s: None
fontes.avisos_inmet = fake_inmet
alerta.ARQ_ESTADO = RAIZ / "tests" / "_estado_sim.json"
alerta.ARQ_ENS = RAIZ / "tests" / "_ens_sim.json"
alerta.ARQ_HIST = RAIZ / "tests" / "_hist_sim.csv"
if "--manter" not in sys.argv:
  for p in (alerta.ARQ_ESTADO, alerta.ARQ_ENS, alerta.ARQ_HIST):
    p.unlink(missing_ok=True)

st = alerta.rodar(enviar_telegram=False)
assert st["resumo"]["nivel_24h"] >= 2, st["resumo"]
assert st["janelas"] and st["serie_horaria"] and st["localidades"]
j0 = st["janelas"][0]
print("linha:", j0["direcao_linha_graus"], j0["direcao_chegada"], "| células:", j0["direcao_celulas"], "| ar frio:", j0["ar_frio"],
      "| seta:", st["direcao_graus"], st["direcao_chegada"])
assert j0["direcao_linha_graus"] is not None and j0["direcao_chegada"] != j0["direcao_celulas"]
assert any(j["ar_frio"] for j in st["janelas"])
print("\nOK — status.json de exemplo gravado em docs/data/status.json")
