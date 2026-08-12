## ADDED Requirements

### Requirement: Container smoke gates the composed system
CI SHALL run `scripts/evi-container-smoke.sh`, which builds the agent image, brings up `postgres`, `qdrant` and `agent-api` under an isolated compose project, and asserts the properties that only exist once the system is built and wired. It SHALL always tear the stack down, and SHALL NOT touch a developer's running stack or volumes. Because the base compose file bind-mounts `./data`, and a bind mount ignores the compose project name, the smoke SHALL redirect those volumes to named ones AND SHALL refuse to start if any writable bind mount under `./data` survives — an isolation that is asserted, not assumed. The same script SHALL be reachable locally as `./scripts/evi-test container`.

The assertions SHALL include:
- `GET /` and `GET /health` answer, and **every** `/health` check that is not `skipped` reports `ok: true` — the aggregate `status` alone is too coarse. Dependencies the smoke deliberately does not start (Windmill, Ollama) are named explicitly and reported as `[INFO]`, never fatal.
- `GET /tools` lists the whole registry, so a tool that cannot import inside the image fails the build.
- Every module-level path constant resolved from `__file__` at import time exists inside the image and is not `/`. Modules with a known, tracked defect (the dev bridge, BACKLOG #33) are listed as explicit exemptions and printed as `[KNOWN]`, so the exemption is visible rather than silently absent.
- Every published port for a data service in `docker compose config` carries a host IP.
- A clean boot produces no `soft-fail` line and no traceback.

#### Scenario: SCN-CI-02
- **WHEN** `./scripts/evi-container-smoke.sh` runs on a clean checkout
- **THEN** it exits 0 with one `[PASS]` line per assertion, and the stack is removed afterwards even on failure

### Requirement: The smoke catches the regressions that motivated it
The assertion helpers SHALL be pure functions covered by unit tests, so their logic is verified without Docker, and SHALL demonstrably reject the two defects that reached `main` with a green pipeline: a repo-root constant resolving to `/`, and a `/health` payload whose Qdrant check failed while the aggregate still read `ok`.

#### Scenario: SCN-CI-03
- **WHEN** `tests/unit/test_container_checks.py` runs
- **THEN** a path constant of `/` is rejected, and a health payload with `qdrant.ok = false` is rejected even when `status` is `ok`
