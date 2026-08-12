## 1. Implementation

- [x] 1.1 Reset `env_file` and cut the interpolation channel
  - SCN-CI-04
  - Files: `docker-compose.smoke.yml`, `scripts/evi-container-smoke.sh`
  - Verify: `docker compose ... config` shows no real credential in `agent-api.environment`

- [x] 1.2 Neutralise the channel env so no poller can start
  - SCN-CI-04
  - Files: `scripts/evi-container-smoke.sh`
  - Verify: `docker compose logs agent-api | grep -c 409` does not grow across a smoke run

- [x] 1.3 Rewrite the isolation guard to assert the consequence
  - SCN-CI-04
  - Files: `scripts/evi-container-smoke.sh`
  - Verify: with `env_file: !reset []` removed and a real `.env`, the guard aborts naming the leaked keys

- [x] 1.4 Spec delta
  - Files: `openspec/changes/evi-smoke-isolation-fix/specs/testing/spec.md`
  - Verify: `openspec validate evi-smoke-isolation-fix`

## 2. Close-out

- [x] 2.1 Verification matrix — all three conditions
  - Verify: clean checkout **without** `.env` (the CI condition) → exit 0;
    **with** a real `.env` → exit 0; with the fix reverted → exit 1

- [x] 2.2 Full gate, then archive
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ruff check agent/ --select E,W,F --ignore E501 && openspec validate --specs`
  - Then update `openspec/BACKLOG.md`, `openspec archive evi-smoke-isolation-fix`, and confirm the CI `container` job goes green on the pushed commit.
