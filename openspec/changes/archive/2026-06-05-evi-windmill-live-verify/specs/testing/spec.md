## ADDED Requirements

### Requirement: Windmill live traceability
docs/testing.md SHALL map Windmill live scenarios to evi-test commands.

#### Scenario: SCN-EMAIL-05 trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-EMAIL-05 maps to `./scripts/evi-test email --live-windmill`

#### Scenario: SCN-TASK-05 trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-TASK-05 maps to `./scripts/evi-test tasks --live-windmill`
