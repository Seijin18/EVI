#!/usr/bin/env bash
# Claude Code CLI wrapper — plan/apply/review for the EVI dev bridge.
set -euo pipefail

ROOT="${EVI_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

usage() {
  echo "Usage: $0 <plan|apply|review> <description>"
  echo "  plan   — claude --permission-mode plan --print (no file edits)"
  echo "  apply  — claude --permission-mode acceptEdits --print (edits on a job branch)"
  echo "  review — claude --print review prompt"
  exit 1
}

CMD="${1:-}"
shift || usage
DESC="${*:-EVI maintenance task}"
[[ -n "$DESC" ]] || usage

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code CLI not installed. See https://code.claude.com/docs"
  exit 1
fi

TIMEOUT="${EVI_DEV_BRIDGE_TIMEOUT_SEC:-900}"

case "$CMD" in
  plan)
    exec timeout "$TIMEOUT" claude -p "$DESC" \
      --permission-mode plan \
      --output-format text
    ;;
  apply)
    BRANCH="dev/job-$(date +%s)"
    git checkout -b "$BRANCH"
    trap 'git checkout - >/dev/null 2>&1 || true' EXIT

    timeout "$TIMEOUT" claude -p "$DESC" \
      --permission-mode acceptEdits \
      --output-format text

    if ! git diff --quiet || ! git diff --cached --quiet; then
      git add -A
      git commit -m "dev-bridge(claude): $DESC" --quiet
      echo "EVI_DEV_BRANCH=$BRANCH"
      echo "EVI_DEV_DIFFSTAT=$(git diff --stat HEAD~1 HEAD | tail -1)"
    else
      echo "EVI_DEV_BRANCH=$BRANCH"
      echo "EVI_DEV_DIFFSTAT=no changes"
    fi
    ;;
  review)
    exec timeout "$TIMEOUT" claude -p "Review recent EVI changes: $DESC" \
      --output-format text
    ;;
  *)
    usage
    ;;
esac
