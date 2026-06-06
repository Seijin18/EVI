## ADDED Requirements

### Requirement: List calendar events via Windmill
The tool `list_calendar_events` SHALL POST to `WINDMILL_WEBHOOK_LIST_EVENTS` with `wait_result`, gcal resource, and return upcoming events.

#### Scenario: SCN-CAL-06
- **WHEN** `list_calendar_events` is invoked with valid Windmill config
- **THEN** result includes event titles and start times or a documented empty list

### Requirement: Google Tasks OAuth resource
Tasks integration SHALL use a Windmill OAuth resource with Google Tasks scope (`gtasks`), documented as distinct from `gcloud` cloud-platform scope.

#### Scenario: SCN-TASK-06
- **WHEN** `windmill/README.md` is inspected
- **THEN** it documents custom `gtasks` resource and `WINDMILL_GTASKS_RESOURCE`
