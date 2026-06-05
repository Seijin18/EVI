## ADDED Requirements

### Requirement: Email live harness
The productivity test harness SHALL invoke `summarize_inbox` when `--live-windmill` is passed to the email feature.

#### Scenario: SCN-EMAIL-05
- **WHEN** `./scripts/evi-test email --live-windmill` runs
- **THEN** `summarize_inbox` is invoked and summary content is validated in the result
