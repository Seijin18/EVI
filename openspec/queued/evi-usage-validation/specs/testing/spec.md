## ADDED Requirements

### Requirement: Every user turn is recorded with structured tool outcomes
Each `/chat` turn SHALL be recorded in `turn_log` with channel, user text, truncated reply, latency, LLM call count, error, and the tools called with `ok` and `reason` taken from `ToolResult` (or `ok: null` for tools without a structured result). Recording SHALL run under `soft_fail` and SHALL NOT affect the reply.

#### Scenario: SCN-USE-01
- **WHEN** a turn calls `schedule_event` and Windmill returns an OAuth error
- **THEN** the turn row has `tools = [{"name": "schedule_event", "ok": false, "reason": "oauth", ...}]`
- **AND** a database error while recording still delivers the reply

### Requirement: Test traffic never counts as real use
Turns whose `session_id` starts with `evi-test`, `test-`, `health-check` or `tg-digest-verify`, or that carry `X-Evi-Test: 1`, SHALL be recorded with `is_test=true` and excluded from every KPI. `scripts/evi-cleanup-test-data` SHALL list test rows in production tables and delete them only with `--apply`.

#### Scenario: SCN-USE-02
- **WHEN** `./scripts/evi-test smoke` runs against the live stack
- **THEN** its turns are `is_test=true` and the weekly KPIs are unchanged

### Requirement: Explicit feedback on the last turn
`/bom` and `/ruim [motivo]` SHALL set `feedback` (and `feedback_note`) on the latest non-command turn of the same session and reply with a one-line acknowledgement.

#### Scenario: SCN-USE-03
- **WHEN** the user sends `/ruim marcou o dia errado` after a scheduling turn
- **THEN** that turn has `feedback='ruim'` and `feedback_note='marcou o dia errado'`

### Requirement: Implicit outcome signals
A nightly idempotent job SHALL mark each turn with `tool_failed`, `correction`, `rephrase` and `cant_do` per the rules in the design. A turn succeeds when it has no failure signal and no `ruim` feedback.

#### Scenario: SCN-USE-04
- **GIVEN** turn A "Você consegue listar meus compromissos?" followed within 3 minutes by turn B "Listar compromissos" in the same session
- **WHEN** the job runs
- **THEN** A is marked `rephrase`
- **AND** a turn followed by "Esse número na verdade é de Fulana" is marked `correction`

### Requirement: Weekly real-use report
`POST /jobs/usage-report` SHALL compute, for the previous ISO week and excluding test traffic: active days, turns per channel, per-turn success rate, failures by tool and reason, correction/rephrase rate, latency p50/p95, LLM calls per turn, commitment confirm/dismiss counts and probe failures; each with deltas against the previous week and the baseline. It SHALL write `EVI_WORKSPACE/reports/usage-YYYY-Www.md`, list up to 5 turns to review with their ids, and send a summary of at most 10 lines to the user's Telegram. `/metrics` SHALL expose `evi_turns_total{channel,outcome}`.

#### Scenario: SCN-USE-05
- **WHEN** the report runs over a seeded week with 10 real turns (2 corrected) and 5 test turns
- **THEN** it reports 10 turns, 80% success, and lists the 2 corrected turns for review

### Requirement: Daily read-only production probe
`POST /jobs/probe` SHALL call the production integration path for today's events, one task, one inbox message and Telegram `getMe`, without the LLM and without any write operation, record each check in `probe_log`, and notify the user at most once per day per failing check with its reason.

#### Scenario: SCN-USE-06
- **WHEN** the Gmail check fails with `reason=oauth` on two probe runs in the same day
- **THEN** exactly one Telegram warning is sent, naming Gmail and the reconnect path

### Requirement: Real failures become simulation scenarios
`evi-sim promote <turn_id>` SHALL write an anonymized scenario draft to `tests/sim/scenarios/from-usage/` containing the turn's context and an `expect` marked TODO; contact names, phone numbers and email addresses SHALL be replaced consistently with fictitious values. The simulation runner SHALL refuse to run a scenario whose `expect` is marked TODO.

#### Scenario: SCN-USE-07
- **WHEN** a turn mentioning "5511955550123" and "Fulana Exemplo" is promoted
- **THEN** the YAML contains neither value and the runner rejects it until `expect` is filled

### Requirement: New inbound payload shapes are captured structurally
The Evolution webhook SHALL compute a signature of each payload's key paths and, for a signature not seen before, store the payload with every text value replaced under `data/payload_shapes/`. The weekly report SHALL list new signatures.

#### Scenario: SCN-USE-08
- **WHEN** a webhook arrives with a previously unseen key structure
- **THEN** one file is written whose values contain none of the original text
