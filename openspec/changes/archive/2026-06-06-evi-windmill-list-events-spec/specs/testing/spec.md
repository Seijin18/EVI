## ADDED Requirements

### Requirement: Calendar list events live harness
The project SHALL provide `./scripts/evi-test calendar-list --live-windmill` for SCN-CAL-06 live verification.

#### Scenario: SCN-CAL-06 live
- **WHEN** `./scripts/evi-test calendar-list --live-windmill` runs with Windmill and gcal OAuth configured
- **THEN** `list_calendar_events` returns upcoming events or an empty-list message without failure prefix
