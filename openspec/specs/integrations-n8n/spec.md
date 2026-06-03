# n8n integrations (deprecated)

## Purpose

Historical n8n webhooks; orchestration MUST use Windmill instead.

## Requirements

### Requirement: Deprecated
n8n SHALL NOT be used for new deployments; orchestration MUST use Windmill (see integrations-windmill/spec.md).

#### Scenario: SCN-DEP-01
- **WHEN** reading orchestration docs
- **THEN** Windmill is the active integration path

### Requirement: Legacy calendar
The former tool `schedule_event` SHALL NOT rely on `N8N_WEBHOOK_URL` in new deployments.

#### Scenario: SCN-CAL-01
- **WHEN** calendar scheduling is configured
- **THEN** `WINDMILL_WEBHOOK_CALENDAR` is used instead of n8n

### Requirement: Legacy tasks
The former tool `create_task` SHALL NOT rely on `N8N_TASKS_WEBHOOK_URL` in new deployments.

#### Scenario: SCN-TASK-02
- **WHEN** task creation is configured
- **THEN** `WINDMILL_WEBHOOK_TASKS` is used instead of n8n

### Requirement: Legacy email
The former tool `summarize_inbox` SHALL NOT rely on `N8N_EMAIL_WEBHOOK_URL` in new deployments.

#### Scenario: SCN-EMAIL-01
- **WHEN** email summary is configured
- **THEN** `WINDMILL_WEBHOOK_EMAIL` is used instead of n8n
