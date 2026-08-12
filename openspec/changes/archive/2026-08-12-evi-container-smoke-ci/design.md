## Design

### Shape

`scripts/evi-container-smoke.sh` is the single implementation; CI and
`./scripts/evi-test container` both call it. Duplicating the assertions into a
Python runner would let the two drift, which is the failure mode that produced
the drift between `agent/Dockerfile` and `requirements-dev.txt` in the first
place.

The script is `set -euo pipefail`, prints one `[PASS]`/`[FAIL] <check>` line per
assertion in the same shape as `_result` in `agent/testing/cli.py`, and exits
non-zero on the first failure. It always tears the stack down in a `trap`, using
a dedicated project name (`-p evi-smoke`) so it never touches a running dev
stack or its volumes.

### Which services come up

`postgres`, `qdrant`, `agent-api`. Not Windmill: it takes ~40s to become healthy,
adds a second DB migration, and nothing this smoke asserts depends on it —
`/health` reports Windmill as a check but the assertion tolerates `skipped`.
Not Evolution or Redis for the same reason. Keeping the set small is what makes
this affordable enough to run on every push.

### The import-time path assertion

The generic form of the dev-bridge bug is: *a module computes a path from
`__file__` at import time, and that path is only correct outside the container.*

The check runs inside the built image:

```
for each module-level constant whose value is a Path and whose name ends in _ROOT
or _DIR:  the resolved path must exist AND must not be "/"
```

`/` is the specific tell — `parents[N]` overshooting the image root produces
exactly that, and nothing legitimately roots at `/`. Anything under `/app`,
`/workspace`, `/logs`, `/data` passes. This is deliberately a shape check, not a
list of known-bad modules: a new module that repeats the mistake fails without
anyone remembering to add it.

Pure helpers (`resolve_repo_paths`, `assert_health_payload`,
`assert_ports_bound`) live in `agent/testing/container_checks.py` so they are
unit-testable without Docker; the shell script shells into the container to run
them and interprets the exit code.

### Health assertion is per-check, not aggregate

`run_health_checks` returns `ok` when *any* evaluated check passes and none fail
hard. The Qdrant regression proved the aggregate is too coarse: it read `ok`
while Qdrant 401'd. The smoke asserts every check that is not `skipped (...)` has
`ok: true`, and prints the offending check names on failure.

### CI cost

A separate `container` job, `needs: []` so it runs in parallel with `smoke`.
The image build dominates (~3-4 min cold). Docker layer caching via
`docker/build-push-action` with a GHA cache is deliberately **not** added here —
it is a second thing to debug, and the job is already off the critical path for
unit feedback. If the wall time becomes a problem, caching is a follow-up.

## Out of scope

- **Fixing the dev bridge** so it passes (#33). This change asserts the
  invariant; it does not decide who satisfies it. Until #33 lands, the dev-bridge
  modules are the known exception and the check is scoped to not fail the build
  on them — recorded explicitly in the script with the issue reference, so the
  exemption is visible rather than silently absent.
- **A full E2E in CI** (Windmill, Evolution, Ollama, real LLM). Needs
  credentials and minutes; the live harnesses already cover it on demand.
- **Docker layer caching**, per above.
- **Running the unit suite inside the container.** It passes on the host runner
  already; re-running it in the image would double the slowest job for no new
  signal, since what differs is wiring, not logic.
