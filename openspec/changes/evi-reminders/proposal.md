## Why

"Me lembra às 18h de pagar o boleto" é o pedido mais básico de um assistente por
mensagem e hoje é impossível: o EVI só cria evento no Google Calendar e depende da
notificação de outro app. Pontualidade é o que define confiança em lembretes (a
crítica recorrente a assistentes concorrentes é lembrete atrasado). Depois do
briefing (#40), é o segundo passo do EVI chegar até a pessoa sem ser chamado.
Roadmap: Etapa 19; análise em [`docs/ux-review-2026-10.md`](../../../docs/ux-review-2026-10.md) (P2).

## What Changes

- Tabela `reminders` e tools `create_reminder`, `list_reminders`, `cancel_reminder`,
  `snooze_reminder`, `complete_reminder` (registradas em `registry.py`).
- Disparo por **loop in-process** no `agent-api` (thread daemon, tick de 30 s, mesmo
  padrão do `telegram_poller`), atrás de `EVI_REMINDERS_ENABLED` (default `false`).
- Recorrência por preset (`daily`, `weekdays`, `weekly`, `monthly`) calculada com
  `dateutil.rrule` no fuso `EVI_TIMEZONE`.
- Responder ao lembrete age sobre ele ("feito", "adia 1h", "adia para amanhã"): o
  lembrete entra no histórico da sessão Telegram e num snapshot `last_reminder`,
  como o briefing.
- Lembrete atrasado (stack fora do ar) é entregue ao voltar com a marca "atrasado",
  nunca descartado em silêncio.
- Métrica de pontualidade (desvio entre `due_at` e envio) no `/metrics` e no
  relatório semanal.

## Impact

Novo: `agent/services/reminders.py`, `agent/services/reminder_loop.py`,
`agent/tools/reminder_tools.py`, `tests/sim/scenarios/reminders/`.
Alterado: `agent/db.py`, `agent/main.py` (lifespan), `agent/tools/registry.py`,
`agent/services/metrics.py`, `agent/services/usage_report.py`,
`EVI_WORKSPACE/AGENTS.md`, `agent/requirements.txt` (`python-dateutil`, pinado),
`.env.example`, `tests/sim/sim.env`. Spec: `proactive`. Sem container novo.

## Validação em uso real

Janela de 7 dias após ligar `EVI_REMINDERS_ENABLED`, medida pelo relatório semanal:
- desvio de disparo < 60 s em ≥ 95% dos lembretes (`evi_reminder_drift_seconds`);
- nenhum lembrete vencido sem envio (`status='pending'` com `due_at` > 10 min no passado = 0);
- ≥ 3 lembretes criados pelo usuário na janela (uso real, não teste).

## Out of scope

- Escalonamento para SMS/ligação; lembretes para terceiros; envio por WhatsApp.
- Recorrência arbitrária (RRULE livre, "toda segunda e quarta"): só os presets.
- Lembretes no briefing matinal (seção própria) — avaliar depois de medir uso.
- Lembrete por localização.
