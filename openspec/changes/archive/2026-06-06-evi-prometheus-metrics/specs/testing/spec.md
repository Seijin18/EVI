## ADDED Requirements

### Requirement: Prometheus metrics endpoint
When `EVI_METRICS_ENABLED` is true, agent-api SHALL expose `GET /metrics` with Prometheus text format including HTTP and webhook histograms.

#### Scenario: SCN-OPS-03
- **WHEN** client calls `GET /metrics` with metrics enabled
- **THEN** response includes `evi_http_requests_total` metric family
