## 1. Implementation

- [x] 1.1 Pure assertion helpers (health payload, port bindings, import-time paths)
  - SCN-CI-02
  - Files: `agent/testing/container_checks.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_container_checks.py -q`

- [x] 1.2 `scripts/evi-container-smoke.sh` — build, up, assert, always tear down
  - SCN-CI-02
  - Files: `scripts/evi-container-smoke.sh`
  - Verify: `./scripts/evi-container-smoke.sh` exits 0 against a clean checkout

- [x] 1.3 Prove it catches the two regressions it exists for
  - SCN-CI-03
  - Files: `tests/unit/test_container_checks.py`
  - Verify: helpers reject a `_REPO_ROOT` of `/` and a `/health` payload whose qdrant check is `ok: false`

- [x] 1.4 CI job + local subcommand
  - SCN-CI-02
  - Files: `.github/workflows/ci.yml`, `agent/testing/cli.py`, `docs/testing.md`
  - Verify: `./scripts/evi-test container`

- [x] 1.5 Spec delta
  - Files: `openspec/changes/evi-container-smoke-ci/specs/testing/spec.md`
  - Verify: `openspec validate evi-container-smoke-ci`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-container-smoke.sh && ruff check agent/ --select E,W,F --ignore E501 && openspec validate --specs`

- [x] 2.2 Update `Progress.md` + `openspec/BACKLOG.md`, then `openspec archive evi-container-smoke-ci`
  - Files: `Progress.md`, `openspec/BACKLOG.md`
  - Verify: `openspec list` empty
