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
  status VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | firing | sent | done | cancelled | failed
  chat_id VARCHAR(64) NOT NULL,
  created_from VARCHAR(16) NOT NULL,  -- canal real do turno: telegram | whatsapp_control | api
  snooze_until TIMESTAMPTZ,           -- adiamento de UMA ocorrência; NULL = sem adiamento
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  fired_at TIMESTAMPTZ,
  drift_s INTEGER
);
CREATE INDEX IF NOT EXISTS reminders_due ON reminders (status, due_at);
```

`claim_due(now)`: `UPDATE reminders SET status='firing' WHERE id IN (SELECT id FROM
reminders WHERE status='pending' AND COALESCE(snooze_until, due_at) <= now FOR UPDATE SKIP LOCKED LIMIT 20)
RETURNING *` — dois ticks concorrentes nunca disparam o mesmo lembrete. Depois do
envio: sem recorrência → `sent` (+ `fired_at`, `drift_s`); com recorrência → volta a
`pending` com o próximo `due_at`. Envio que falhou → volta a `pending` (tenta no
próximo tick); se o resultado for `not_configured` (sem token/chat), vira `failed` e
é logado uma vez. `finish_fired` só age em linha `firing`; se o envio passou mas o
`finish_fired` falhou, ele é repetido até 3x no tick e, persistindo, fica numa lista em
memória terminada no início do tick seguinte (antes do `requeue_stuck`), sem reenviar. Linha presa em `firing` há mais de 5 min (processo morreu no meio)
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

### 5b. Adiar e concluir recorrentes

`due_at` guarda o agendamento da série (âncora de hora/dia da semana); o adiamento vai
em `snooze_until` e o horário efetivo é `COALESCE(snooze_until, due_at)` (usado por
`claim_due`, listagem, atraso/drift). "adia 1h" num diário 08:00 reentrega aquela
ocorrência às 09:00 e a próxima continua amanhã 08:00: no disparo adiado limpa-se
`snooze_until` e mantém-se o `due_at` (já a próxima ocorrência) — não avança duas
vezes; se o `due_at` ainda não passou à frente, a recorrência é calculada a partir
da âncora, nunca do horário do adiamento. Avulso adiado volta de `sent` a `pending`
com `snooze_until`. "feito" num recorrente confirma só a ocorrência (status e série
intactos; `complete_reminder` devolve a flag e a tool diz "o próximo é <data>");
parar a série é só `cancel_reminder`. `snooze`/`complete`/`cancel` filtram por
`chat_id` (`TELEGRAM_CHAT_ID`).

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
- **Lembrete de teste em produção**: turnos de teste (`X-Evi-Test` ou
  sessão com prefixo de teste) não criam lembretes: `create_reminder` responde "Lembrete
  de teste não agendado" via `turn_log.current_is_test()`; a simulação usa sessões
  normais (`telegram-<chat>`). `created_from` vem de `turn_log.current_channel()`
  (fallback `api`); sem `TELEGRAM_CHAT_ID` a tool recusa criar.

## Out of scope

Ver `proposal.md`.

## As-built (2026-10-10)

- Recorrência sem `dateutil` (aritmética de datas locais + `anchor_day` para o mensal).
- `snooze_until` adia só uma ocorrência; "feito" em recorrente confirma só a do dia;
  `cancel_reminder` encerra a série. Status `failed` quando o Telegram não está configurado.
- `reminder_fires` registra cada ocorrência (estatística correta para recorrentes).
- `finish_fired` protegido por `status='firing'`, com retentativa em memória sem reenvio.
- Turnos de teste não criam lembretes; `created_from` vem do canal real do turno;
  `create_reminder` só por pedido explícito (regra no `AGENTS.md`).
- O lifespan agora também para o poller do Telegram no shutdown.
- Passos `clock` do runner da simulação afirmam mensagens proativas (`SIM-REM-01..05`).
- Achado lateral corrigido no mesmo change: com `EVI_GEMINI_THINKING_BUDGET=0` o modelo
  passava o número do briefing como id; `confirm/dismiss_commitments` ganharam
  `briefing_items`, resolvidos no código pelo snapshot `morning_briefing`.
