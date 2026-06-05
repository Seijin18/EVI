## ADDED Requirements

### Requirement: Evolution filter unit tests
The project SHALL include unit tests for `evolution_filter` covering whitelist and dedupe behavior.

#### Scenario: SCN-WA-09
- **WHEN** `pytest tests/unit/test_evolution_filter.py` runs
- **THEN** all tests pass without network
