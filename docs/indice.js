/* Índice de risco convectivo — versão JavaScript de motor/indice.py.
 * Mesma lógica: AMBIENTE LOCAL (WMAXSHEAR) + GATILHO REGIONAL (tempestade simulada a montante).
 * Funciona no navegador (window.Indice) e no Node (module.exports) para testes de paridade.
 */
(function (raiz) {
  "use strict";
  const NOMES = ["Normal", "Atenção", "Alerta", "Severo"];
  const SEV_INMET = { Moderate: 1, Severe: 2, Extreme: 3 };
  const ROT_INMET = { Moderate: "Perigo Potencial (amarelo)", Severe: "Perigo (laranja)", Extreme: "Grande Perigo (vermelho)" };
  const ROSA = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"];
  const rad = g => g * Math.PI / 180;
  const nulo = v => v === null || v === undefined;

  function cisalhamento(v500, d500, v10, d10) {
    if ([v500, d500, v10, d10].some(nulo)) return null;
    const ax = v500 * Math.sin(rad(d500)), ay = v500 * Math.cos(rad(d500));
    const bx = v10 * Math.sin(rad(d10)), by = v10 * Math.cos(rad(d10));
    return Math.hypot(ax - bx, ay - by) / 3.6;
  }
  function wmaxshear(cape, sh) {
    if (nulo(cape) || nulo(sh)) return null;
    return Math.sqrt(2 * Math.max(cape, 0)) * sh;
  }
  function direcaoMedia(dirs) {
    const ds = dirs.filter(d => !nulo(d));
    if (!ds.length) return null;
    const x = ds.reduce((a, d) => a + Math.sin(rad(d)), 0), y = ds.reduce((a, d) => a + Math.cos(rad(d)), 0);
    return ((Math.atan2(x, y) * 180 / Math.PI) + 360) % 360;
  }
  const rosa = g => nulo(g) ? "—" : ROSA[Math.floor(((g + 22.5) % 360) / 45)];
  function anguloEntre(a, b) { const d = Math.abs(a - b) % 360; return Math.min(d, 360 - d); }
  const val = (s, nome, i) => { const l = s[nome] || []; return i < l.length ? l[i] : null; };

  function gatilhoNaJanela(s, ini, fim, lim) {
    for (let i = ini; i < fim; i++) {
      const wc = val(s, "wcode", i), pr = val(s, "precip", i);
      if (!nulo(wc) && wc >= lim.gatilho_weather_code) return true;
      if (!nulo(pr) && pr >= lim.gatilho_precip_mm_h) return true;
    }
    return false;
  }
  function ambienteNaJanela(s, ini, fim, lim) {
    let m = { ws: 0, cape: 0, shear: 0, hora: null }, pmax = 0, rmax = 0, iso = null;
    for (let i = ini; i < fim; i++) {
      const cape = val(s, "cape", i);
      const sh = cisalhamento(val(s, "v500", i), val(s, "d500", i), val(s, "v10", i), val(s, "d10", i));
      const ws = wmaxshear(cape, sh);
      if (ws !== null && cape >= lim.cape_minimo && ws > m.ws) m = { ws, cape, shear: sh, hora: i };
      const pr = val(s, "precip", i); if (!nulo(pr)) pmax = Math.max(pmax, pr);
      const rj = val(s, "rajada", i); if (!nulo(rj)) rmax = Math.max(rmax, rj);
      const iz = val(s, "isoterma0", i); if (!nulo(iz)) iso = iso === null ? iz : Math.min(iso, iz);
    }
    return { ...m, precip_max: pmax, rajada_max: rmax, isoterma0_min: iso };
  }
  function nivelDoModelo(ws, gat, lim) {
    if (gat && ws >= lim.wmaxshear_severo) return 3;
    if (gat && ws >= lim.wmaxshear_alerta) return 2;
    if ((gat && ws >= lim.wmaxshear_atencao) || ws >= lim.wmaxshear_sem_gatilho) return 1;
    return 0;
  }
  function consenso(niveis) {
    if (!niveis.length) return 0;
    const o = [...niveis].sort((a, b) => b - a);
    return o.length >= 2 ? o[1] : o[0];
  }
  const mediana = vs => {
    const v = vs.filter(x => !nulo(x)).sort((a, b) => a - b);
    if (!v.length) return null;
    const k = Math.floor(v.length / 2);
    return v.length % 2 ? v[k] : (v[k - 1] + v[k]) / 2;
  };

  /* local: {localId: {modelo: serie}}; regional: {pontoId: {modelo: serie}} */
  function avaliarJanela(local, regional, ini, fim, lim, prob, inmet) {
    const modelos = [...new Set(Object.values(local).flatMap(o => Object.keys(o)))].sort();
    const pm = {};
    for (const m of modelos) {
      const avs = []; let gatLocal = false;
      for (const [lid, porMod] of Object.entries(local)) {
        const s = porMod[m]; if (!s) continue;
        const a = ambienteNaJanela(s, ini, fim, lim); a.localidade = lid; avs.push(a);
        gatLocal = gatLocal || gatilhoNaJanela(s, ini, fim, lim);
      }
      if (!avs.length) continue;
      const amb = { ...avs.reduce((x, y) => (y.ws > x.ws ? y : x)) };
      amb.precip_max = Math.max(...avs.map(a => a.precip_max));
      amb.rajada_max = Math.max(...avs.map(a => a.rajada_max));
      const isos = avs.map(a => a.isoterma0_min).filter(x => x !== null);
      amb.isoterma0_min = isos.length ? Math.min(...isos) : null;
      const gatReg = Object.values(regional).some(porMod => porMod[m] && gatilhoNaJanela(porMod[m], ini, fim, lim));
      pm[m] = { ...amb, gatilho_local: gatLocal, gatilho_regional: gatReg, nivel: nivelDoModelo(amb.ws, gatLocal || gatReg, lim) };
    }
    const niveis = Object.values(pm).map(v => v.nivel);
    const nivelModelos = consenso(niveis);
    const motivos = [];
    if (niveis.length && nivelModelos >= 1) {
      const ok = niveis.filter(n => n >= Math.max(nivelModelos, 1)).length;
      motivos.push(`${ok} de ${niveis.length} modelos indicam nível ${nivelModelos} ou mais`);
    }
    let nivel = nivelModelos;
    if (prob) {
      const pa = prob.p_alerta || 0, ps = prob.p_severo || 0;
      if (nivel >= 1 && pa >= lim.prob_ensemble_eleva && nivel < 2) { nivel = 2; motivos.push(`${Math.round(pa * 100)}% dos ${prob.membros} cenários do ECMWF com ambiente de alerta`); }
      if (nivel >= 2 && ps >= lim.prob_ensemble_eleva && nivel < 3) { nivel = 3; motivos.push(`${Math.round(ps * 100)}% dos ${prob.membros} cenários do ECMWF com ambiente severo`); }
    }
    if (inmet) {
      const piso = SEV_INMET[inmet.severidade] || 0;
      if (piso > nivel) { nivel = piso; motivos.push(`Aviso oficial do INMET: ${ROT_INMET[inmet.severidade] || ""}`); }
    }
    const vs = Object.values(pm);
    const wsMed = mediana(vs.map(v => v.ws)), capeMed = mediana(vs.map(v => v.cape)), shMed = mediana(vs.map(v => v.shear));
    const pmax = vs.length ? Math.max(...vs.map(v => v.precip_max)) : 0;
    const isos = vs.map(v => v.isoterma0_min).filter(x => x);
    const isoMin = isos.length ? Math.min(...isos) : null;
    const gatQ = vs.some(v => v.gatilho_local || v.gatilho_regional);
    const perigos = [], perigosNivel = {};
    const nGatLocal = vs.filter(v => v.gatilho_local).length;
    const ws0 = wsMed || 0, sh0 = shMed || 0, cape0 = capeMed || 0;
    const shForte = lim.cisalhamento_forte_ms ?? 18, capeProv = lim.cape_granizo_provavel ?? 2500;
    if (nivel >= 1 && gatQ) { perigos.push("raios"); perigosNivel["raios"] = nGatLocal >= 2 ? "provável" : "possível"; }
    if (ws0 >= lim.wmaxshear_alerta && sh0 >= lim.cisalhamento_organizado_ms && gatQ) {
      perigos.push("rajadas fortes / vendaval");
      perigosNivel["rajadas fortes / vendaval"] = (ws0 >= lim.wmaxshear_severo || sh0 >= shForte) ? "provável" : "possível";
    }
    if (cape0 >= lim.cape_granizo && sh0 >= lim.cisalhamento_organizado_ms && gatQ) {
      const nome = isoMin !== null && isoMin < lim.isoterma_zero_granizo_grande_m ? "granizo (inclusive de maior porte)" : "granizo";
      perigos.push(nome); perigosNivel[nome] = (cape0 >= capeProv && sh0 >= shForte) ? "provável" : "possível";
    }
    if (pmax >= lim.chuva_intensa_mm_h || (nivel >= 2 && gatQ)) {
      perigos.push("chuva intensa em pouco tempo");
      perigosNivel["chuva intensa em pouco tempo"] = pmax >= lim.chuva_intensa_mm_h ? "provável" : "possível";
    }
    const porModelo = {};
    for (const [m, v] of Object.entries(pm)) porModelo[m] = { nivel: v.nivel, wmaxshear: Math.round(v.ws), gatilho_local: v.gatilho_local, gatilho_regional: v.gatilho_regional, hora_pico: v.hora, localidade_pico: v.localidade };
    return {
      nivel, nome: NOMES[nivel], nivel_modelos: nivelModelos, motivos, perigos, perigos_nivel: perigosNivel,
      ingredientes: {
        wmaxshear: wsMed === null ? null : Math.round(wsMed), cape: capeMed === null ? null : Math.round(capeMed),
        cisalhamento_ms: shMed === null ? null : Math.round(shMed * 10) / 10, precip_max_mm_h: Math.round(pmax * 10) / 10,
        isoterma0_min_m: isoMin ? Math.round(isoMin) : null
      },
      por_modelo: porModelo, prob_ensemble: prob || null, inmet: inmet || null
    };
  }
  function probEnsembleJanela(membros, ini, fim, lim) {
    if (!membros || !membros.length) return null;
    const picos = membros.map(m => ambienteNaJanela(m, ini, fim, lim).ws), n = picos.length;
    return { membros: n, p_alerta: picos.filter(p => p >= lim.wmaxshear_alerta).length / n, p_severo: picos.filter(p => p >= lim.wmaxshear_severo).length / n };
  }
  function anel(lat, lon, raioKm, n) {
    const pts = [];
    for (let k = 0; k < n; k++) {
      const rumo = 360 * k / n;
      pts.push({ id: "anel" + String(Math.round(rumo)).padStart(3, "0"), rumo,
        lat: +(lat + raioKm / 111 * Math.cos(rad(rumo))).toFixed(4),
        lon: +(lon + raioKm / (111 * Math.cos(rad(lat))) * Math.sin(rad(rumo))).toFixed(4) });
    }
    return pts;
  }
  function pontosAMontante(pts, dir, abertura) {
    return dir === null ? pts.map(p => p.id) : pts.filter(p => anguloEntre(p.rumo, dir) <= abertura).map(p => p.id);
  }
  /* ponto dentro de polígono ([[lat,lon],...]) — ray casting */
  function dentro(lat, lon, poli) {
    let d = false;
    for (let i = 0, j = poli.length - 1; i < poli.length; j = i++) {
      const [yi, xi] = poli[i], [yj, xj] = poli[j];
      if (((yi > lat) !== (yj > lat)) && (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)) d = !d;
    }
    return d;
  }

  const API = { NOMES, cisalhamento, wmaxshear, direcaoMedia, rosa, anguloEntre, gatilhoNaJanela, ambienteNaJanela,
    nivelDoModelo, consenso, avaliarJanela, probEnsembleJanela, anel, pontosAMontante, dentro };
  if (typeof module !== "undefined" && module.exports) module.exports = API; else raiz.Indice = API;
})(typeof window !== "undefined" ? window : globalThis);
