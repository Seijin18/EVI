## MODIFIED Requirements

### Requirement: Tasks via Windmill
The tool `create_task` SHALL POST to `WINDMILL_WEBHOOK_TASKS` with `wait_result`, `$res:` gtasks resource, and return created task status when Google Tasks API succeeds.

#### Scenario: SCN-TASK-03
- **WHEN** `create_task` tool runs with valid Windmill env
- **THEN** Windmill job completes and response includes task title

#### Scenario: SCN-TASK-05
- **WHEN** `./scripts/evi-test tasks --live-windmill` runs with configured `WINDMILL_GTASKS_RESOURCE`
- **THEN** response contains `"status":"created"`
