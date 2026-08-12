## Why

Product priority is productivity + remote access; both are currently unsafe to run
unattended. `app_state.memory` is a single process-wide `BoundedMemory`, so two
sessions (Telegram, WhatsApp control JID, `/chat`) that run concurrently in FastAPI's
threadpool can read each other's history. `EVI_API_KEY` is empty and four endpoints
never had a `Depends(verify_api_key)` at all. `graph.py` builds the CALENDAR LOOKUP
TABLE — which the system prompt orders the model to trust verbatim — from naive
`datetime.now()` in a UTC container, so every evening in `America/Sao_Paulo` the
agent is confidently one day ahead. Compose publishes Postgres, Qdrant (no auth),
Evolution and Neo4j on `0.0.0.0`, and the image installs LangChain unpinned with
`uvicorn --reload`. None of this is new feature work; it is the reliability floor
that everything after Etapa 11 depends on.

## What Changes

- **Session isolation**: replace the global `BoundedMemory` with a keyed registry
  (`services/session_memory.py`, bounded LRU over `session_id`). `_chat_impl`,
  `_reset_session` and `_compact_session` operate on the session's own buffer.
  `session_lane` keeps serializing same-session turns; different sessions no longer
  share state.
- **Auth closes**: `Depends(verify_api_key)` on `/note`, `/insight`, `/reset` and
  `/tools`. New `EVI_REQUIRE_API_KEY` (default `false`) makes an empty `EVI_API_KEY`
  a startup failure instead of silent open access. `GET /` and `GET /health` stay
  unauthenticated for the Docker healthcheck and Prometheus.
- **Network surface**: compose binds Postgres, Qdrant, Evolution and Neo4j to
  `127.0.0.1`; Qdrant gains `QDRANT__SERVICE__API_KEY`. Only `agent-api` and
  `windmill-server` keep host-reachable ports.
- **Timezone**: `_calendar_block()` and `iso_event_range()` use
  `ZoneInfo(EVI_TIMEZONE)`, matching the fix already applied to `daily_summary.py`
  and `telegram_schedule.py`. `TZ` is set on `agent-api` as defence in depth.
- **Reproducible image**: pin every dependency in `agent/requirements.txt` (single
  source, `requirements-dev.txt` references it), drop `--reload` from `CMD`.
- **Thread-safe background LLM**: `build_background_llm` stops mutating
  `os.environ`; provider selection becomes an explicit argument to `build_llm`.
- **Failure visibility**: the 35 `except Exception: pass` sites log through one
  `services/soft_fail.py` helper. Behaviour is unchanged — failures stay non-fatal —
  but they stop being invisible.

## Impact

`agent/main.py`, `agent/memory.py`, `agent/services/session_memory.py` (new),
`agent/services/soft_fail.py` (new), `agent/llm.py`, `agent/graph.py`,
`agent/tools/calendar_time.py`, `agent/auth.py`, `agent/Dockerfile`,
`agent/requirements.txt` (new), `docker-compose.yml`, `.env.example`,
`agent/testing/cli.py` (`evi-test sessions`), `tests/unit/test_session_memory.py`,
`test_auth_required.py`, `test_calendar_block_tz.py` (new).
Specs: `agent-api`, `remote-access`, `providers`, `testing`.
