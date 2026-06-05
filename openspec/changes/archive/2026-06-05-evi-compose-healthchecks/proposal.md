# Proposal: evi-compose-healthchecks

## Why

`docker compose up` starts agent-api before Postgres/Qdrant/Windmill are ready, causing flaky smoke tests and webhook races on 16 GB hosts.

## What Changes

- Healthchecks on `postgres`, `qdrant`, `windmill-server`, `redis`, `agent-api`
- `depends_on` with `condition: service_healthy` for `agent-api`, `windmill-worker`, `evolution-api`
- Boot order note in `docs/testing.md`

## Capabilities

### Modified Capabilities

- `testing`: ADD compose boot-order scenario

## Impact

- `docker-compose.yml`, `docs/testing.md`

## Out of scope

Ollama container, Prometheus, GitHub CI, new services.
