#!/usr/bin/env bash
# Container smoke — asserts what only exists once the system is built and wired.
#
# Catches the class of defect the unit suite cannot see, e.g.:
#   - dev_bridge._REPO_ROOT resolving to "/" inside the image (six weeks unnoticed,
#     feature since removed — the check stays)
#   - QDRANT__SERVICE__API_KEY="" turning on auth and 401ing everything, while
#     /health still reported "ok"
#
# Runs under its own compose project, so it never touches a running dev stack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT="evi-smoke"
SERVICES="postgres qdrant agent-api"
DATA_SERVICES="postgres qdrant evolution-api neo4j"
CORE_TOOLS="schedule_event,list_calendar_events,summarize_inbox,list_pending_commitments,confirm_commitments"
API="http://127.0.0.1:18002"

FAILED=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAILED=1; }

# --env-file /dev/null: Compose reads ./.env for ${VAR} interpolation too, which
# is a SEPARATE channel from a service's `env_file`. Resetting env_file alone
# still let WINDMILL_TOKEN and NEO4J_PASSWORD through, because the base file
# interpolates them. This closes the fourth and last way out of the project.
dc() {
  docker compose -p "$PROJECT" --env-file /dev/null \
    -f docker-compose.yml -f docker-compose.smoke.yml "$@"
}

cleanup() {
  echo "==> Derrubando stack de smoke..."
  dc down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# An isolated env: no .env secrets, no host volumes worth clobbering, and the
# published ports shifted so a running dev stack keeps its own.
export POSTGRES_DB=evidb POSTGRES_USER=evi POSTGRES_PASSWORD=smoke
export EVI_LLM_PROVIDER=ollama EVI_EMBED_PROVIDER=ollama
export QDRANT_URL=http://qdrant:6333
export OLLAMA_BASE_URL=http://127.0.0.1:1
export EVI_TIMEZONE=America/Sao_Paulo
export EVI_CONTACT_MEMORY_DIR=/data/contact_memory
# Explicitly empty: even if the env isolation regresses, the smoke must never
# start a Telegram poller against the real bot (that is what caused the 409s).
export TELEGRAM_MODE= TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID=
export EVI_WHATSAPP_CONTROL_JIDS= EVOLUTION_API_KEY= GEMINI_API_KEY=

# Guard, learned the hard way on 2026-08-12: a bind mount ignores the compose
# project name, so `-p evi-smoke` alone does NOT isolate anything. Running this
# against ./data/postgres while the dev stack held it corrupted the database.
# Refuse to start unless the override really redirected the data volumes.
echo "==> 0/7 Verificando isolamento..."
# Via env var, not a pipe: `python3 - <<'PY'` makes the heredoc stdin, so a
# piped payload would never reach the script.
SMOKE_CONFIG="$(dc config --format json 2>/dev/null || echo '')"
SMOKE_CONFIG="$SMOKE_CONFIG" python3 - <<'PY' || exit 1
import json, os, sys

raw = os.environ.get("SMOKE_CONFIG") or ""
if not raw.strip():
    print("[FAIL] ISOLAMENTO: `docker compose config` não retornou nada — abortando")
    sys.exit(1)
cfg = json.loads(raw)
offenders = []
for name, svc in (cfg.get("services") or {}).items():
    for vol in svc.get("volumes") or []:
        if vol.get("type") != "bind" or vol.get("read_only"):
            continue
        src = vol.get("source", "")
        if "/data/" in src or src.endswith("/data"):
            offenders.append(f"{name}: {src} -> {vol.get('target')}")
# env_file is the third way the base compose reaches outside the project. Do NOT
# check for the `env_file` key: `docker compose config` resolves it into
# `environment` and drops the key, so that check silently always passes — worse
# than no check. Assert the consequence instead: no real credential may appear
# in the smoke's resolved environment.
_SECRETS = (
    "TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "EVOLUTION_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "WINDMILL_TOKEN",
    "EVI_WHATSAPP_CONTROL_JIDS", "TELEGRAM_CHAT_ID", "NEO4J_PASSWORD",
)
for name, svc in (cfg.get("services") or {}).items():
    env = svc.get("environment") or {}
    for key in _SECRETS:
        if (env.get(key) or "").strip():
            offenders.append(f"{name}: {key} tem valor real (o .env de dev vazou)")
    # A live poller would fight the real bot for getUpdates (the 409s of 12/08).
    if (env.get("TELEGRAM_MODE") or "").strip():
        offenders.append(f"{name}: TELEGRAM_MODE={env['TELEGRAM_MODE']!r} iniciaria um poller")

if offenders:
    print("[FAIL] ISOLAMENTO: o smoke alcançaria estado de dev:")
    for o in offenders:
        print(f"         {o}")
    print("       Abortando — docker-compose.smoke.yml deve usar volumes nomeados")
    print("       e `env_file: !reset []`.")
    sys.exit(1)
print("[PASS] sem bind mount de ./data em escrita e sem env_file herdado")
PY

echo "==> 1/7 Build da imagem..."
dc build agent-api >/dev/null
pass "imagem construída a partir de agent/Dockerfile"

echo "==> 2/7 Subindo $SERVICES..."
# --no-deps on agent-api: its depends_on pulls Windmill, which this smoke does
# not assert and which costs ~40s of migrations to become healthy.
if ! dc up -d --wait postgres qdrant >/dev/null 2>&1 \
   || ! dc up -d --wait --no-deps agent-api >/dev/null 2>&1; then
  fail "stack não subiu"
  dc logs --tail 40 agent-api || true
  exit 1
fi
pass "postgres, qdrant e agent-api saudáveis"

PORT="$(dc port agent-api 8000 | awk -F: '{print $NF}')"
API="http://127.0.0.1:${PORT}"

echo "==> 3/7 Endpoints..."
if curl -sf -m 10 "$API/" >/dev/null; then
  pass "GET / responde"
else
  fail "GET / não responde"
fi

HEALTH="$(curl -s -m 20 "$API/health" || echo '{}')"
TOOLS="$(curl -s -m 10 "$API/tools" || echo '{}')"

echo "==> 4/7 Health por check (não só o agregado)..."
HEALTH="$HEALTH" python3 - <<'PY' || FAILED=1
import json, os, sys
sys.path.insert(0, "agent")
from testing.container_checks import check_health_payload

# Windmill and Ollama are deliberately not started (see design.md): reported,
# never fatal. Everything else — postgres, qdrant, graph, contact_memory — is
# asserted strictly, which is where the Qdrant 401 regression lived.
problems = check_health_payload(
    json.loads(os.environ["HEALTH"] or "{}"),
    not_started=("windmill", "ollama"),
)
for p in problems:
    print(f"[FAIL] health: {p}")
if not problems:
    print("[PASS] todos os checks de /health ok (skips tolerados)")
sys.exit(1 if problems else 0)
PY

echo "==> 5/7 Registry de tools dentro da imagem..."
TOOLS="$TOOLS" CORE="$CORE_TOOLS" python3 - <<'PY' || FAILED=1
import json, os, sys
sys.path.insert(0, "agent")
from testing.container_checks import check_tools_payload

expected = os.environ["CORE"].split(",")
problems = check_tools_payload(json.loads(os.environ["TOOLS"] or "{}"), expected=expected)
for p in problems:
    print(f"[FAIL] tools: {p}")
if not problems:
    print("[PASS] tools centrais presentes no registry da imagem")
sys.exit(1 if problems else 0)
PY

echo "==> 6/7 Paths resolvidos em tempo de import (dentro da imagem)..."
dc exec -T agent-api python3 -m testing.container_checks || FAILED=1

echo "==> 7/7 Binds de porta e log de boot..."
CONFIG="$(docker compose config --format json 2>/dev/null || echo '{}')"
CONFIG="$CONFIG" DATA="$DATA_SERVICES" python3 - <<'PY' || FAILED=1
import json, os, sys
sys.path.insert(0, "agent")
from testing.container_checks import check_port_bindings

problems = check_port_bindings(
    json.loads(os.environ["CONFIG"] or "{}"),
    data_services=os.environ["DATA"].split(),
)
for p in problems:
    print(f"[FAIL] ports: {p}")
if not problems:
    print("[PASS] serviços de dados publicam só com host IP")
sys.exit(1 if problems else 0)
PY

LOGS="$(dc logs --no-color agent-api 2>&1 || true)"
LOGS="$LOGS" python3 - <<'PY' || FAILED=1
import os, sys
sys.path.insert(0, "agent")
from testing.container_checks import check_boot_logs

problems = check_boot_logs(os.environ["LOGS"])
for p in problems:
    print(f"[FAIL] boot: {p}")
if not problems:
    print("[PASS] boot sem soft-fail nem traceback")
sys.exit(1 if problems else 0)
PY

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  echo "Container smoke: OK"
else
  echo "Container smoke: FALHOU"
fi
exit "$FAILED"
