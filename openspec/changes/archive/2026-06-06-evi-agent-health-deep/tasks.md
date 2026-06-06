## 1. Health endpoint

- [x] 1.1 Add services/health.py and GET /health
  - Files: `agent/services/health.py`, `agent/main.py`
  - Verify: `python3 tests/unit/test_health.py`

- [x] 1.2 evi-test health + spec
  - Files: `agent/testing/cli.py`, `openspec/specs/agent-api/spec.md`, `docs/testing.md`
  - Verify: `./scripts/evi-test health && ./scripts/evi-test smoke`
