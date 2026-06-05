# Design: evi-compose-healthchecks

## Context

Compose uses simple `depends_on` without readiness. Agent spec already has `GET /` (SCN-API-01).

## Goals / Non-Goals

**Goals:** deterministic startup; agent waits for postgres, qdrant, windmill-server healthy.

**Non-Goals:** Ollama on host; health endpoint changes.

## Decisions

1. **Postgres** — `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` (image includes pg_isready)
2. **Qdrant** — HTTP `GET /readyz` on 6333
3. **Windmill** — HTTP `GET /api/version` on internal 8000
4. **Redis** — `redis-cli ping`
5. **Agent-api** — Python urllib to `http://127.0.0.1:8000/` (no curl in slim image)
6. **Evolution** — wait postgres + redis healthy only (no HTTP health in image without extra deps)

## Risks / Trade-offs

- [Slower first boot] → `start_period` 15–30s on postgres/windmill
- [Ollama still external] → document in testing.md; chat may fail until Ollama up
