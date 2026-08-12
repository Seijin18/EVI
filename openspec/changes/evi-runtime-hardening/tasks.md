## 1. Implementation

- [ ] 1.1 Session memory registry
  - SCN-RT-03
  - Files: `agent/services/session_memory.py`, `agent/memory.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_session_memory.py -q`

- [ ] 1.2 Wire `/chat`, reset and compaction to per-session buffers
  - SCN-RT-03, SCN-RESET-01
  - Files: `agent/main.py`
  - Verify: `./scripts/evi-test sessions`

- [ ] 1.3 `evi-test sessions` — two interleaved session ids keep separate history
  - SCN-RT-03, SCN-TEST-11
  - Files: `agent/testing/cli.py`, `tests/unit/test_session_memory.py`
  - Verify: `./scripts/evi-test sessions && ./scripts/evi-test smoke`

- [ ] 1.4 Auth on `/note`, `/insight`, `/reset`, `/tools` + `EVI_REQUIRE_API_KEY`
  - SCN-AUTH-02, SCN-AUTH-03
  - Files: `agent/main.py`, `agent/auth.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_auth_required.py -q`

- [ ] 1.5 Bind data services to `127.0.0.1`; Qdrant API key
  - SCN-OPS-04
  - Files: `docker-compose.yml`, `.env.example`
  - Verify: `docker compose config | grep -E '127\.0\.0\.1|published'` then `./scripts/evi-test health`

- [ ] 1.6 Timezone-aware calendar block and event range
  - SCN-CAL-07
  - Files: `agent/tools/calendar_time.py`, `agent/graph.py`, `docker-compose.yml`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_calendar_block_tz.py -q`

- [ ] 1.7 Pin dependencies; drop `--reload` from `CMD`
  - SCN-OPS-05
  - Files: `agent/requirements.txt`, `agent/Dockerfile`, `requirements-dev.txt`
  - Verify: `docker compose build agent-api && ./scripts/evi-test smoke`

- [ ] 1.8 `build_background_llm` without `os.environ` mutation
  - SCN-PROV-04
  - Files: `agent/llm.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_llm_factory.py -q`

- [ ] 1.9 `soft_fail` helper replacing silent `except Exception: pass`
  - SCN-OPS-06
  - Files: `agent/services/soft_fail.py`, `agent/main.py`, `agent/services/whatsapp_control.py`, `agent/services/contact_filesystem.py`, `agent/services/graph_sync.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q` (no behaviour change) + `grep -rn "except Exception:$" agent/ | wc -l` trends to 0

- [ ] 1.10 Spec deltas
  - Files: `openspec/changes/evi-runtime-hardening/specs/{agent-api,remote-access,providers,integrations-windmill,testing}/spec.md`
  - Verify: `openspec validate evi-runtime-hardening`

## 2. Close-out

- [ ] 2.1 Full gate green
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-test runtime-v3 && ./scripts/evi-test inbox-ux && ruff check agent/ --select E,W,F --ignore E501 && openspec validate --specs`

- [ ] 2.2 Update `Progress.md` (Etapa 12) and `openspec/BACKLOG.md`, then `openspec archive evi-runtime-hardening`
  - Files: `Progress.md`, `openspec/BACKLOG.md`
  - Verify: `openspec list` empty
