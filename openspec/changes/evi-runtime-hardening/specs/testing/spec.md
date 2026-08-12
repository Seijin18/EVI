## ADDED Requirements

### Requirement: Session isolation harness
The project SHALL provide `./scripts/evi-test sessions`, verifying offline that two interleaved `session_id` values do not share bounded conversation memory.

#### Scenario: SCN-TEST-11
- **WHEN** `./scripts/evi-test sessions` runs without Docker
- **THEN** each session's assembled message list contains only its own turns, and the command exits non-zero if any cross-session message is observed
