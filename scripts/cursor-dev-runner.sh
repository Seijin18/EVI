#!/usr/bin/env bash
# Cursor Agent CLI wrapper — plan/apply/review with worktree isolation.
set -euo pipefail

ROOT="${EVI_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

usage() {
  echo "Usage: $0 <plan|apply|review> <description>"
  echo "  plan   — agent --mode=plan --print (no file edits)"
  echo "  apply  — agent -p --worktree --trust --force (edits in worktree)"
  echo "  review — agent -p --print review prompt"
  exit 1
}

CMD="${1:-}"
shift || usage
DESC="${*:-EVI maintenance task}"
[[ -n "$DESC" ]] || usage

if ! command -v agent >/dev/null 2>&1; then
  echo "Cursor Agent CLI not installed. Run: curl https://cursor.com/install -fsS | bash"
  exit 1
fi

TIMEOUT="${EVI_DEV_BRIDGE_TIMEOUT_SEC:-900}"
WORKSPACE="$ROOT"

case "$CMD" in
  plan)
    exec timeout "$TIMEOUT" agent -p --mode=plan --trust --workspace "$WORKSPACE" \
      --output-format text "$DESC"
    ;;
  apply)
    exec timeout "$TIMEOUT" agent -p --worktree --trust --workspace "$WORKSPACE" \
      --output-format text --force "$DESC"
    ;;
  review)
    exec timeout "$TIMEOUT" agent -p --trust --workspace "$WORKSPACE" \
      --output-format text "Review recent EVI changes: $DESC"
    ;;
  *)
    usage
    ;;
esac
