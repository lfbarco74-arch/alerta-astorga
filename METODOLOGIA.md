# Metodologia — Alerta Tempo Astorga v0.1

## 1. O problema que o sistema resolve (e o que ele não resolve)

**Resolve:** dizer, com 6 a 48 horas de antecedência, se haverá **ambiente** para tempestades severas em Astorga (vendaval, granizo, chuva intensa), em linguagem simples e sem alarmismo.

**Não resolve:** rastrear cada tempestade minuto a minuto. Downbursts têm 1 a 4 km e duram minutos; os modelos globais trabalham com blocos de 9 a 28 km. Para o "está chegando agora", o painel mostra o radar e remete à Defesa Civil.

## 2. Por que não usar "rajada prevista ≥ 60 km/h"

A primeira proposta (Gemini) usava a rajada prevista pelo modelo como gatilho. Nos dois eventos de referência, ela falharia:

| Evento | Rajada máxima no modelo | O que aconteceu |
|---|---|---|
| 02/11/2026, ~03h | 35 km/h, chuva zero no ponto às 3h | Vendaval: 169 casas danificadas em Astorga, emergência decretada. Mesmo sistema do tornado F2 de Maringá (rajada medida de 96,8 km/h no INMET) |
| 07/11/2026, tarde | 58 km/h | Frente fria com vendavais em todo o Paraná (Simepar) |

O modelo não "vê" o vento da tempestade. Ele vê os **ingredientes** que a tornam possível.

## 3. O índice: ambiente local + gatilho regional

### 3.1 Ambiente (em Astorga)
**WMAXSHEAR = √(2·CAPE) × cisalhamento 0–6 km** (m²/s²)
- **CAPE**: energia disponível para correntes ascendentes (J/kg).
- **Cisalhamento**: diferença vetorial entre o vento a 500 hPa (~5,5 km) e a 10 m (m/s). É ele que organiza tempestades em linhas e supercélulas, as que produzem vendaval e granizo. Estudos com dados brasileiros mostram que o cisalhamento pesa mais que a instabilidade nos ambientes severos do país.

Calculado nas quatro localidades (sede, Santa Zélia, Içara, Tupinambá), considerando o pior valor.

### 3.2 Gatilho (em Astorga ou a montante)
Algum modelo simula trovoada (código WMO ≥ 95) ou chuva ≥ 5 mm/h **em Astorga ou nos pontos a 60 km na direção de onde sopra o vento em 700 hPa** (±60°).

O ajuste veio do evento de 02/11: os modelos não simularam a tempestade sobre Astorga, mas simularam convecção na região e um ambiente local muito favorável. Tempestades noturnas nascem a oeste ou noroeste e se deslocam com o vento; o ambiente de Astorga decide se chegam severas.

A direção é **calculada a cada rodada**: no dia 02/11 o vento em 700 hPa vinha de **noroeste** (~300°); no dia 07/11, de **oeste/sudoeste** (~260°). Um corredor fixo a oeste/sudoeste teria errado o primeiro caso.

### 3.3 Níveis por modelo
| Nível | Regra |
|---|---|
| 3 · Severo | WMAXSHEAR ≥ 1200 **e** gatilho |
| 2 · Alerta | WMAXSHEAR ≥ 800 **e** gatilho |
| 1 · Atenção | WMAXSHEAR ≥ 500 com gatilho, **ou** ≥ 1000 sem gatilho (ambiente carregado esperando disparo) |
| 0 · Normal | demais casos |

### 3.4 Combinação
1. **Consenso**: vale o nível alcançado por **pelo menos 2 dos 4 modelos** (ECMWF IFS, GFS, ICON, GEM). Um modelo isolado não dispara alerta.
2. **Ensemble (ECMWF, 51 cenários)**: se ≥ 50% dos cenários têm ambiente de alerta, sobe um nível (de 1 para 2; de 2 para 3 com 50% em ambiente severo). Em vez de um número, uma distribuição: a mesma lógica de olhar o risco de um investimento pela dispersão dos cenários, e não só pelo valor esperado.
3. **Piso oficial**: aviso do INMET que lista Astorga (código IBGE 4102109 no CAP) define um nível mínimo: amarelo → 1, laranja → 2, vermelho → 3. O sistema nunca rebaixa um aviso oficial.

### 3.5 Perigos indicados (com grau)
Cada perigo vem como **provável** (ingrediente com folga) ou **possível** (no limite). Rajadas: provável com WMAXSHEAR ≥ 1200 ou cisalhamento ≥ 18 m/s. Granizo: provável com CAPE ≥ 2500 e cisalhamento ≥ 18 m/s. Chuva intensa: provável se algum modelo simula ≥ 15 mm/h. Raios: provável se 2 ou mais modelos simulam tempestade no próprio ponto.

Regras de entrada:
- **Rajadas/vendaval**: WMAXSHEAR ≥ 800 e cisalhamento ≥ 12,5 m/s, com gatilho.
- **Granizo**: CAPE ≥ 1500 e cisalhamento ≥ 12,5 m/s, com gatilho; "maior porte" se a isoterma de 0 °C estiver abaixo de 4000 m.
- **Chuva intensa**: algum modelo com ≥ 15 mm/h, ou nível ≥ 2 com gatilho.

### 3.6 Direção de chegada: linha x células (desde 21/11/2026)
O vento em 700 hPa (~3 km) conduz cada célula, mas linhas de instabilidade avançam também pela borda do ar frio que despejam, e chegam por outro lado. A seta passou a usar o **vetor de Corfidi** (Corfidi, 2003): vento médio 850-300 hPa (Vcl) e jato de baixos níveis (V850); deslocamento da linha = 2·Vcl − V850, calculado nas 5 horas em torno do pico previsto. O vento em 700 hPa continua guiando o gatilho regional (pontos a montante) e aparece como "direção das células".

| Caso | Observado | 700 hPa (4 modelos) | Corfidi (média na janela) | Corfidi na hora (ECMWF) |
|---|---|---|---|---|
| 20/11, 19h | sudoeste (relato) | 273-299° (oeste/noroeste) | 241-254° | 227° (sudoeste) |
| 02/11 e 07/11 | não registrado | 298-311° / 264-271° | 263-270° / 262-266° | — |

Evidência ainda fraca: um único caso com direção observada. Os relatos de campo com "de onde veio" vão decidir se o vetor de Corfidi fica.

### 3.7 Queda brusca de temperatura
Aviso quando ≥ 2 modelos preveem queda ≥ 2,5 °C em 1 hora (tolerância de 1 h entre modelos): assinatura de frente de rajada ou frente fria. O resfriamento normal do fim de tarde fica perto de 1 °C/h; critérios de 3 °C em 2-3 h dispararam em quase todos os fins de tarde de novembro e foram descartados. Backtest 01-21/11/2026: disparou em 01/11 16h, 07/11 14-15h (frente fria), 14/11 16-17h (a confirmar) e 20/11 18-19h (observado às 19h). Não altera o nível de alerta.

## 4. Evidência da calibração (Open-Meteo Historical Forecast, Astorga)

| Janela | CAPE máx. | Cisalhamento | WMAXSHEAR | Gatilho | Nível |
|---|---|---|---|---|---|
| 01/11 12h → 02/11 09h | 2290 J/kg | ~15 m/s | ~1030–1220 | trovoada às 14–15h e 08h | **Alerta/Severo** |
| 02/11 20h → 06h, só o ponto | 1820 | ~14 | ~860 | nenhum | Normal → **erraria** |
| 02/11 20h → 06h, com região | idem | idem | idem | convecção a montante | **Alerta** |
| 07/11 06h → 23h | 4160 J/kg | ~13–16 m/s | ~1170 | trovoada às 13h e 17h | **Alerta**, granizo |

**Ponto de atenção (honestidade sobre falsos alarmes):** de 20/10 a 19/11/2026, um período excepcionalmente ativo no norte do Paraná, o ambiente passou de 1000 em cerca de 12 dos 31 dias, e com gatilho em cerca de 7. Parte desses dias teve tempestades reais (24/10, 05/11, com aviso de perigo do INMET), mas não todos em Astorga. Por isso o Telegram só fala quando o nível **muda**, e a calibração será revista.

## 4.1 Primeiro caso registrado (20/11/2026, 19h, relato de campo)
Painel em **Alerta** desde as 15h20 (pico previsto 18–19h, chegada pelo oeste); aviso laranja do INMET ativo. Às 19h, frente de rajada em Astorga: vento forte com direção variável, queda brusca de temperatura, energia piscou. Pouca chuva, sem granizo, sem danos; núcleo passou ao lado. **Acerto parcial**: ambiente, horário e rajada corretos; chuva intensa e granizo listados não ocorreram no ponto. Consequência: os perigos passaram a ter grau ("provável" ou "possível").

## 5. Como vamos medir se funciona
Cada rodada grava uma linha em `data/historico.csv`. Depois de cada evento (ou de cada mês), comparar com o que aconteceu:
- **POD** (acerto): eventos reais em que o sistema estava em Alerta ou Severo com antecedência.
- **FAR** (falso alarme): dias em Alerta/Severo sem tempestade forte em Astorga nem nos vizinhos.
- **Antecedência média** do primeiro Alerta.

A meta para a v0.2 é ter 2 a 3 meses de histórico e ajustar os limiares por esses números, não por impressão.

## 6. Limites conhecidos
- Sem observações em tempo real (estações, raios, radar quantitativo) no motor. O radar aparece só no painel.
- A rede aberta de radares do Simepar não tem API pública. O radar de banda S previsto para Jandaia do Sul (~30 km) muda o jogo se os dados forem abertos.
- O GitHub Actions pode atrasar rodadas agendadas em horários de pico.
- Cidade e distritos ficam a 6–13 km entre si, menos que um bloco de modelo: a diferença urbano/rural está no **tipo de impacto**, não no dado.

## 7. Próximos passos (v0.2)
1. Revisão dos limiares com o histórico (POD/FAR).
2. Observações: estações automáticas do INMET (Maringá) como confirmação de rajada medida.
3. Raios em tempo real, se houver fonte aberta com licença compatível.
4. Variável de energia de descida (DCAPE), o melhor discriminador de downburst, assim que houver fonte aberta para o Brasil.

## Fontes
- Corfidi, S. F. (2003). Cold pools and MCS propagation: forecasting the motion of downwind-developing MCSs. *Weather and Forecasting*, 18(6), 997-1017.
- Open-Meteo: Forecast, Ensemble e Historical Forecast APIs (CC-BY 4.0).
- INMET: feed RSS `apiprevmet3.inmet.gov.br/avisos/rss` e CAP de cada aviso.
- Simepar e imprensa regional: registros dos eventos de 02/11 e 07/11/2026.
- Taszarek et al. (2020), *Severe Convective Storms across Europe and the United States, Part II* — WMAXSHEAR como composto de instabilidade e cisalhamento.
- Estudo de discriminantes CAPE × cisalhamento para tempestades severas no Brasil (NSF PAR 10510960).
