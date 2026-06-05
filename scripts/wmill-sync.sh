#!/usr/bin/env bash
# Fast non-interactive Windmill sync (scripts only, workspace evi)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/windmill"
exec "$ROOT/scripts/wmill.sh" sync push \
  --workspace evi \
  --yes \
  --skip-resources \
  --skip-variables \
  --skip-secrets \
  --skip-flows \
  --skip-apps \
  "$@"
