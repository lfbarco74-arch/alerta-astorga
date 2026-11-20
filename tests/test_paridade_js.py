"""Garante que docs/indice.js (usado no clique do mapa) dá o mesmo resultado que motor/indice.py.
Gera casos reais (02/11 e 07/11) e aleatórios, roda os dois e compara. Pula se não houver Node."""
import json
import random
import shutil
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
from motor import indice  # noqa: E402
from test_indice import LIM, NOV02, NOV07, calmo, serie  # noqa: E402

CAMPOS = ("cape", "v10", "d10", "v500", "d500", "precip", "wcode", "rajada", "isoterma0", "d700")


def aleatoria(rng, n=48):
    def lst(f, p_nulo=0.05):
        return [None if rng.random() < p_nulo else f() for _ in range(n)]
    return indice.SerieModelo(
        cape=lst(lambda: rng.choice([0, 100, 300, 800, 1500, 2500, 4000]) * rng.random()),
        v10=lst(lambda: rng.uniform(0, 40)), d10=lst(lambda: rng.uniform(0, 360)),
        v500=lst(lambda: rng.uniform(10, 110)), d500=lst(lambda: rng.uniform(0, 360)),
        precip=lst(lambda: rng.choice([0, 0, 0, 0.5, 3, 8, 20])), wcode=lst(lambda: rng.choice([0, 1, 3, 51, 61, 80, 95, 96])),
        rajada=lst(lambda: rng.uniform(10, 90)), isoterma0=lst(lambda: rng.uniform(3500, 5200)),
        d700=lst(lambda: rng.uniform(0, 360)))


def para_js(s):
    return {k: getattr(s, k) for k in CAMPOS}


class TestParidade(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node não instalado")
    def test_python_e_js_iguais(self):
        rng = random.Random(42)
        casos = []
        reais = [({"sede": {"a": serie(NOV02), "b": serie(NOV02, 250), "c": calmo(22)}}, {"anel": {"a": calmo(22)}}, 0, 22),
                 ({"sede": {"a": serie(NOV07, 270), "b": calmo(18)}}, {}, 0, 18)]
        for loc, reg, ini, fim in reais:
            casos.append((loc, reg, ini, fim, None, None))
        for k in range(60):
            nmod = rng.randint(1, 4)
            loc = {f"l{j}": {f"m{i}": aleatoria(rng) for i in range(nmod)} for j in range(rng.randint(1, 3))}
            reg = {f"r{j}": {f"m{i}": aleatoria(rng) for i in range(nmod)} for j in range(rng.randint(0, 3))}
            ini = rng.randint(0, 20)
            prob = {"membros": 51, "p_alerta": rng.random(), "p_severo": rng.random()} if k % 3 == 0 else None
            inmet = {"severidade": rng.choice(["Moderate", "Severe", "Extreme"])} if k % 5 == 0 else None
            casos.append((loc, reg, ini, ini + rng.randint(1, 28), prob, inmet))

        esperado, entrada = [], []
        for loc, reg, ini, fim, prob, inmet in casos:
            r = indice.avaliar_janela(loc, reg, ini, fim, LIM, prob, inmet)
            esperado.append(r)
            entrada.append({"local": {l: {m: para_js(s) for m, s in pm.items()} for l, pm in loc.items()},
                            "regional": {l: {m: para_js(s) for m, s in pm.items()} for l, pm in reg.items()},
                            "ini": ini, "fim": fim, "prob": prob, "inmet": inmet})
        membros = [aleatoria(rng) for _ in range(20)]
        esperado_ens = indice.prob_ensemble_janela(membros, 3, 27, LIM)

        script = f"""
const I = require({json.dumps(str(RAIZ / 'docs' / 'indice.js'))});
const d = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = d.casos.map(c => I.avaliarJanela(c.local, c.regional, c.ini, c.fim, d.lim, c.prob, c.inmet));
const ens = I.probEnsembleJanela(d.membros, 3, 27, d.lim);
process.stdout.write(JSON.stringify({{out, ens}}));
"""
        dados = json.dumps({"casos": entrada, "lim": LIM, "membros": [para_js(m) for m in membros]})
        res = subprocess.run(["node", "-e", script], input=dados, capture_output=True, text=True, check=True)
        js = json.loads(res.stdout)

        for i, (py, j) in enumerate(zip(esperado, js["out"])):
            with self.subTest(caso=i):
                for chave in ("nivel", "nome", "nivel_modelos", "perigos", "perigos_nivel", "motivos"):
                    self.assertEqual(py[chave], j[chave], f"caso {i}: {chave}")
                for k, v in py["ingredientes"].items():
                    if isinstance(v, float):
                        self.assertAlmostEqual(v, j["ingredientes"][k], places=1)
                    else:
                        self.assertEqual(v, j["ingredientes"][k], f"caso {i}: {k}")
                for m, v in py["por_modelo"].items():
                    self.assertEqual(v["nivel"], j["por_modelo"][m]["nivel"])
                    self.assertEqual(v["wmaxshear"], j["por_modelo"][m]["wmaxshear"])
        self.assertAlmostEqual(esperado_ens["p_alerta"], js["ens"]["p_alerta"])
        self.assertAlmostEqual(esperado_ens["p_severo"], js["ens"]["p_severo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
