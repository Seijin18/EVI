## Why

CI validates unit logic and spec shape; nothing validates the composed system.
Two defects in the last two days lived exactly in that gap and both reached
`main` with a green pipeline:

- **Dev bridge** shipped as Done on 1 Aug. `_REPO_ROOT = parents[2]` resolves to
  `/` inside the image (`WORKDIR /app` + `COPY . .`), and `scripts/` is not in the
  image, so `dev approve` has never once worked in the container. Every test mocks
  the backend, so nothing noticed for six weeks.
- **Qdrant** (12 Aug) — `QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY:-}` passed an
  empty string, which Qdrant reads as "auth on with an empty key" and 401s
  everything. The health check's `< 500` rule reported `"status": "ok"` while RAG
  was dead. Found by starting the stack by hand, not by any test.

Both share a signature: correct in isolation, broken once built and wired. A
container smoke is the cheapest instrument that sees that class at all, and it
gates the dev-bridge decision (#33) — without it there is no way to tell whether
a fix actually worked.

## What Changes

- **`scripts/evi-container-smoke.sh`** — builds the image from
  `agent/Dockerfile`, brings up `postgres` + `qdrant` + `agent-api`, waits for
  health, then asserts what only exists in the composed system:
  - `GET /` and `GET /health` answer, and `/health` reports `status != "down"`
    with **every non-skipped check `ok`** — the aggregate alone would have hidden
    the Qdrant 401, which only showed as `degraded` after the check was fixed.
  - `GET /tools` returns the full registry, so a tool that fails to import in the
    image (missing dep, bad path) fails the build instead of disappearing at runtime.
  - **Paths that modules resolve at import time are inside the image.** Generic
    check: for every module exposing a `_REPO_ROOT`-style constant, the resolved
    path must contain the expected marker file. This is the assertion the dev
    bridge would have failed.
  - Every published port in `docker compose config` for a data service carries a
    host IP, so the localhost binding cannot silently regress.
  - `docker compose logs agent-api` contains no `soft-fail` line and no traceback
    during a clean boot.
- **CI job `container`** — runs the script on `ubuntu-latest`, which already has
  Docker. Kept as a separate job from `smoke` so a slow image build never blocks
  the fast unit feedback, and so its failure is legible on its own.
- **`./scripts/evi-test container`** — the same assertions, for local use before
  pushing.

## Impact

`scripts/evi-container-smoke.sh` (new), `.github/workflows/ci.yml`,
`agent/testing/cli.py`, `docs/testing.md`.
Tests: `tests/unit/test_container_smoke_assertions.py` (the pure assertion
helpers, so the script's logic is itself covered).
Specs: `testing`.

Out of scope: making the dev bridge pass this check — that is #33's decision.
The smoke asserts the invariant; #33 chooses whether the dev bridge satisfies it
or stops existing.
