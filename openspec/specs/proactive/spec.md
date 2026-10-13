# proactive Specification

## Purpose
TBD - created by archiving change evi-morning-briefing. Update Purpose after archive.
## Requirements
### Requirement: Morning briefing delivered without being asked
When `EVI_BRIEFING_ENABLED=true`, `POST /jobs/briefing` SHALL assemble a briefing and deliver it to `TELEGRAM_CHAT_ID`. The briefing SHALL contain, in this order: today's calendar events (in `EVI_TIMEZONE`, overlapping events flagged as conflicts), open Google Tasks due today or overdue, up to `EVI_BRIEFING_EMAIL_MAX` inbox emails that look actionable, and pending WhatsApp commitments. Items SHALL be numbered continuously across sections (1..N). Each section SHALL be capped (events 8, tasks 5, emails 3, WhatsApp 5) with a trailing `+N` when truncated. Assembly SHALL NOT call an LLM.

#### Scenario: SCN-BRIEF-01
- **GIVEN** Windmill fixtures with 2 events today, 1 overdue task, 4 inbox emails (2 promotional) and 1 pending commitment
- **WHEN** the briefing is assembled
- **THEN** it lists 2 events, 1 task, 2 emails and 1 commitment numbered 1..6, and no LLM client is constructed

#### Scenario: SCN-BRIEF-01b
- **GIVEN** every source returns empty
- **WHEN** the briefing is assembled
- **THEN** a single "dia livre" line is delivered — the briefing is never silently skipped

### Requirement: A failing source degrades one section, not the briefing
Each source SHALL be collected independently. When a source fails (OAuth expired, Windmill unreachable, timeout), its section SHALL render as `⚠ <fonte> indisponível — <motivo>` using the `ToolResult.reason`/`detail`, and the remaining sections SHALL be delivered.

#### Scenario: SCN-BRIEF-02
- **GIVEN** the Gmail source returns an OAuth error and the other sources succeed
- **WHEN** the briefing is assembled
- **THEN** the email section shows the warning with the reason and the calendar, tasks and WhatsApp sections are complete

### Requirement: Email selection heuristic
The email section SHALL exclude messages labelled `CATEGORY_PROMOTIONS`, `CATEGORY_SOCIAL` or `CATEGORY_UPDATES` and senders matching `no-?reply`, and SHALL show the most recent remaining messages first. When labels are unavailable, only the sender filter applies.

#### Scenario: SCN-BRIEF-03
- **WHEN** the inbox contains a promotion, a `noreply@` notification and two personal emails
- **THEN** only the two personal emails appear

### Requirement: One briefing per day and kind
Each delivery SHALL be recorded in `briefing_log` with `(day, kind)` unique, `day` computed with `now_local()`. A second request for the same `(day, kind)` after a successful delivery SHALL return `{"status": "already_sent"}` unless `force=true`. A failed delivery (`ok=false`) SHALL NOT block a retry. With `EVI_BRIEFING_ENABLED=false` the endpoint SHALL return `{"status": "disabled"}` and send nothing. The endpoint SHALL require the API key like every other mutating route.

#### Scenario: SCN-BRIEF-04
- **WHEN** `/jobs/briefing` is called twice on the same local day with `kind=morning`
- **THEN** exactly one Telegram message is sent and the second call returns `already_sent`
- **AND** a call without a valid API key returns 401

### Requirement: Replying to the briefing acts on its items
After a successful delivery, the briefing text SHALL be appended as an assistant message to the session memory of `telegram-<TELEGRAM_CHAT_ID>`, and a tool snapshot named `morning_briefing` SHALL be stored with `{"kind", "day", "refs": {"<n>": "<kind>:<id>"}}` where each ref carries the commitment id, Gmail message id, task id or calendar event id. The bootstrap instructions SHALL tell the model to resolve item numbers from that snapshot.

#### Scenario: SCN-BRIEF-05
- **GIVEN** a delivered briefing where item 4 is pending commitment id 12
- **WHEN** the next Telegram turn is assembled
- **THEN** the session history ends with the briefing and the SESSION TOOL SNAPSHOTS block maps `"4": "commitment:12"`

### Requirement: Briefing is scheduled from Windmill
A Windmill script `f/integrations/briefing` SHALL POST `/jobs/briefing` with the API key, following the `heartbeat` script's envelope (`{"status": "ok"|"error", ...}`). The schedule itself lives in Windmill and SHALL be documented in `windmill/README.md`, including the optional evening run with `kind=evening`.

#### Scenario: SCN-BRIEF-06
- **WHEN** the script runs against a live stack
- **THEN** it returns `{"status": "ok", ...}` and the briefing arrives on Telegram

### Requirement: Briefing engagement is measured
`/metrics` SHALL expose `evi_briefing_sent_total{kind}` and `evi_briefing_replied_total{kind}`. A reply is a user message in the briefing's Telegram session within 3 hours of delivery, counted at most once per briefing.

#### Scenario: SCN-BRIEF-08
- **WHEN** a briefing is delivered and the user writes twice within 3 hours
- **THEN** `sent` increments by 1 and `replied` increments by 1

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
After delivery, the reminder text SHALL be appended to the Telegram session history (memory and persisted messages) and a tool snapshot `last_reminder` with its id SHALL be stored. "feito" SHALL complete it and "adia 1h" / "adia para amanhã" SHALL snooze it through `complete_reminder` / `snooze_reminder`, resolved by the LLM from that snapshot. Snoozing a recurring reminder SHALL affect only that occurrence (the series keeps its schedule); "feito" on a recurring reminder SHALL confirm only that occurrence; `cancel_reminder` stops the series.

#### Scenario: SCN-REM-04
- **GIVEN** a reminder just delivered
- **WHEN** the user answers "adia 1h"
- **THEN** the reminder is `pending` with `due_at` one hour after the reply, and it is delivered again when the clock reaches that time

### Requirement: Reminder punctuality is measured
Each delivery SHALL record `fired_at` and `drift_s`. `/metrics` SHALL expose `evi_reminders_fired_total{late}` and `evi_reminder_drift_seconds`, and the weekly usage report SHALL show reminders created, fired, late, and the p95 drift.

#### Scenario: SCN-REM-06
- **WHEN** the weekly report runs over a week with 10 fired reminders, one of them 4 minutes late
- **THEN** it shows 10 fired, 0 late and the p95 drift

### Requirement: Briefing groups WhatsApp items by what the user must do
When `EVI_REPLY_DEBTS_ENABLED=true`, the briefing's WhatsApp section SHALL list, in this order and continuously numbered with the rest of the briefing: conversations waiting for the user's reply (contact, age, wrapped preview), the user's pending promises, and pending dated commitments. Each item SHALL carry a ref (`reply_debt:<jid>` or `commitment:<id>`) in the `morning_briefing` snapshot.

#### Scenario: SCN-DEBT-06
- **GIVEN** one reply debt, one promise and one dated commitment
- **WHEN** the briefing is assembled
- **THEN** the WhatsApp section shows three labelled groups with one item each, and the snapshot maps each number to its ref

### Requirement: No per-capture WhatsApp notifications
When `EVI_REPLY_DEBTS_ENABLED=true`, capturing a commitment or promise SHALL NOT send a notification; the briefing is the only delivery channel for these items.

#### Scenario: SCN-DEBT-07
- **WHEN** a contact proposes "vôlei amanhã às 19h"
- **THEN** a dated commitment is stored and no Telegram or WhatsApp message is sent at capture time

### Requirement: Action rate per item type is reported
The weekly usage report SHALL show, per type (reply debt, promise, dated commitment), how many items were shown and the share the user acted on (replied, done or confirmed).

#### Scenario: SCN-DEBT-08
- **WHEN** the report runs over a week with 10 reply debts of which 4 were answered
- **THEN** it shows 10 shown and 40% acted for reply debts

### Requirement: The Monday briefing asks for missing contact names
The Monday briefing SHALL list at most 3 direct conversations with at least 3 messages in the last 14 days and no name, each with the number, an excerpt of the contact's last message (wrapped as external data) and, when available, a suggested name. Replying "nomeia N <nome>" SHALL set that name as user-defined; "ignora N" SHALL stop asking about it for 90 days.

#### Scenario: SCN-NAME-05
- **GIVEN** an unnamed contact with 5 messages this week
- **WHEN** the Monday briefing is sent and the user replies "nomeia 1 Hollmann"
- **THEN** the contact is named "Hollmann" and is not asked about again

### Requirement: Suggested names need literal evidence
A suggested name SHALL come from the structured LLM task `CONTACT_NAME_HINT` only when the contact introduced or signed themselves, and SHALL be discarded unless its evidence appears literally in one of the contact's messages. A suggestion SHALL never be stored without the user's confirmation.

#### Scenario: SCN-NAME-06
- **GIVEN** the contact wrote "Abs, Pedro" and the LLM suggests "Paulo"
- **WHEN** the suggestion is validated
- **THEN** it is discarded

### Requirement: What the user reads carries no model markers
Every message sent to the user (briefing, lists, direct replies) SHALL be rendered from data without `wrap_external` markers, with third-party text escaped for the Telegram format in use; the version stored in the session history that later reaches an LLM SHALL keep third-party text wrapped as external data. A residual marker found at send time SHALL be removed and logged as a soft failure.

#### Scenario: SCN-UX-02
- **GIVEN** a briefing with a calendar event titled "entrega lote 2 <isla>"
- **WHEN** it is sent to Telegram and stored in the session
- **THEN** the user sees the title escaped and without `«externo`, and the stored session text has it wrapped as external data

### Requirement: Briefing items read person-first in one line
Briefing items SHALL be one line each with the person (contact or sender name) first and emphasized, then the subject, then short metadata (age, due date); a truncated section SHALL say what kind of items are hidden and which reply lists them; the briefing SHALL end with the reply commands valid for the items shown. If Telegram rejects the formatting, the same content SHALL be resent as plain text.

#### Scenario: SCN-UX-03
- **GIVEN** a pending promise "Mandar a modelagem" to Eliana due Friday and 11 more promises
- **WHEN** the morning briefing is assembled
- **THEN** its line reads with "Eliana" first, the task and "até sex", and the section ends with "+11 promessas" and the command to list them

### Requirement: Long briefings collapse low-priority sections
When the assembled briefing would exceed about 25 lines, lower-priority sections SHALL be replaced by a one-line summary with the command that lists them.

#### Scenario: SCN-UX-04
- **GIVEN** 8 events, 5 tasks, 9 emails and 15 WhatsApp items
- **WHEN** the briefing is assembled
- **THEN** it has at most about 25 lines and each collapsed section shows its count and command

