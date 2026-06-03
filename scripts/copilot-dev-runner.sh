#!/usr/bin/env bash
# Wrapper for GitHub Copilot CLI — use for scaffold/debug, not runtime agent reasoning.
set -euo pipefail

usage() {
  echo "Usage: $0 <explain|scaffold|debug> [args...]"
  echo "  explain <error log file>  — explain Docker/Python errors"
  echo "  scaffold <description>  — generate boilerplate (tests, tools)"
  echo "  debug <description>       — troubleshoot agent issues"
  exit 1
}

if ! command -v copilot >/dev/null 2>&1; then
  echo "copilot CLI not installed. Run: npm install -g @github/copilot-cli"
  exit 1
fi

CMD="${1:-}"
shift || usage

case "$CMD" in
  explain)
    FILE="${1:-}"
    [[ -f "$FILE" ]] || usage
    copilot explain "$(cat "$FILE")"
    ;;
  scaffold)
    DESC="${*:-MCP tool stub}"
    copilot suggest "Scaffold for EVI project: $DESC"
    ;;
  debug)
    DESC="${*:-agent-api failure}"
    copilot suggest "Debug EVI LangGraph agent: $DESC"
    ;;
  *)
    usage
    ;;
esac
