## ADDED Requirements

### Requirement: Reminders fire on time from inside the agent
When `EVI_REMINDERS_ENABLED=true`, the `agent-api` SHALL run an in-process loop (default tick 30 s, `EVI_REMINDERS_TICK_SEC`) started and stopped by the application lifespan, which delivers every reminder whose `due_at` has passed to `TELEGRAM_CHAT_ID`. With the flag off no loop SHALL start and the reminder tools SHALL answer that reminders are disabled without storing anything. A failing tick SHALL NOT stop the loop.

#### Scenario: SCN-REM-01
- **GIVEN** the clock at D0 17:00 and the user says "me lembra às 18h de pagar o boleto"
- **WHEN** the clock reaches D0 18:00
- **THEN** within 60 s a Telegram message containing "pagar o boleto" is sent to the user, the reminder is `sent` with `drift_s` < 60, and nothing is sent to third parties

### Requirement: A reminder fires exactly once per occurrence
Due reminders SHALL be claimed atomically (`FOR UPDATE SKIP LOCKED`) before sending, so concurrent ticks or processes never deliver the same occurrence twice. A failed send SHALL return the reminder to `pending` for the next tick. A reminder stuck in `firing` for more than 5 minutes SHALL be returned to `pending`.

#### Scenario: SCN-REM-02
- **WHEN** two ticks claim due reminders at the same time
- **THEN** each reminder id is returned to at most one of them

### Requirement: Recurring reminders keep wall-clock time
Reminders MAY repeat `daily`, `weekdays`, `weekly` or `monthly`. The next occurrence SHALL be computed in `EVI_TIMEZONE` so the local time of day is preserved; a monthly reminder on a day the month lacks SHALL fall on the month's last day. After firing, a recurring reminder SHALL return to `pending` with the next future occurrence.

#### Scenario: SCN-REM-03
- **GIVEN** a daily reminder at 08:00 local that was due 3 days ago while the stack was down
- **WHEN** the loop runs
- **THEN** it fires once marked "atrasado" and its next `due_at` is the next 08:00 local in the future

### Requirement: Late reminders are delivered, never dropped
A reminder delivered more than 5 minutes after `due_at` SHALL carry the mark "atrasado" with the original local time. No pending reminder SHALL be discarded because it is overdue.

#### Scenario: SCN-REM-05
- **GIVEN** a one-off reminder due at D0 18:00
- **WHEN** the clock jumps from D0 17:00 to D0 21:00
- **THEN** the reminder is delivered once with "atrasado" and "18:00"

### Requirement: Replying to a reminder acts on it
After delivery, the reminder text SHALL be appended to the Telegram session history (memory and persisted messages) and a tool snapshot `last_reminder` with its id SHALL be stored. "feito" SHALL complete it and "adia 1h" / "adia para amanhã" SHALL snooze it through `complete_reminder` / `snooze_reminder`, resolved by the LLM from that snapshot.

#### Scenario: SCN-REM-04
- **GIVEN** a reminder just delivered
- **WHEN** the user answers "adia 1h"
- **THEN** the reminder is `pending` with `due_at` one hour after the reply, and it is delivered again when the clock reaches that time

### Requirement: Reminder punctuality is measured
Each delivery SHALL record `fired_at` and `drift_s`. `/metrics` SHALL expose `evi_reminders_fired_total{late}` and `evi_reminder_drift_seconds`, and the weekly usage report SHALL show reminders created, fired, late, and the p95 drift.

#### Scenario: SCN-REM-06
- **WHEN** the weekly report runs over a week with 10 fired reminders, one of them 4 minutes late
- **THEN** it shows 10 fired, 0 late and the p95 drift
