#!/usr/bin/env bash
# Run wmill with Node 20+ (uses nvm + windmill/.nvmrc when default node is 18).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  nvm use "$(cat "$ROOT/windmill/.nvmrc" 2>/dev/null || echo 22)" >/dev/null 2>&1 || true
fi
if ! command -v wmill >/dev/null 2>&1; then
  echo "wmill not in PATH. Run: ./scripts/install-wmill.sh"
  exit 1
fi
exec wmill "$@"
