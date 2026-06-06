## 1. Metrics

- [x] 1.1 services/metrics.py + GET /metrics
  - Files: `agent/services/metrics.py`, `agent/main.py`, `agent/Dockerfile`
  - Verify: `python3 tests/unit/test_metrics.py`

- [x] 1.2 Spec and harness
  - Files: `openspec/specs/testing/spec.md`, `docker-compose.yml`, `.env.example`
  - Verify: `./scripts/evi-test metrics`
