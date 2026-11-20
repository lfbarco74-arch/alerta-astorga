# Alerta Tempo Astorga — v0.1 (teste)

Painel e alertas no Telegram sobre risco de tempestade severa, vendaval e granizo em Astorga (PR).
Projeto pessoal, não oficial, sem fins comerciais.

- **Motor** (`motor/`): Python sem dependências externas. Roda no GitHub Actions a cada 30 min.
- **Painel** (`docs/`): página estática servida pelo GitHub Pages, lê `docs/data/status.json`.
- **Alertas**: canal do Telegram, enviados pelo próprio motor, com regras para não repetir mensagens.
- **Metodologia**: veja [METODOLOGIA.md](METODOLOGIA.md).

## Como está no ar
- **Página**: Netlify (`https://alerta-tempo-astorga.netlify.app/`), publicada a partir da pasta `docs/` do branch `main`.
- **Motor**: GitHub Actions, a cada 30 min (`.github/workflows/alerta.yml`).
- **Dados**: cada rodada grava `status.json`, `estado.json`, `ensemble_cache.json` e `historico.csv` no branch **`dados`**. A página lê `status.json` direto desse branch. Como o Netlify só acompanha o `main`, as rodadas não geram deploys.
- **Telegram**: desligado (`"ativo": false` em `config.json`). Para ligar: crie bot e canal, cadastre `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` em *Settings → Secrets and variables → Actions* e mude para `true`.

## Previsão por ponto (clique no mapa)
- Qualquer ponto do Paraná: a página consulta o Open-Meteo direto do navegador de quem clica e aplica o mesmo índice do motor (`docs/indice.js`, idêntico a `motor/indice.py`, com teste de paridade em `tests/test_paridade_js.py`).
- É **previsão, não alerta**: não gera mensagens. Fora de ~150 km de Astorga aparece o aviso de confiança menor (limiares calibrados no norte do PR).
- Avisos do INMET por ponto: o motor publica em `status.json` (`avisos_estado`) as áreas dos avisos vigentes no Paraná; a página testa se o ponto está dentro.
- Link compartilhável: `https://alerta-tempo-astorga.netlify.app/#p=LAT,LON`.
- Aba **Windy**: incorporação oficial do windy.com (marca visível, uso não comercial).

## Testar localmente
```bash
python -m unittest discover -s tests -p "test_*.py"   # testes com os eventos de 02/11 e 07/11
python tests/simular_rodada.py                         # rodada completa sem rede (dados simulados)
python -m motor.alerta --sem-telegram                  # rodada real, imprime as mensagens em vez de enviar
```

## Regras de envio no Telegram
| Situação | Envia? |
|---|---|
| Nível das próximas 24 h sobe | Sim (nível 1 chega sem som) |
| Mesmo nível ≥ 2, mas o ambiente fica 25% mais intenso | Sim, como atualização |
| Novo aviso do INMET que inclui Astorga | Sim, uma vez por aviso |
| Cai de Alerta/Severo para Atenção/Normal | Sim, uma vez ("risco diminuiu") |
| Boletim das 6 h | Sim, sem som |
| Nada mudou | Não |

## Arquivos gerados a cada rodada
- `docs/data/status.json` — o que o painel mostra.
- `data/estado.json` — memória anti-repetição do Telegram e cache dos avisos do INMET.
- `data/ensemble_cache.json` — ensemble do ECMWF (buscado a cada 3 h).
- `data/historico.csv` — uma linha por rodada. Serve para medir acertos e falsos alarmes depois de cada evento.

## Fontes e créditos
Previsão: [Open-Meteo](https://open-meteo.com/) (CC-BY 4.0), com dados de ECMWF, NOAA GFS, DWD ICON e ECCC GEM.
Avisos: [INMET](https://avisos.inmet.gov.br/). Radar no painel: [RainViewer](https://www.rainviewer.com/).
Alertas oficiais: SMS com o CEP para **40199** (Defesa Civil do Paraná).
