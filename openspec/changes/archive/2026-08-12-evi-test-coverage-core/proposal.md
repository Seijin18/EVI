## Why

Four modules on the critical path had no test file at all. Two of them are how
this deployment actually runs, and the third is where every durable fact lives:

- `services/telegram_poller.py` — `TELEGRAM_MODE=polling` is the production
  configuration here. A regression that kills the loop or freezes the offset
  stops the bot silently.
- `services/evolution_client.py` / `messaging/evolution.py` — outbound WhatsApp.
  It just gained retry and a structured result in `evi-small-correctness` with no
  direct coverage.
- `db.py` — migrations, `ON CONFLICT` dedupe and the status transitions that
  `confirm_commitments` depends on, verified until now only by running the product.
- `main.py`'s Evolution webhook — ~200 lines of routing (control JID vs ingest,
  echo guard, dedupe, queueing) whose failure mode is a dropped message and one
  JSONL line.

The container smoke (#32) proved the class of defect that lives between modules;
this closes the gaps *inside* them.

## What Changes

- `tests/unit/test_telegram_poller.py` — URL construction, `ok: false` raising,
  webhook removal before polling, and the three loop invariants: it survives a
  handler exception, it survives a transport failure (the "Network is
  unreachable" seen in production), and the offset advances past processed
  updates rather than replaying them.
- `tests/unit/test_evolution_client.py` — JID→number stripping, the `[EVI]`
  prefix and its idempotence (re-prefixing would stack), API key header, retry on
  a blip, no retry on 4xx, and the `EVI_EVOLUTION_CONTACTS_LIMIT` that was
  truncating a 2553-contact address book to 300.
- `tests/unit/test_db.py` — real Postgres, skipped when `DATABASE_URL` is unset.
  Covers idempotent migrations, session scoping, duplicate `source_id` rejection,
  the pending→scheduled transition and its audit columns, the guard that a second
  confirm cannot rewrite an audited row, past-date filtering, priority ordering,
  and case-insensitive alias merging. Also asserts a fresh database does **not**
  get the removed `dev_jobs` / `dev_bridge_state` tables back.
- `tests/unit/test_main_endpoints.py` — `/`, `/tools`, `/reset` scoping, `/note`,
  `/run-task` 404, the job endpoints, and the webhook: normal ingest, echo guard,
  control-JID routing, replay dedupe, group and own-message filtering, unknown
  events, and the JSONL trace.
- **CI gains an ephemeral Postgres service** so `test_db.py` runs rather than skips.

## Impact

`tests/unit/test_{telegram_poller,evolution_client,db,main_endpoints}.py` (new),
`.github/workflows/ci.yml`.
No production code changes. Specs: `testing`.

Out of scope: `session_lane` (covered by `test_chat_commands` since
`evi-runtime-hardening`), and the remaining ~20 modules without test files —
those are lower-traffic helpers, not the critical path.
