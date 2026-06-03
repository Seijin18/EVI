#!/usr/bin/env bash
# Install Windmill CLI (wmill) — requires Node.js 20+
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

use_nvm_22() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ -s "$NVM_DIR/nvm.sh" ]; then
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
    if [ -f "$ROOT/windmill/.nvmrc" ]; then
      nvm use "$(cat "$ROOT/windmill/.nvmrc")" >/dev/null
    else
      nvm use 22 >/dev/null 2>&1 || nvm install 22
    fi
  fi
}

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js not found. Install Node 20+ or enable nvm, then re-run."
  exit 1
fi

major=$(node -p 'process.versions.node.split(".")[0]')
if [ "$major" -lt 20 ]; then
  echo "Node $(node -v) is too old (windmill-cli needs 20+)."
  if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    echo "Switching via nvm..."
    use_nvm_22
    major=$(node -p 'process.versions.node.split(".")[0]')
  fi
fi

if [ "$major" -lt 20 ]; then
  echo "Still on Node $(node -v). Run: nvm install 22 && nvm use 22"
  exit 1
fi

npm install -g windmill-cli
wmill --version
echo ""
echo "Next (from repo):"
echo "  1. Windmill UI → Workspace settings → Tokens → create token"
echo "  2. cd ~/Projects/EVI/windmill"
echo "  3. wmill workspace add evi evi http://localhost:8001 --token '<TOKEN>'"
echo "  4. wmill workspace switch evi"
echo "  5. wmill folder add-missing -y && wmill generate-metadata"
echo "  6. wmill sync push"
