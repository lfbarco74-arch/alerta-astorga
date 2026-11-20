// Recebe um relato de campo ("Como está o tempo aí?") e guarda no Netlify Blobs.
// Sem nome, sem IP guardado; localização arredondada a ~1 km. Um blob por relato (nada de ler-modificar-gravar).
import type { Config, Context } from "@netlify/functions";
import { getStore } from "@netlify/blobs";

const EVENTOS = ["vento_forte", "vendaval", "chuva_forte", "granizo", "raios", "alagamento", "estragos", "sem_energia", "tempo_bom"];
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
  let eventos: string[] = Array.isArray(b?.eventos) ? [...new Set(b.eventos.filter((e: unknown) => EVENTOS.includes(String(e))))] as string[] : [];
  if (eventos.length > 1) eventos = eventos.filter(e => e !== "tempo_bom");
  if (!eventos.length) return erro("marque pelo menos um item");

  const soTempoBom = eventos.length === 1 && eventos[0] === "tempo_bom";
  const intensidade = soTempoBom ? null : Math.min(3, Math.max(1, Math.round(Number(b?.intensidade) || 2)));
  const atraso = ATRASOS.includes(Number(b?.minutos_atras)) ? Number(b.minutos_atras) : 0;
  const origem = b?.origem === "gps" ? "gps" : "mapa";

  const agora = new Date();
  const id = `${agora.toISOString()}-${Math.random().toString(36).slice(2, 8)}`;
  const registro = {
    id,
    recebido: agora.toISOString(),
    quando: new Date(agora.getTime() - atraso * 60_000).toISOString(),
    lat: Math.round(lat * 100) / 100,
    lon: Math.round(lon * 100) / 100,
    eventos,
    intensidade,
    origem,
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
