## Why

`GET /` only returns static alive string; ops need dependency-aware health for compose and monitoring.

## What Changes

- `GET /health` with postgres, qdrant, windmill, ollama, graph checks
- `./scripts/evi-test health` (+ `--full` live)
- SCN-API-02

**Out of scope:** Prometheus (next change).
