# Windmill integrations

## Purpose

Code-first orchestration for calendar, tasks, email, and Telegram bridge via Windmill HTTP triggers.

## Requirements

### Requirement: Calendar via Windmill
The tool `schedule_event` SHALL POST to `WINDMILL_WEBHOOK_CALENDAR`.

#### Scenario: SCN-CAL-02
- **WHEN** Windmill script accepts payload
- **THEN** tool returns success message

### Requirement: Tasks via Windmill
The tool `create_task` SHALL POST to `WINDMILL_WEBHOOK_TASKS`.

#### Scenario: SCN-TASK-03
- **WHEN** Windmill tasks webhook accepts payload
- **THEN** tool returns success message

### Requirement: Email via Windmill
The tool `summarize_inbox` SHALL POST to `WINDMILL_WEBHOOK_EMAIL`.

#### Scenario: SCN-EMAIL-02
- **WHEN** Windmill email webhook accepts payload
- **THEN** tool returns summary or success message

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
