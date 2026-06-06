## Why

No CI workflow; local smoke only on maintainer machine.

## What Changes

- `.github/workflows/ci.yml`: pytest + `./scripts/evi-test smoke` offline
- SCN-CI-01 in testing spec

**Out of scope:** Docker compose in CI; Ollama; `--full` chat.
