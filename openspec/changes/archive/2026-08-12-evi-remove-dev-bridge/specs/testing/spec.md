## MODIFIED Requirements

### Requirement: E2E checklist
The project SHALL document Docker+Ollama validation steps in docs/testing.md.

#### Scenario: SCN-E2E-02
- **WHEN** offline smoke runs after a change
- **THEN** result is 13/13 PASS or skips documented — the `dev-bridge` entry was removed with the feature it exercised
