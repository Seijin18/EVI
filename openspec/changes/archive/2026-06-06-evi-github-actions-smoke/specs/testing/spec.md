## ADDED Requirements

### Requirement: GitHub Actions offline smoke
The repository SHALL include a CI workflow that runs unit tests and `./scripts/evi-test smoke` without Docker or Ollama.

#### Scenario: SCN-CI-01
- **WHEN** `.github/workflows/ci.yml` runs on push to main
- **THEN** pytest and offline smoke complete successfully
