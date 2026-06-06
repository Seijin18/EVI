## ADDED Requirements

### Requirement: JSONL log retention
Audit JSONL logs under `EVI_LOG_DIR` SHALL be trimmed to `EVI_LOG_MAX_AGE_DAYS` (default 7) after append operations.

#### Scenario: SCN-OPS-02
- **WHEN** `trim_jsonl` runs on `evolution_webhook.jsonl`
- **THEN** lines older than the configured max age are removed
