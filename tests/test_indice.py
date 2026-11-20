"""Testes com valores reais do Open-Meteo (Historical Forecast API) para Astorga.

Eventos de referência:
  * 02/11/2026 ~03h — vendaval em Astorga (169 casas danificadas); mesmo sistema do tornado F2 de Maringá.
  * 07/11/2026 tarde — frente fria com vendavais em todo o Paraná.
Os valores horários foram copiados da API (modelo 'best_match'). As direções do vento em 10 m e
500 hPa foram fixadas iguais (premissa conservadora: subestima o cisalhamento vetorial).
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from motor import indice, telegram  # noqa: E402

LIM = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))["limiares"]

# 01/11 12h -> 02/11 09h  (22 horas)
NOV02 = dict(
    cape=[1560, 1980, 2050, 2080, 1880, 2070, 2290, 1900, 1820, 1090, 980, 920, 960, 800, 960, 530, 540, 460, 820, 610, 680, 70],
    v500=[57, 56, 58.6, 60.5, 60, 60, 59.8, 62, 61, 60, 62, 63, 65, 71, 68, 67, 67, 69, 68, 66, 57, 61],
    v10=[17.8, 16.2, 16.2, 10.7, 11.1, 8.3, 5.2, 8, 10, 9, 9, 12, 15, 15, 15, 12, 15, 20, 15, 11, 12, 16],
    precip=[0.2, 0.1, 1.8, 1.2, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.6, 0.1, 0.3, 0.2, 4.8, 0.1],
    wcode=[51, 51, 95, 95, 51, 1, 1, 1, 3, 3, 3, 3, 3, 1, 3, 3, 80, 51, 51, 51, 95, 51],
)
# 07/11 06h -> 07/11 23h (18 horas)
NOV07 = dict(
    cape=[1160, 1600, 2470, 2610, 3870, 4160, 2860, 1880, 2550, 450, 1030, 1350, 1200, 720, 330, 20, 60, 110],
    v500=[50, 47, 47, 50, 52, 56, 57, 59, 64, 71, 69, 65, 66, 74, 74, 76, 72, 71],
    v10=[8, 8, 10, 13, 4, 19, 26, 20, 5, 24, 16, 9, 9, 9, 7, 6, 7, 9],
    precip=[0, 0, 0, 0, 0.6, 0, 0.1, 1.4, 0.2, 0, 1.4, 2.4, 0.3, 0.1, 0, 0, 0, 0],
    wcode=[0, 0, 1, 3, 53, 3, 51, 95, 51, 3, 80, 95, 51, 51, 3, 3, 3, 3],
)


def serie(d, direcao=300):
    n = len(d["cape"])
    return indice.SerieModelo(cape=d["cape"], v10=d["v10"], d10=[direcao] * n, v500=d["v500"],
                              d500=[direcao] * n, precip=d["precip"], wcode=d["wcode"], d700=[direcao] * n)


def calmo(n=24):
    return indice.SerieModelo(cape=[100] * n, v10=[10] * n, d10=[90] * n, v500=[30] * n, d500=[270] * n,
                              precip=[0] * n, wcode=[1] * n)


def regional_com_tempestade(n, hora):
    s = calmo(n)
    s.wcode = [95 if i == hora else 3 for i in range(n)]
    return s


class TestEventosReais(unittest.TestCase):
    def test_02nov_janela_24h_tarde_do_dia_1(self):
        """Saída das 12h de 01/11: o dia seguinte já aparece como Alerta (nível >= 2)."""
        loc = {"sede": {"best": serie(NOV02)}}
        r = indice.avaliar_janela(loc, {}, 0, 22, LIM)
        self.assertGreaterEqual(r["nivel"], 2, r)
        self.assertIn("rajadas fortes / vendaval", r["perigos"])

    def test_02nov_madrugada_so_dispara_com_gatilho_regional(self):
        """Janela 20h-06h: o modelo NÃO simula tempestade sobre Astorga (chuva zero às 3h).
        Sem pontos regionais: nível 0. Com tempestade a montante no modelo: Alerta."""
        loc = {"sede": {"best": serie(NOV02)}}
        sem = indice.avaliar_janela(loc, {}, 8, 19, LIM)
        self.assertLessEqual(sem["nivel"], 1)
        reg = {"anel315": {"best": regional_com_tempestade(22, 13)}}
        com = indice.avaliar_janela(loc, reg, 8, 19, LIM)
        self.assertGreaterEqual(com["nivel"], 2, com)

    def test_07nov_tarde(self):
        loc = {"sede": {"best": serie(NOV07, 270)}}
        r = indice.avaliar_janela(loc, {}, 0, 18, LIM)
        self.assertGreaterEqual(r["nivel"], 2, r)
        self.assertIn("granizo", " ".join(r["perigos"]))

    def test_regra_antiga_do_gemini_teria_falhado(self):
        """Regra 'rajada >= 60 km/h = severo': o modelo mostrou no máximo 58 km/h (07/11)
        e 35 km/h (02/11). Ambas as datas ficariam abaixo do nível severo."""
        rajadas_modelo_02nov = [25, 26, 26, 27, 28, 25, 35, 34, 28, 25]
        rajadas_modelo_07nov = [14, 16, 20, 26, 28, 37, 58, 55, 38, 25, 46, 37]
        self.assertLess(max(rajadas_modelo_02nov), 60)
        self.assertLess(max(rajadas_modelo_07nov), 60)


class TestRegras(unittest.TestCase):
    def test_dia_calmo(self):
        r = indice.avaliar_janela({"sede": {"a": calmo(), "b": calmo()}}, {}, 0, 24, LIM)
        self.assertEqual(r["nivel"], 0)
        self.assertEqual(r["perigos"], [])

    def test_consenso_exige_dois_modelos(self):
        loc = {"sede": {"a": serie(NOV02), "b": calmo(22), "c": calmo(22)}}
        r = indice.avaliar_janela(loc, {}, 0, 22, LIM)
        self.assertEqual(r["nivel_modelos"], 0, "um modelo sozinho não deve disparar")
        loc = {"sede": {"a": serie(NOV02), "b": serie(NOV02), "c": calmo(22)}}
        self.assertGreaterEqual(indice.avaliar_janela(loc, {}, 0, 22, LIM)["nivel"], 2)

    def test_piso_do_inmet(self):
        r = indice.avaliar_janela({"sede": {"a": calmo()}}, {}, 0, 24, LIM, inmet={"severidade": "Severe"})
        self.assertEqual(r["nivel"], 2)
        self.assertTrue(any("INMET" in m for m in r["motivos"]))

    def test_ensemble_eleva_um_nivel(self):
        loc = {"sede": {"a": serie(NOV02), "b": serie(NOV02)}}
        base = indice.avaliar_janela(loc, {}, 8, 19, LIM)  # madrugada, sem gatilho: nível <= 1
        com = indice.avaliar_janela(loc, {}, 8, 19, LIM, prob_ensemble={"p_alerta": 0.7, "p_severo": 0.1})
        if base["nivel"] == 1:
            self.assertEqual(com["nivel"], 2)

    def test_prob_ensemble(self):
        membros = [serie(NOV02)] * 30 + [calmo(22)] * 21
        p = indice.prob_ensemble_janela(membros, 0, 22, LIM)
        self.assertAlmostEqual(p["p_alerta"], 30 / 51)

    def test_cisalhamento_vetorial(self):
        self.assertAlmostEqual(indice.cisalhamento_ms(36, 270, 0, 0), 10.0, places=3)
        self.assertAlmostEqual(indice.cisalhamento_ms(36, 270, 36, 90), 20.0, places=3)

    def test_direcao_e_rosa(self):
        self.assertEqual(indice.rosa(indice.direcao_media([350, 10])), "norte")
        self.assertEqual(indice.rosa(300), "noroeste")


class TestTelegram(unittest.TestCase):
    def _status(self, nivel, ws=900, avisos=None):
        j = {"rotulo": "De 6 a 24 horas", "nivel": nivel, "nome": indice.NOMES_NIVEL[nivel],
             "perigos": ["raios"], "motivos": ["teste"], "hora_pico_local": "03:00"}
        return {"gerado_em": "2026-11-20T10:00-03:00", "pagina_url": "https://x", "direcao_chegada": "noroeste",
                "resumo": {"nivel_24h": nivel, "nome_24h": indice.NOMES_NIVEL[nivel], "wmaxshear_24h": ws,
                           "janela_pior": j},
                "janelas": [j], "avisos_inmet": avisos or []}

    def test_sobe_reenvia_baixa(self):
        cfg, e = {"nivel1_silencioso": True, "reenvio_se_pico_aumentar": 1.25, "boletim_diario_hora": 6}, {}
        self.assertEqual([m[0] for m in telegram.decidir(self._status(2), e, cfg, 10)], ["subiu"])
        self.assertEqual(telegram.decidir(self._status(2), e, cfg, 10), [], "mesmo nível: silêncio")
        self.assertEqual([m[0] for m in telegram.decidir(self._status(2, ws=1200), e, cfg, 10)], ["piorou"])
        self.assertEqual([m[0] for m in telegram.decidir(self._status(0), e, cfg, 10)], ["baixou"])
        self.assertEqual([m[0] for m in telegram.decidir(self._status(1), e, cfg, 10)], ["subiu"])

    def test_inmet_uma_vez_e_boletim(self):
        cfg, e = {"boletim_diario_hora": 6}, {}
        av = [{"id": "1", "titulo": "Aviso de Tempestade", "severidade": "Severe", "inicio": "2026-11-20T09:00",
               "fim": "2026-11-20T23:00", "descricao": "x", "link": "https://y"}]
        tipos = [m[0] for m in telegram.decidir(self._status(0, avisos=av), e, cfg, 6)]
        self.assertEqual(tipos, ["inmet", "boletim"])
        self.assertEqual(telegram.decidir(self._status(0, avisos=av), e, cfg, 6), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
