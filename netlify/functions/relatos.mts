// Lista os relatos de campo recentes (para o mapa e para o motor arquivar na calibração).
import type { Config, Context } from "@netlify/functions";
import { getStore } from "@netlify/blobs";

const MAX = 300;

async function resumo(texto: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto));
  return Array.from(new Uint8Array(h).slice(0, 6), b => b.toString(16).padStart(2, "0")).join("");
}

export default async (req: Request, _context: Context) => {
  const url = new URL(req.url);
  const horas = Math.min(48, Math.max(1, Math.round(Number(url.searchParams.get("horas")) || 6)));
  const corte = Date.now() - horas * 3600_000;

  const dias = new Set<string>();
  for (let t = corte; t <= Date.now() + 3600_000; t += 6 * 3600_000) dias.add(new Date(t).toISOString().slice(0, 10));
  dias.add(new Date().toISOString().slice(0, 10));

  try {
    const store = getStore("relatos");
    const chaves: string[] = [];
    for (const dia of dias) {
      const { blobs } = await store.list({ prefix: `r/${dia}/` });
      for (const b of blobs) {
        const iso = b.key.split("/")[2]?.slice(0, 24);
        if (iso && Date.parse(iso) >= corte) chaves.push(b.key);
      }
    }
    chaves.sort().reverse();
    const brutos = (await Promise.all(chaves.slice(0, MAX).map(k => store.get(k, { type: "json" })))).filter(Boolean);
    // o código do aparelho não sai como está: vira um resumo que muda a cada dia (dá para contar aparelhos
    // diferentes no mesmo dia, mas não para seguir uma pessoa ao longo do tempo)
    const relatos = await Promise.all(brutos.map(async ({ aparelho, ...r }: any) => ({
      ...r, ap: aparelho ? await resumo(`${aparelho}|${String(r.quando || r.recebido || "").slice(0, 10)}`) : null,
    })));
    return Response.json(
      { horas, total: relatos.length, relatos },
      { headers: { "Cache-Control": "public, max-age=60", "Netlify-CDN-Cache-Control": "public, s-maxage=60, stale-while-revalidate=60" } },
    );
  } catch (e) {
    console.error("falha ao listar relatos", e);
    return Response.json({ horas, total: 0, relatos: [], erro: "indisponível" }, { status: 500 });
  }
};

export const config: Config = { path: "/api/relatos", method: "GET" };
