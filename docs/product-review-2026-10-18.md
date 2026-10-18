# Revisão do EVI contra as referências — 2026-10-18

> Uma semana depois de ligar briefing, lembretes, dívidas de resposta, voz e conhecimento de
> contato (11/10). Compara o que foi entregue com as referências de
> [`ux-review-2026-10.md` §3](ux-review-2026-10.md#3-referências) (Google CC, ChatGPT Pulse,
> Poke, Superhuman, Zapia, Perplexity, OpenClaw) e com os dados reais de uso. Insumo para a
> próxima fila; fonte de verdade de requisitos continua sendo `openspec/specs/`.

## 1. O que os dados dizem (11–18/10)

Consulta ao Postgres em 2026-10-18 (turnos de teste excluídos).

| Sinal | Valor | Meta do change | Leitura |
|---|---|---|---|
| Turnos de conversa | 23 em 5 de 8 dias, todos no Telegram | > 0 contínuo | O EVI voltou a ser usado (set/out tinham 0) |
| Briefing entregue | 8/8 manhãs | ≥ 13/14 dias | Entrega pontual |
| Briefing respondido | 2/8 dias (25 %) | ≥ 50 % | Lido talvez, mas pouco acionado |
| Dívidas de resposta com ação | 1 de 7 (14 %) | ≥ 30 % | Abaixo do limiar |
| Promessas com ação | 0 de 16 (todas dispensadas na reavaliação) | ≥ 30 % | O padrão antigo gerava ruído; o juiz com contexto entrou em 13/10 e ainda não teve promessa nova |
| Lembretes criados | 0 | ≥ 3 até 17/10 | **Recurso não descoberto** |
| Turnos por voz | 0 | ≥ 3 até 17/10 | **Recurso não descoberto** |
| 👍/👎 (`/bom`, `/ruim`) | 0 | — | Feedback embutido não é usado |
| Latência p50 / p95 | 3,1 s / 51 s | — | p95 vem das tools de WhatsApp (abaixo) |
| `list_recent_whatsapp_messages` / `summarize_whatsapp_messages` | p50 46 s / 41 s | — | Lentas demais para conversa |
| Custo das tarefas estruturadas (OpenRouter ZDR) | US$ 0,004 na semana | < US$ 0,10/dia | Muito abaixo do teto |
| **WhatsApp** | `state: close` desde **14/10 11:21**; nenhum alerta | — | 4 dias sem ler WhatsApp e ninguém soube |
| **Google (agenda, tarefas, Gmail)** | sonda falhou hoje nos três | — | Token OAuth expira a cada 7 dias (app em modo "Teste") — reconectado em 11/10, caiu em 18/10 |

Validações com data vencida (17/10), a registrar no BACKLOG: **lembretes** (0 criados) e
**voz** (0 turnos) não atingiram o limiar — não por falha técnica, mas porque não foram usados.

## 2. Cada referência: o que já temos, o que falta

| Referência | Lição registrada em 10/10 | Hoje no EVI | Lacuna / melhoria |
|---|---|---|---|
| **Google CC** — "Your Day Ahead" por e-mail; você responde para agir; 👍/👎 em cada mensagem | Briefing matinal é o produto; responder ao briefing é a interface; feedback embutido | Briefing às 7h no Telegram, HTML legível, itens numerados, respostas "confirma/respondido/nomeia N" | **Responder exige digitar um comando.** 2/8 respostas. O CC age com um toque. → **Botões inline do Telegram** por item (✅ feito · 🕑 adiar · ✖ dispensar) e 👍/👎 no rodapé. Era "recomendação" no `evi-ux-review`; os dados agora justificam |
| **ChatGPT Pulse** — briefing proativo diário | Validação do padrão | Briefing da manhã | Prévia da noite existe no código (`kind=evening`) mas **não tem schedule**. Ligar a prévia de amanhã às 21h é configuração, não código |
| **Poke** — sinaliza o que exige ação; críticas: urgente enterrado, lembrete no horário errado | Precisão e pontualidade definem confiança | Briefing por exigência de ação, teto de 25 linhas, dívidas determinísticas | **Confiabilidade é o maior risco hoje:** WhatsApp fora 4 dias e Google caindo a cada 7 dias, sem o usuário perceber pelo EVI. A sonda não verifica o WhatsApp; o aviso de OAuth sai no chat, que ninguém abriu |
| **Superhuman Auto Reminders** — lembra de cobrar quem **não respondeu você** | "Pendências de resposta" é o alvo mais útil | Quem espera **sua** resposta (determinístico) + suas promessas | **Falta o outro lado:** "você mandou e não responderam" (follow-up). O estado já existe (`wa_conversation_state.last_out_at`); é uma consulta e uma seção nova, sem LLM |
| **Zapia** — lembretes recorrentes, sync com Calendar, **áudio** | No Brasil, áudio e lembrete são o mínimo | Lembretes com recorrência, adiar/feito; voz no Telegram via Gemini | **Os dois existem e ninguém usou.** O `/ajuda` cita, o briefing não. → Rodapé do briefing com um exemplo rotativo ("dica: mande um áudio 'me lembra de…'"), e o briefing da noite sugerir lembrete para itens com prazo amanhã |
| **Perplexity no WhatsApp** — "me manda X todo dia às 8h" | Tarefas agendadas em linguagem natural | Lembrete agendado envia **texto fixo** | Falta **tarefa agendada** (rodar uma pergunta no horário: "toda sexta 18h, resuma meus e-mails da semana"). Reaproveita o loop dos lembretes + o grafo com allowlist de tools de leitura |
| **OpenClaw** — heartbeat ≠ cron; skills; **número de WhatsApp dedicado** | Separar vigiar de entregar | Watchdog externo, sonda diária, schedules no Windmill | O vigia não vigia o WhatsApp. E o número é o pessoal: a sessão caiu duas vezes em 8 dias (10/10 e 14/10). Número dedicado reduz risco de banimento, mas perde a leitura das conversas pessoais — que é o valor do EVI. → manter o pessoal, **monitorar e alertar** |

## 3. O que está bom (manter)

- **Entrega pontual**: 8/8 briefings, nenhuma falha de envio; sonda roda todo dia.
- **Segurança**: nada exposto na rede (8001/8002 recusam), segredos trocados, autenticação
  por padrão, ZDR fixo no código, teto de gasto fail-closed.
- **Custo**: US$ 0,004/semana nas tarefas estruturadas; Gemini só no chat.
- **Qualidade de teste**: suíte unitária ~1430, smoke, simulação com replay que agora não
  depende do dia do calendário.

## 4. Recomendações priorizadas

### P0 — Confiabilidade percebida (o que derrubou a semana)
1. **Sonda do WhatsApp**: `connectionState` da Evolution como check da sonda e do watchdog
   (a cada 5 min no watchdog, que já fala direto com a API do Telegram). Aviso em ≤ 10 min com
   o comando para gerar o QR. Sem LLM, ~30 linhas.
2. **OAuth do Google sem expirar**: publicar o app OAuth em **Produção** no Google Cloud
   (ação do usuário; tira o ciclo de 7 dias). Enquanto isso, o aviso de OAuth vai **no topo do
   briefing**, não só como mensagem avulsa.
3. **Falha de fonte visível no briefing**: hoje uma seção que falha some em silêncio ou vira
   linha de erro; trocar por um selo no cabeçalho ("⚠️ WhatsApp desconectado desde 14/10 —
   responda 'qr'").

### P1 — Agir com um toque (Google CC)
4. **Botões inline** nos itens do briefing (callback do Telegram → mesmo código das respostas
   "confirma/respondido/dispensa N", que já é determinístico) e 👍/👎 por briefing.
   Meta: respostas ao briefing ≥ 50 % dos dias.

### P2 — Velocidade
5. **Resumo de WhatsApp em < 5 s**: as tools fazem `findMessages` + LLM a cada pedido
   (46 s). Pré-computar o resumo por conversa no lote noturno (já existe o loop das 03:30) e
   servir do cache; ack imediato já existe.

### P3 — Descoberta (Zapia)
6. Dica rotativa no rodapé do briefing (lembrete, áudio, "o que você sabe sobre X").
7. Prévia da noite às 21h (só schedule) com "quer um lembrete?" para itens de amanhã.

### P4 — Capacidades novas (Superhuman, Perplexity)
8. **"Esperando resposta deles"** (follow-up): conversas em que você foi o último a falar
   há > N dias, com pergunta ou pedido na sua mensagem. Seção do briefing de segunda.
9. **Tarefas agendadas** em linguagem natural, só com tools de leitura.

### Registrar e não fazer agora
- Número de WhatsApp dedicado (OpenClaw): perde o valor central; reavaliar se a sessão
  continuar caindo depois do P0.
- Rebaixar promessas: a janela do `evi-promise-context` só começou a valer em 13/10;
  reavaliar em 24/10 com promessas novas.

## 5. Como medir na próxima janela (25/10)

| Métrica | Hoje | Alvo |
|---|---|---|
| Horas sem WhatsApp sem alerta | 96 h | 0 (alerta ≤ 10 min) |
| Dias com Google fora sem aviso no briefing | 1 | 0 |
| Respostas ao briefing | 25 % | ≥ 50 % |
| Ação em dívidas de resposta | 14 % | ≥ 30 % |
| p95 de latência | 51 s | < 15 s |
| Lembretes criados / turnos de voz | 0 / 0 | ≥ 3 / ≥ 3 |
