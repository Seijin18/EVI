# n8n integrations

## ADDED Requirements

### Requirement: Calendar scheduling
The tool `schedule_event` SHALL POST JSON to `N8N_WEBHOOK_URL`, trying `webhook-test` first then production path.

#### Scenario: SCN-CAL-01
- **WHEN** n8n returns 200 (or mock in tests)
- **THEN** tool returns success message

### Requirement: Task creation
The tool `create_task` SHALL POST to `N8N_TASKS_WEBHOOK_URL`.

### Requirement: Email
The tool `summarize_inbox` SHALL POST to `N8N_EMAIL_WEBHOOK_URL`.

Workflow exports live under `n8n/workflows/` (configure in n8n UI).
