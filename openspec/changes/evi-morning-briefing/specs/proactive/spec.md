## ADDED Requirements

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
After a successful delivery, the briefing text SHALL be appended as an assistant message to the session memory of `telegram-<TELEGRAM_CHAT_ID>`, and a tool snapshot named `morning_briefing` SHALL be stored with `{"items": [{"n": <number>, "ref": {...}}]}` where `ref` carries the commitment id, Gmail message id or calendar event id. The bootstrap instructions SHALL tell the model to resolve item numbers from that snapshot.

#### Scenario: SCN-BRIEF-05
- **GIVEN** a delivered briefing where item 4 is pending commitment id 12
- **WHEN** the next Telegram turn is assembled
- **THEN** the session history ends with the briefing and the SESSION TOOL SNAPSHOTS block maps `4 → {"kind": "commitment", "id": 12}`

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
