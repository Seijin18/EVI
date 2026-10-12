## MODIFIED Requirements

### Requirement: API key
`EVI_API_KEY` SHALL be required: the agent SHALL refuse to start without it unless explicitly running in an offline test mode, and every route except `/` and `/health` SHALL require a matching `X-Api-Key` header.

#### Scenario: SCN-AUTH-01
- **WHEN** protected route is called without matching key
- **THEN** HTTP 401 is returned

#### Scenario: SCN-SEC-05
- **GIVEN** `EVI_API_KEY` is empty and no offline test mode is set
- **WHEN** the agent starts
- **THEN** startup fails with an error naming the missing key

## ADDED Requirements

### Requirement: Services are not published beyond the host by default
Every port published in `docker-compose.yml` SHALL be bound to `127.0.0.1`; access from other machines SHALL go only through a path recorded in the threat model (Tailscale) and SHALL still require authentication.

#### Scenario: SCN-SEC-01
- **WHEN** another machine on the LAN connects to ports 8001 or 8002 of the host
- **THEN** the connection is refused

### Requirement: No default secrets in use
Services SHALL NOT run with the default secrets shipped in examples (`evi-dev-key`, `changeme`, `windmill`), Qdrant SHALL require an API key, and `.env`, `data/` and `logs/` SHALL be readable only by the owner.

#### Scenario: SCN-SEC-04
- **WHEN** `./scripts/evi-security-scan` runs
- **THEN** it reports no default secret in use and no group/world-readable secret or data path
