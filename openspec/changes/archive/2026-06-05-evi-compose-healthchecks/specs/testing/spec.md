## ADDED Requirements

### Requirement: Compose boot order
docker-compose SHALL define healthchecks for core data services and gate agent-api startup on healthy dependencies.

#### Scenario: SCN-OPS-01
- **WHEN** `docker compose up -d` runs on a clean stack
- **THEN** agent-api starts only after postgres, qdrant, and windmill-server report healthy
