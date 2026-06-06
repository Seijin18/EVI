## ADDED Requirements

### Requirement: Deep health
The system SHALL expose `GET /health` reporting aggregate `status` (`ok`, `degraded`, or `down`) and per-dependency checks for graph, postgres, qdrant, windmill, and ollama.

#### Scenario: SCN-API-02
- **WHEN** client calls `GET /health`
- **THEN** response status is 200 with `status` and `checks` object
