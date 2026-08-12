## 1. Implementation

- [x] 1.1 Session memory registry (+ bounded `session_lane` locks)
  - SCN-RT-03
  - Files: `agent/services/session_memory.py`, `agent/memory.py`, `agent/services/session_lane.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_session_memory.py -q`

- [x] 1.2 Wire `/chat`, `/reset`, `/insight` and compaction to per-session buffers
  - SCN-RT-03, SCN-RESET-01
  - Files: `agent/main.py`
  - Verify: `./scripts/evi-test sessions`

- [x] 1.3 `evi-test sessions` — two interleaved session ids keep separate history
  - SCN-RT-03, SCN-TEST-11
  - Files: `agent/testing/cli.py`, `tests/unit/test_session_memory.py`, `tests/unit/test_chat_invoke.py`, `.github/workflows/ci.yml`, `docs/testing.md`
  - Verify: `./scripts/evi-test sessions && ./scripts/evi-test smoke`

- [x] 1.4 Auth on `/note`, `/insight`, `/reset`, `/tools` + `EVI_REQUIRE_API_KEY`
  - SCN-AUTH-02, SCN-AUTH-03
  - Files: `agent/main.py`, `agent/auth.py`, `.env.example`, `tests/unit/test_auth_required.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_auth_required.py -q`

- [x] 1.5 Bind data services to `127.0.0.1`; Postgres host port → 5433; Qdrant API key
  - SCN-OPS-04
  - Files: `docker-compose.yml`, `.env.example`, `docs/testing.md`
  - Verify: `docker compose config | grep -E '127\.0\.0\.1|published'` then `./scripts/evi-test health`
  - Note: host 5432 is occupied by an unrelated `whatbot-db-1` container; container-internal port stays 5432.

- [x] 1.6 Timezone-aware calendar block and event range
  - SCN-CAL-07
  - Files: `agent/tools/calendar_time.py`, `agent/graph.py`, `docker-compose.yml`, `tests/unit/test_calendar_block_tz.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_calendar_block_tz.py -q`

- [x] 1.7 Pin dependencies; drop `--reload` from `CMD`
  - SCN-OPS-05
  - Files: `agent/requirements.txt`, `agent/Dockerfile`, `requirements-dev.txt`
  - Verify: `docker compose build agent-api && ./scripts/evi-test smoke`

- [x] 1.8 `build_background_llm` without `os.environ` mutation
  - SCN-PROV-04
  - Files: `agent/llm.py`, `agent/services/daily_summary.py`, `agent/services/whatsapp_llm_extract.py`, `agent/services/contact_learning.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_llm_factory.py -q`

- [x] 1.9a `soft_fail` helper + `agent/main.py` (10 silent sites)
  - SCN-OPS-06
  - Files: `agent/services/soft_fail.py`, `agent/main.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q` (no behaviour change)

- [x] 1.9b Silent sites in contact memory and commitment replay
  - SCN-OPS-06
  - Files: `agent/services/contact_filesystem.py` (7), `agent/services/commitment_replay.py` (4)
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`

- [x] 1.9c Remaining silent sites (9 modules, 1–2 each)
  - SCN-OPS-06
  - Files: `agent/tools/contact_tool.py`, `agent/services/telegram_handler.py`, `agent/services/whatsapp_control.py`, `agent/services/session_context.py`, `agent/services/chat_commands.py` (+ `rag_tool`, `whatsapp_processor`, `telegram_audit`, `contact_registry`, `contact_memory_audit`, `contact_learning`, `commitment_capture_notify` — 1 site each)
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q` + `grep -rzoP "except Exception:\s*\n\s*pass" agent/ | wc -l` is 0

- [x] 1.10 Spec deltas
  - Files: `openspec/changes/evi-runtime-hardening/specs/{agent-api,remote-access,providers,integrations-windmill,testing}/spec.md`
  - Verify: `openspec validate evi-runtime-hardening`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-test sessions && ./scripts/evi-test runtime-v3 && ./scripts/evi-test inbox-ux && ruff check agent/ --select E,W,F --ignore E501 && openspec validate --specs`

- [x] 2.2 Update `Progress.md` (Etapa 12) and `openspec/BACKLOG.md`, then `openspec archive evi-runtime-hardening`
  - Files: `Progress.md`, `openspec/BACKLOG.md`
  - Verify: `openspec list` empty
