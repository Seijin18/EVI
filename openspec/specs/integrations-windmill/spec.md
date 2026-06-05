# Windmill integrations

## Purpose

Code-first orchestration for calendar, tasks, email, and Telegram bridge via Windmill HTTP triggers.
## Requirements
### Requirement: Calendar via Windmill
The tool `schedule_event` SHALL POST to `WINDMILL_WEBHOOK_CALENDAR` using `wait_result` and SHALL pass `gcal` as a Windmill resource reference (`$res:u/.../gcal`) and `calendar_id` from `WINDMILL_CALENDAR_ID`.

#### Scenario: SCN-CAL-02
- **WHEN** Windmill script completes successfully
- **THEN** job result includes `"status":"created"` and an `html_link` or `event_id`

#### Scenario: SCN-CAL-03
- **WHEN** `./scripts/evi-test calendar` runs offline
- **THEN** fixture payload validates and tool wiring is correct

#### Scenario: SCN-CAL-04
- **WHEN** `./scripts/evi-test calendar --live-windmill` runs with valid Windmill token and gcal resource
- **THEN** result text indicates created event or reports Windmill error detail

### Requirement: Calendar environment
Agent and compose SHALL expose `WINDMILL_TOKEN`, `WINDMILL_GCAL_RESOURCE`, and `WINDMILL_CALENDAR_ID` for calendar scheduling.

#### Scenario: SCN-CAL-05
- **WHEN** `.env.example` is inspected
- **THEN** Windmill calendar variables are documented with Bearer and calendar ID hints

### Requirement: Tasks via Windmill
The tool `create_task` SHALL POST to `WINDMILL_WEBHOOK_TASKS` with `wait_result`, `$res:` gtasks resource, and return created task status when Google Tasks API succeeds.

#### Scenario: SCN-TASK-03
- **WHEN** Windmill `create_task` script completes successfully
- **THEN** job result includes `"status":"created"` and a `task_id`

#### Scenario: SCN-TASK-05
- **WHEN** `./scripts/evi-test tasks` runs offline
- **THEN** fixture payload validates

### Requirement: Email via Windmill
The tool `summarize_inbox` SHALL POST to `WINDMILL_WEBHOOK_EMAIL` with `wait_result` and `$res:` gmail resource.

#### Scenario: SCN-EMAIL-02
- **WHEN** Windmill `summarize_inbox` script completes successfully
- **THEN** job result includes non-empty `summary` and `count` >= 0

#### Scenario: SCN-EMAIL-04
- **WHEN** `./scripts/evi-test email` runs offline
- **THEN** tool returns without Windmill network error

### Requirement: Telegram bridge
Windmill script `telegram_to_evi` SHALL forward updates to `POST /webhooks/telegram`.

#### Scenario: SCN-TG-03
- **WHEN** Telegram update hits Windmill trigger
- **THEN** agent receives forwarded payload at `/webhooks/telegram`

### Requirement: Versioned scripts
Integration scripts MUST live under `windmill/f/integrations/` and sync via `wmill sync`.

#### Scenario: SCN-WM-01
- **WHEN** repository Windmill folder is inspected
- **THEN** calendar, tasks, email, and telegram scripts are present

### Requirement: No n8n webhooks
Agents MUST NOT use `N8N_*` URLs; n8n is removed from docker-compose.

#### Scenario: SCN-DEP-02
- **WHEN** agent tools load webhook configuration
- **THEN** only `WINDMILL_WEBHOOK_*` variables are referenced

