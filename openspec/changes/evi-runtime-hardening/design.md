## Design

### Session memory registry

`agent/services/session_memory.py`:

- `get_session_memory(session_id) -> BoundedMemory` backed by an
  `OrderedDict[str, BoundedMemory]` guarded by one `threading.Lock`, capped by
  `EVI_SESSION_MEMORY_MAX` (default 32) with LRU eviction. `max_pairs` stays 8 —
  this change does not alter context length, only ownership.
- `drop_session_memory(session_id)` for `/reset`.
- `AgentApplicationState.memory` is removed so no call site can accidentally keep
  using a shared buffer.
- `session_lane._locks` moves into this module under the same cap. `session_lane()`
  stays exported from `services/session_lane.py` (the public import, used by
  `main.py` and `tests/unit/test_chat_commands.py`); only the data structure moves.

`BoundedMemory` gains an optional `session_id` and `clear()` now resets `_on_trim`.
Resetting the callback at the source kills the stickiness for good, instead of
relying on every call site to remember to rebind it.

Note `_chat_impl` re-adds up to 16 messages into a `maxlen=16` deque after
`clear()`; because `add()` fires `_on_trim` when the buffer is already at capacity,
the 16th re-add can trigger a spurious flush. Re-adding into a fresh buffer with the
callback unset (the new `clear()` semantics) removes that too.

Why a registry and not a memory instance per request: `_hydrate_memory` currently
reloads from Postgres on every turn, so a per-request buffer would work, but the
`set_on_trim` → `maybe_flush_before_compaction` hook and `_compact_session` (called
from the Telegram poller and the WhatsApp control path, outside a request) both need
a stable handle for a session. A keyed registry serves both without changing those
call sites' signatures.

RAM impact: 32 sessions × 16 messages, bounded by the same per-message size already
held today. Negligible against the 2 GB `mem_limit`; no new container.

### Auth

`verify_api_key` gains a startup-time companion, `require_api_key_configured()`,
called from `lifespan`. With `EVI_REQUIRE_API_KEY=true` and an empty `EVI_API_KEY`
the app refuses to start rather than serving everything open. Default stays `false`
so existing local setups are unaffected — the change is opt-in enforcement plus the
four missing `Depends`, which are backward compatible while `EVI_API_KEY` is empty.

`/` and `/health` remain open: the compose healthcheck hits `/`, and a Prometheus
scrape cannot send a header. `/metrics` also stays open but only when
`EVI_METRICS_ENABLED=true`, which is already the gate.

### Timezone

One helper, `tools/calendar_time.now_local()`, returning
`datetime.now(ZoneInfo(evi_timezone()))`. `graph._calendar_block()` and
`calendar_time.iso_event_range()` call it. `note_core.py` and `testing/cli.py` keep
naive `datetime.now()` — those are filenames and test session ids, where a UTC
timestamp is harmless and changing them would churn golden files.

`TZ=${EVI_TIMEZONE}` on `agent-api` is belt-and-braces: it fixes anything that still
reads the system clock, but the code no longer depends on it.

### Host ports

Data services bind `127.0.0.1` rather than being unpublished, because the host
genuinely needs them: `evi-test rag --live-qdrant` hits `localhost:6333`
(`agent/testing/cli.py`), `scripts/setup-evolution.sh` and the QR manager UI use
`localhost:8082`, and `docs/testing.md` SCN-E2E-03 connects to Postgres from the
host.

Postgres moves to host port **5433**: an unrelated `whatbot-db-1` container on this
machine already publishes `0.0.0.0:5432`, which is why `evi-postgres-1` has been
down. The container-internal port stays 5432, so the compose-internal
`DATABASE_URL` (`postgres:5432`) is unchanged; only host-side references move
(`.env.example`, `docs/testing.md`).

### Dependency pinning

`agent/requirements.txt` becomes the single source, pinned with `==` from whatever
the currently green CI resolved (capture with `pip freeze` in CI before pinning, so
the pins reflect a known-good set rather than today's latest). `Dockerfile` switches
to `COPY requirements.txt .` + `pip install -r`, which also restores layer caching —
today every source edit reinstalls LangChain. `requirements-dev.txt` keeps only test
tooling and adds `-r agent/requirements.txt`.

### Background LLM provider

`build_llm(*, provider: str | None = None, ...)` — when `provider` is passed it wins
over `EVI_LLM_PROVIDER`. `build_background_llm` passes
`EVI_BACKGROUND_LLM_PROVIDER` through instead of swapping the env var around a call.
Removes a real race: today a background summary can flip the provider under a
concurrent `/chat`.

### Soft-fail logging

`services/soft_fail.py`: `soft_fail(context: str, exc: Exception) -> None` writing one
`logging.warning` line with a stable `context` label. Every `except Exception: pass`
becomes `except Exception as exc: soft_fail("contact_filesystem.ingest", exc)`.
Semantics are identical — nothing starts raising. This is deliberately mechanical so
it can be reviewed as a diff of one line per site.

## Out of scope

- **Dev bridge repo-root bug.** `_REPO_ROOT` resolving to `/` inside the container
  is real and known, but fixing it means deciding whether the bridge should exist in
  the container at all (mount the repo + install `git`/`claude`, or run it host-side
  only). That is a product decision, tracked separately in `BACKLOG.md`.
- **Structured tool result contract.** Replacing `if "failed" in result.lower()`
  with a typed result touches all 26 tools and every Windmill script — its own change.
- **`heartbeat._contacts_needing_synthesis` always-true comparison.** Separate,
  tracked in `BACKLOG.md`.
- **Postgres connection pooling**, `/health` check concurrency, and tool gating by
  configuration. Performance, not correctness; no evidence they bite at current load.
- **Prompt-injection hardening** of WhatsApp content reaching the main graph.
  Needs its own threat model and spec.
