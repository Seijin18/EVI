## Context

| Peça existente | Onde | Uso aqui |
|---|---|---|
| Thread daemon com start idempotente | `services/telegram_poller.start_poller` + `lifespan` em `agent/main.py` | Molde do loop de disparo |
| Envio Telegram com retry | `services/telegram_notify.send_telegram_message` → `SendResult` | Entrega |
| Histórico + snapshot após envio proativo | `services/briefing.deliver_briefing` (memória, `db.save_message`, `save_tool_snapshot`) | "feito"/"adia 1h" resolvem o id |
| Hora local | `tools/calendar_time.now_local()` / `evi_timezone()` | `due_at` e recorrência |
| Relógio simulado | libfaketime no `Dockerfile.sim`, passo `clock` com `+Nh` no runner | Cenários de disparo |

## Decisões

### 1. Loop in-process, não cron do Windmill

Pontualidade é o requisito. Um cron por minuto no Windmill é mais pesado e põe mais
uma dependência no caminho. Thread daemon no `agent-api`, tick de 30 s, iniciada no
`lifespan` só com `EVI_REMINDERS_ENABLED=true`; parada no shutdown (o `lifespan`
ganha o trecho depois do `yield`). Cada tick em `soft_fail`.

### 2. Disparo atômico

```sql
CREATE TABLE IF NOT EXISTS reminders (
  id SERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  due_at TIMESTAMPTZ NOT NULL,
  repeat VARCHAR(16),                 -- NULL | daily | weekdays | weekly | monthly
  status VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | firing | sent | done | cancelled
  chat_id VARCHAR(64) NOT NULL,
  created_from VARCHAR(16) NOT NULL,  -- telegram | whatsapp_control | api
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  fired_at TIMESTAMPTZ,
  drift_s INTEGER
);
CREATE INDEX IF NOT EXISTS reminders_due ON reminders (status, due_at);
```

`claim_due(now)`: `UPDATE reminders SET status='firing' WHERE id IN (SELECT id FROM
reminders WHERE status='pending' AND due_at <= now FOR UPDATE SKIP LOCKED LIMIT 20)
RETURNING *` — dois ticks concorrentes nunca disparam o mesmo lembrete. Depois do
envio: sem recorrência → `sent` (+ `fired_at`, `drift_s`); com recorrência → volta a
`pending` com o próximo `due_at`. Envio que falhou → volta a `pending` (tenta no
próximo tick). Linha presa em `firing` há mais de 5 min (processo morreu no meio)
volta a `pending` no tick seguinte.

### 3. Atrasado nunca é descartado

`drift = now - due_at`. Acima de 5 min a mensagem leva "⏰ (atrasado, era HH:MM)".
Recorrente muito atrasado (stack parada dias) dispara **uma** vez com a marca e
avança para a próxima ocorrência futura — não dispara N vezes.

### 4. Recorrência

Presets calculados com aritmética de datas locais (diário, dias úteis, semanal,
mensal); o mensal guarda `anchor_day` (dia do primeiro `due_at`) e cai no último dia
do mês quando ele não existe, voltando ao dia original no mês seguinte. Hora local
convertida para UTC — o horário de parede se mantém. As-built: `dateutil.rrule` foi
descartado (pula meses sem o dia em vez de ajustar); nenhuma dependência nova.

### 5. Criação pelo LLM

`create_reminder(text, due_at_iso, repeat=None)`: o modelo resolve "amanhã às 18h"
com o cabeçalho de calendário que já está no prompt (mesmo caminho do
`schedule_event`). A tool valida: ISO com ou sem offset (sem offset = `EVI_TIMEZONE`),
futuro (até 1 min no passado é tolerado e dispara já), no máximo 1 ano à frente,
`repeat` no enum. Resposta curta com a hora local confirmada ("Lembrete para sex
10/10 às 18:00: pagar o boleto").

### 6. Responder ao lembrete

Após o envio: `AIMessage` na memória da sessão `telegram-<chat_id>`, `db.save_message`
(o histórico é reidratado a cada turno) e snapshot `last_reminder` `{"id", "text"}`.
`AGENTS.md`: "feito"/"ok" após um lembrete → `complete_reminder`; "adia 1h"/"adia
para amanhã" → `snooze_reminder(id, until_iso)`. Sem handler direto; caminho LLM + tools.

### 7. Medida

`evi_reminders_fired_total{late}` e `evi_reminder_drift_seconds` (histograma);
`drift_s` por linha; o relatório semanal ganha a seção "Lembretes" (criados,
disparados, p95 do desvio, atrasados).

## Configuração

| Env | Default | Efeito |
|---|---|---|
| `EVI_REMINDERS_ENABLED` | `false` | Liga o loop. Desligado, as tools respondem "lembretes desativados" e não gravam |
| `EVI_REMINDERS_TICK_SEC` | `30` | Intervalo do loop |

## RAM / containers

Nenhum container novo. Uma thread e uma consulta indexada a cada 30 s.

## Riscos

- **Dois processos `agent-api`** (ex.: smoke do container rodando em paralelo à stack):
  o `SKIP LOCKED` evita disparo duplo no mesmo banco; o smoke usa banco próprio.
- **Clock do container**: `due_at` é `TIMESTAMPTZ`; comparação com `now()` do Python
  em UTC aware, nunca com hora ingênua.
- **Lembrete de teste em produção**: sessões de teste (`is_test`) não criam lembretes
  reais quando `X-Evi-Test`; harnesses usam a simulação.

## Out of scope

Ver `proposal.md`.
