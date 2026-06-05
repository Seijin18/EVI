#!/usr/bin/env bash
# Run wmill with Node 20+ (windmill/.nvmrc). Avoids nvm↔~/.npmrc prefix conflicts on Pop!_OS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NVM_VERSION="$(cat "$ROOT/windmill/.nvmrc" 2>/dev/null || echo 22)"
NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

# Prefer direct Node binary (no `nvm use` — breaks when ~/.npmrc sets prefix=)
if [ -d "$NVM_DIR/versions/node" ]; then
  best=""
  for ver_dir in "$NVM_DIR/versions/node"/v"${NVM_VERSION}"*; do
    [ -x "$ver_dir/bin/node" ] || continue
    best="$ver_dir/bin"
  done
  if [ -n "$best" ]; then
    export PATH="$best:$PATH"
  fi
fi

# Fallback: nvm with --delete-prefix if node still < 20
if command -v node >/dev/null 2>&1; then
  major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
else
  major=0
fi
if [ "$major" -lt 20 ] && [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  nvm use --delete-prefix "$NVM_VERSION" --silent 2>/dev/null \
    || nvm use "$NVM_VERSION" >/dev/null 2>&1 \
    || true
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node not found. Install Node 20+ (nvm install $NVM_VERSION) or run ./scripts/install-wmill.sh"
  exit 1
fi
major=$(node -p 'process.versions.node.split(".")[0]')
if [ "$major" -lt 20 ]; then
  echo "Node $(node -v) is too old for windmill-cli (needs 20+)."
  exit 1
fi

if ! command -v wmill >/dev/null 2>&1; then
  echo "wmill not in PATH. Run: ./scripts/install-wmill.sh"
  echo "  (or: npm install -g windmill-cli with Node $(node -v))"
  exit 1
fi
exec wmill "$@"
