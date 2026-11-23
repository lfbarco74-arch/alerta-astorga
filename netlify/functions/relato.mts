// Recebe um relato de campo ("Como está o tempo aí?") e guarda no Netlify Blobs.
// Sem nome, sem IP guardado; localização arredondada a ~1 km. Um blob por relato (nada de ler-modificar-gravar).
import type { Config, Context } from "@netlify/functions";
import { getStore } from "@netlify/blobs";

// Versão 2: cada fenômeno com a própria escala (não existe "vendaval fraco").
const CEU = ["limpo", "parcial", "nublado", "neblina"];
const MAXIMO = { vento: 4, chuva: 5, granizo: 3, raios: 2 }; // vento: calmo..vendaval; chuva: sem..muito forte; granizo: não..grande; raios: não..perto
const EFEITOS = ["esfriou", "alagamento", "galhos", "estragos", "sem_energia"];
const RUMOS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const PR = { latMin: -27.0, latMax: -22.2, lonMin: -55.0, lonMax: -47.7 }; // Paraná com folga
const ATRASOS = [0, 30, 60, 120]; // "agora", "há 30 min", "há 1 h", "há 2 h"

const erro = (msg: string, status = 400) => Response.json({ ok: false, erro: msg }, { status });

export default async (req: Request, _context: Context) => {
  let b: any;
  try {
    b = await req.json();
  } catch {
    return erro("corpo inválido");
  }
  if (b && typeof b.site === "string" && b.site.length > 0) return Response.json({ ok: true }); // armadilha para robôs

  const lat = Number(b?.lat), lon = Number(b?.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < PR.latMin || lat > PR.latMax || lon < PR.lonMin || lon > PR.lonMax) {
    return erro("localização fora do Paraná");
  }
  const escala = (nome: keyof typeof MAXIMO) => {
    const v = b?.[nome];
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isInteger(n) && n >= 0 && n <= MAXIMO[nome] ? n : null;
  };
  const ceu = CEU.includes(String(b?.ceu)) ? String(b.ceu) : null;
  const vento = escala("vento"), chuva = escala("chuva"), granizo = escala("granizo"), raios = escala("raios");
  const efeitos: string[] = Array.isArray(b?.efeitos) ? [...new Set(b.efeitos.map(String).filter((e: string) => EFEITOS.includes(e)))] as string[] : [];
  const de_onde = RUMOS.includes(String(b?.de_onde)) ? String(b.de_onde) : null;
  if ([ceu, vento, chuva, granizo, raios].every(x => x === null) && !efeitos.length) return erro("marque pelo menos um item");

  const atraso = ATRASOS.includes(Number(b?.minutos_atras)) ? Number(b.minutos_atras) : 0;
  // só vale relato com a localização do aparelho, com precisão de até 2 km (evita local marcado à mão)
  if (b?.origem !== "gps") return erro("é preciso usar a localização do aparelho");
  const precisao_m = Number(b?.precisao_m);
  if (!Number.isFinite(precisao_m) || precisao_m < 0 || precisao_m > 2000) return erro("localização imprecisa demais (máximo de 2 km)");
  const origem = "gps";
  // código aleatório do aparelho (sem login): só para contar aparelhos diferentes; nunca é publicado como está
  const aparelho = typeof b?.aparelho === "string" && /^[A-Za-z0-9-]{16,64}$/.test(b.aparelho) ? b.aparelho : null;

  const agora = new Date();
  const id = `${agora.toISOString()}-${Math.random().toString(36).slice(2, 8)}`;
  const registro = {
    id,
    recebido: agora.toISOString(),
    quando: new Date(agora.getTime() - atraso * 60_000).toISOString(),
    lat: Math.round(lat * 100) / 100,
    lon: Math.round(lon * 100) / 100,
    v: 2,
    ceu, vento, chuva, granizo, raios, efeitos, de_onde,
    origem,
    precisao_m: Math.round(precisao_m),
    aparelho,
  };
  try {
    await getStore("relatos").setJSON(`r/${agora.toISOString().slice(0, 10)}/${id}`, registro);
  } catch (e) {
    console.error("falha ao gravar relato", e);
    return erro("não foi possível salvar agora, tente de novo", 500);
  }
  return Response.json({ ok: true, id });
};

export const config: Config = {
  path: "/api/relato",
  method: "POST",
  rateLimit: { action: "rate_limit", aggregateBy: ["ip", "domain"], windowSize: 60, windowLimit: 4 },
};
