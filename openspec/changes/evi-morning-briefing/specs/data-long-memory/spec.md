## ADDED Requirements

### Requirement: Heartbeat does not send maintenance notices when the briefing is on
When `EVI_BRIEFING_ENABLED=true`, `run_heartbeat` SHALL NOT send maintenance findings (contacts needing synthesis) to the user's channels; it SHALL log them instead. Unnotified pending commitments are surfaced by the briefing and SHALL NOT be duplicated by the heartbeat.

#### Scenario: SCN-BRIEF-07
- **GIVEN** `EVI_BRIEFING_ENABLED=true`, `EVI_HEARTBEAT_ENABLED=true`, stale contacts and unnotified pending commitments
- **WHEN** `run_heartbeat` runs
- **THEN** no message is sent and the findings are written to the log
- **AND** with `EVI_BRIEFING_ENABLED=false` the previous behaviour is unchanged
