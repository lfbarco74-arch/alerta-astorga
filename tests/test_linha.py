"""Direção da linha (Corfidi) e queda brusca: fórmula, casos simples e paridade Python x JS."""
import json, math, random, shutil, subprocess, sys, unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from motor import indice  # noqa: E402

N = (850, 700, 500, 300)


def perfil(rng, n=30, p_nulo=0.03):
    lst = lambda f: [None if rng.random() < p_nulo else f() for _ in range(n)]  # noqa: E731
    p = {f"v{k}": lst(lambda: rng.uniform(0, 150)) for k in N}
    p.update({f"d{k}": lst(lambda: rng.uniform(0, 360)) for k in N})
    base = rng.uniform(18, 32)
    p["t2m"] = [None if rng.random() < p_nulo else base - rng.choice([0, 0, 0.5, 1, 2.6, 4]) * (i % 5 == 0) for i in range(n)]
    p["d10"] = lst(lambda: rng.uniform(0, 360))
    return p


class TestLinha(unittest.TestCase):
    def test_vento_uniforme(self):
        p = {**{f"v{k}": [50] for k in N}, **{f"d{k}": [270] for k in N}}
        self.assertAlmostEqual(indice.corfidi_de(p, 0), 270, places=6)

    def test_formula_classica(self):
        # implementação independente: vetores de deslocamento (u, v) e "de onde" = oposto
        def uv(s, d):
            r = math.radians(d); return -s * math.sin(r), -s * math.cos(r)
        rng = random.Random(1)
        for _ in range(200):
            p = {}
            for k in N:
                p[f"v{k}"], p[f"d{k}"] = [rng.uniform(1, 120)], [rng.uniform(0, 360)]
            c = [uv(p[f"v{k}"][0], p[f"d{k}"][0]) for k in N]
            u = 2 * sum(x[0] for x in c) / 4 - c[0][0]; v = 2 * sum(x[1] for x in c) / 4 - c[0][1]
            esperado = (math.degrees(math.atan2(u, v)) + 180) % 360
            self.assertLess(indice.angulo_entre(esperado, indice.corfidi_de(p, 0)), 1e-6)

    def test_queda_exige_dois_modelos(self):
        um = {"a": {"t2m": [28, 25, 24], "d10": [0, 200, 200]}, "b": {"t2m": [28, 27.5, 27], "d10": [0, 0, 0]}}
        self.assertIsNone(indice.queda_brusca(um, 0, 3))
        dois = {"a": {"t2m": [28, 25, 24], "d10": [0, 200, 200]}, "b": {"t2m": [28, 27.5, 24.5], "d10": [0, 0, 180]}}
        r = indice.queda_brusca(dois, 0, 3)
        self.assertEqual(r["indice"], 1)
        self.assertEqual(indice.rosa(r["vento_depois"]), "sul")

    def test_resfriamento_do_entardecer_nao_dispara(self):
        tarde = {m: {"t2m": [30, 29, 28, 27, 26, 25], "d10": [180] * 6} for m in "abcd"}
        self.assertIsNone(indice.queda_brusca(tarde, 0, 6))

    @unittest.skipUnless(shutil.which("node"), "Node não instalado")
    def test_paridade_js(self):
        rng = random.Random(7)
        casos = []
        for _ in range(80):
            perfis = {f"m{i}": perfil(rng) for i in range(rng.randint(1, 4))}
            ini = rng.randint(0, 20)
            casos.append((perfis, ini, ini + rng.randint(1, 10)))
        py = [[indice.direcao_linha(p, a, b), indice.queda_brusca(p, a, b)] for p, a, b in casos]
        js = subprocess.run(["node", "-e", """
const I = require(process.argv[1]); const casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify(casos.map(([p, a, b]) => [I.direcaoLinha(p, a, b), I.quedaBrusca(p, a, b)])));""",
                             str(RAIZ / "docs" / "indice.js")], input=json.dumps(casos), capture_output=True, text=True, check=True)
        for (d1, q1), (d2, q2) in zip(py, json.loads(js.stdout)):
            if d1 is None:
                self.assertIsNone(d2)
            else:
                self.assertLess(indice.angulo_entre(d1, d2), 1e-6)
            if q1 is None:
                self.assertIsNone(q2)
            else:
                self.assertEqual(q1["indice"], q2["indice"]); self.assertAlmostEqual(q1["queda_c"], q2["queda_c"])
                if q1["vento_depois"] is not None:
                    self.assertLess(indice.angulo_entre(q1["vento_depois"], q2["vento_depois"]), 1e-6)


if __name__ == "__main__":
    unittest.main()
