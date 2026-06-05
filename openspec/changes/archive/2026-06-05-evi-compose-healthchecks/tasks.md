# Tasks: evi-compose-healthchecks

## 1. Compose

- [x] 1.1 Add healthchecks to postgres, qdrant, redis, windmill-server, agent-api
  - SCN-OPS-01
  - Files: docker-compose.yml
  - Verify: `docker compose config`

- [x] 1.2 Gate depends_on with service_healthy
  - SCN-OPS-01
  - Files: docker-compose.yml
  - Verify: `docker compose up -d && ./scripts/evi-test smoke`

## 2. Docs

- [x] 2.1 Document boot order and Ollama note
  - SCN-OPS-01
  - Files: docs/testing.md
  - Verify: `openspec validate evi-compose-healthchecks`
