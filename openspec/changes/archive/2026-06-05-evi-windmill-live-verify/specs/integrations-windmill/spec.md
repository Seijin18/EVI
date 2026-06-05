## ADDED Requirements

### Requirement: Email live verification
The test harness SHALL support live Windmill verification for Gmail summary.

#### Scenario: SCN-EMAIL-05
- **WHEN** `./scripts/evi-test email --live-windmill` runs with valid `WINDMILL_TOKEN` and `gmail` resource
- **THEN** result text includes non-empty `summary` or `"status":"ok"` from Windmill

## MODIFIED Requirements

### Requirement: Tasks via Windmill
The tool `create_task` SHALL POST to `WINDMILL_WEBHOOK_TASKS` with `wait_result`, `$res:` gtasks resource, and return created task status when Google Tasks API succeeds.

#### Scenario: SCN-TASK-03
- **WHEN** Windmill `create_task` script completes successfully
- **THEN** job result includes `"status":"created"` and a `task_id`

#### Scenario: SCN-TASK-05
- **WHEN** `./scripts/evi-test tasks --live-windmill` runs with configured `WINDMILL_GTASKS_RESOURCE`
- **THEN** response text contains `"status":"created"` or `"status": "created"`
