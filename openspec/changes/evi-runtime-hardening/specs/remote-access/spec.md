## ADDED Requirements

### Requirement: All mutating routes gated by API key
When `EVI_API_KEY` is set, every route that mutates state or invokes the agent SHALL require a matching `X-Api-Key` header: `/chat`, `/run-task`, `/reset`, `/note`, `/insight`, `/tools`, `/jobs/*` and both webhooks. `GET /` and `GET /health` SHALL remain unauthenticated so the container healthcheck and scrapers keep working.

#### Scenario: SCN-AUTH-02
- **WHEN** `POST /note`, `POST /insight`, `POST /reset` or `GET /tools` is called without a valid key while `EVI_API_KEY` is set
- **THEN** HTTP 401 is returned

### Requirement: Optional startup enforcement of API key
The system SHALL support `EVI_REQUIRE_API_KEY` (default `false`). When `true` and `EVI_API_KEY` is empty, startup SHALL fail with an explicit error instead of serving unauthenticated routes.

#### Scenario: SCN-AUTH-03
- **WHEN** `EVI_REQUIRE_API_KEY=true` and `EVI_API_KEY` is empty at startup
- **THEN** the application refuses to start and logs the missing-key reason

### Requirement: Data services not published to the LAN
Compose SHALL bind Postgres, Qdrant, Evolution API and Neo4j to `127.0.0.1`, and Qdrant SHALL require `QDRANT__SERVICE__API_KEY`. Only `agent-api` and `windmill-server` may publish on all interfaces.

#### Scenario: SCN-OPS-04
- **WHEN** `docker compose config` is inspected
- **THEN** postgres, qdrant, evolution-api and neo4j published ports carry host IP `127.0.0.1`
