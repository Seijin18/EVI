## Why

O EVI só age quando é chamado, e o uso real mostra o custo disso: 520 mensagens
em jun/2026, 66 em ago, zero em set/out; a stack ficou ~6 semanas parada sem que
ninguém sentisse falta. O que ele faz sozinho hoje (heartbeat, daily summary por
JID) é manutenção interna — "N contatos precisando de síntese" não é algo que a
pessoa usa. Para começar o dia, o usuário precisa fazer três pedidos separados
(agenda, tarefas, e-mail). Referências de mercado convergem no mesmo formato:
Google CC ("Your Day Ahead") e ChatGPT Pulse entregam um briefing matinal e
tratam a **resposta ao briefing** como interface. Análise completa:
[`docs/ux-review-2026-10.md`](../../../docs/ux-review-2026-10.md) (P1).

O briefing coloca conteúdo de terceiros (assunto de e-mail, texto de WhatsApp)
na sessão do grafo principal, que tem `delete_emails_by_query` e `schedule_event`
ligados. Por isso a guarda mínima de injeção de prompt (#37)
entra **neste** change, antes de o briefing ir para produção.

Prioridade de produto: produtividade proativa > canal remoto (Telegram).

## What Changes

- **Briefing matinal no Telegram** (`agent/services/briefing.py`, novo): montado
  de forma **determinística** a partir das integrações existentes — agenda de hoje
  (com conflitos), tarefas vencendo/atrasadas, até 3 e-mails que parecem pedir
  ação, compromissos WhatsApp pendentes. Itens numerados. Sem chamada de LLM na
  montagem.
- **Falha parcial visível**: se uma integração falhar (ex.: OAuth do Gmail
  expirado), a seção vira `⚠ Gmail indisponível — <motivo>` e o resto é entregue.
  Isso também transforma o briefing no sinal diário de que o EVI está vivo.
- **Responder ao briefing age sobre ele**: o texto entra na memória da sessão
  `telegram-<TELEGRAM_CHAT_ID>` e os ids estruturados (compromisso, e-mail, evento)
  vão para `session_tool_snapshots`, então "confirma 2" / "apaga o e-mail 1"
  resolvem sem nova busca.
- **Agendamento**: `POST /jobs/briefing` (com `Depends(verify_api_key)`) + script
  Windmill `f/integrations/briefing` no mesmo molde do `heartbeat.py`. Idempotente
  por dia e tipo (`briefing_log`). Variante opcional `kind=evening` (prévia de
  amanhã) pelo mesmo caminho.
- **Heartbeat deixa de notificar manutenção** ao usuário quando o briefing está
  ligado; os achados vão para log.
- **Guarda de injeção (#37, mínima)**: conteúdo de terceiros delimitado como dado
  (`«externo» … «/externo»`) nos quatro caminhos que chegam ao grafo principal —
  o briefing, `summarize_whatsapp`, `_contact_profile_block` e o prompt do
  `whatsapp_llm_extract` — mais instrução defensiva no bootstrap (`AGENTS.md`).
- **Métrica**: `briefing_log` registra envio; resposta do usuário na mesma sessão
  em até 3 h conta como engajamento (`GET /metrics`).

## Impact

Código: `agent/services/briefing.py` (novo), `agent/services/untrusted.py` (novo),
`agent/db.py`, `agent/main.py`, `agent/services/heartbeat.py`,
`agent/services/context_assembly.py`, `agent/services/whatsapp_activity.py`,
`agent/services/whatsapp_llm_extract.py`, `agent/services/metrics.py`,
`agent/testing/cli.py`, `windmill/f/integrations/briefing.py` (+ `.script.yaml`),
`EVI_WORKSPACE/AGENTS.md`, `.env.example`.
Specs: nova capability `proactive`; deltas em `agent-api` e `data-long-memory`.
Sem container novo, sem dependência nova.

## Validação em uso real

Janela de 14 dias após ligar `EVI_BRIEFING_ENABLED`, medida pelo relatório de
`evi-usage-validation`:
- briefing entregue em ≥ 13 de 14 dias (sonda + `briefing_log`);
- resposta ao briefing em ≥ 50% dos dias (`evi_briefing_replied_total`);
- taxa de sucesso por turno não cai em relação à linha de base.

## Out of scope

- Lembretes com horário disparados pelo EVI (P2, `evi-reminders` — próximo change;
  reutiliza o agendamento daqui).
- Repensar a extração de compromissos para "pendências de resposta" (P3). O
  briefing mostra a fila atual como está.
- Botões inline 👍/👎 (exige tratar `callback_query` no poller). A métrica de
  engajamento usa resposta textual.
- Seleção de e-mails por LLM. V1 usa heurística (categoria/remetente).
- Threat model completo do #37 (envio a terceiros, tools destrutivas com
  confirmação). Fica no roadmap Etapa 23 como `evi-prompt-injection-model`, reduzido
  ao que este change não cobre.
- Entrega por WhatsApp (canal de saída proativa é o Telegram — ver risco de
  plataforma em `docs/ux-review-2026-10.md`).
