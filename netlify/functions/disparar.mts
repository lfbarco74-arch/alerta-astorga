// Agendador confiável: o "schedule" do GitHub Actions atrasa ou pula rodadas em horários de pico.
// Esta função agendada do Netlify dispara a rodada a cada 30 min pela API do GitHub (workflow_dispatch).
// Precisa da variável de ambiente GITHUB_TOKEN_DISPARO (token fine-grained, só este repositório,
// permissão "Actions: Read and write"), cadastrada pelo dono do site no painel do Netlify.
import type { Config } from "@netlify/functions";

const URL_DISPARO = "https://api.github.com/repos/lfbarco74-arch/alerta-astorga/actions/workflows/alerta.yml/dispatches";

export default async () => {
  const token = Netlify.env.get("GITHUB_TOKEN_DISPARO");
  if (!token) {
    console.log("disparo: variável GITHUB_TOKEN_DISPARO ausente; nada feito");
    return;
  }
  const r = await fetch(URL_DISPARO, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "alerta-tempo-astorga",
    },
    body: JSON.stringify({ ref: "main", inputs: { origem: "agendador" } }),
  });
  console.log(`disparo: GitHub respondeu ${r.status}${r.ok ? "" : " " + (await r.text()).slice(0, 200)}`);
};

export const config: Config = { schedule: "7,37 * * * *" };
