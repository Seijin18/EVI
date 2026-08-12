## Design

### Why these four, in this order

Ranked by "a silent regression here costs a user-visible failure". The poller and
the webhook are the two entry points that carry real traffic; `db.py` is where a
wrong transition becomes a durable lie (a commitment marked scheduled with
nothing booked — exactly the bug `evi-tool-result-contract` just fixed one layer
up); `evolution_client` is the reply path out.

### Postgres, not a mock

`db.py` is almost entirely SQL. Mocking `psycopg2` would assert that we call the
functions we call, not that the schema behaves — `ON CONFLICT (source, source_id)
DO NOTHING` and `WHERE status = 'pending'` are the contract, and only a real
database can check them. The tests skip without `DATABASE_URL` so a laptop run
stays fast, and CI provides the service.

Each test generates its own ids (`uuid4`), so they neither collide nor need a
truncate between runs — safe against a developer pointing `DATABASE_URL` at a
database that already has rows.

### Loop tests without sleeping

`_poll_loop` is `while not _stop.is_set()`. The tests set `_stop` from inside the
mocked handler, so a single iteration runs deterministically; `time.sleep` is
patched to a no-op so the 5s retry path costs nothing.

### Patch where the name is bound

`test_evolution_client` patches `messaging.evolution.urllib.request.urlopen`, not
`urllib.request.urlopen`. The lesson is fresh: in `evi-tool-result-contract` a
first draft patched `integrations.factory.get_integration` while the tools had
already bound the name at import, so the failure assertions passed vacuously
against a dead Windmill rather than against the fix.

## Out of scope

- **`session_lane`** — its concurrency test was rewritten in
  `evi-runtime-hardening` and lives in `test_chat_commands.py`.
- **The other ~20 modules with no test file.** Mostly formatters and thin
  wrappers; adding tests there is volume, not risk reduction.
- **Coverage measurement.** Adding `pytest-cov` and a threshold invites gaming the
  number; the gap list here was chosen by traffic and blast radius instead.
- **An end-to-end poller test against the real Telegram API.** That needs the live
  bot and would fight the running poller for `getUpdates` — the same 409 conflict
  the smoke isolation fix just eliminated.
