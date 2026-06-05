## MODIFIED Requirements

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
