## Design

### Why the guard was worse than nothing

The first guard checked `svc.get("env_file")` in the output of
`docker compose config`. That key is never present there — Compose resolves
`env_file` into `environment` during normalization and drops it. So the check
could not fail, and it printed `[PASS]` over a config that was leaking every
secret in `.env`.

That is the same failure shape as the `< 500` rule in the Qdrant health check: an
assertion written against the mechanism the author had in mind rather than the
property that matters. The rewrite asserts the property — *no real credential is
present in the smoke's environment* — which holds regardless of which of the four
channels a future regression opens.

Verified empirically in both directions before committing:

- with `env_file: !reset []` removed and a real `.env` present → guard aborts,
  naming `WINDMILL_TOKEN` and `NEO4J_PASSWORD`
- with the fix, `.env` present → passes
- with the fix, `.env` absent (the CI condition) → passes

### Two channels, not one

`env_file: !reset []` removes the service-level file, but Compose independently
reads `./.env` to interpolate `${VAR}` in the compose file itself. The base file
has `- WINDMILL_TOKEN=${WINDMILL_TOKEN:-}` and `- NEO4J_PASSWORD=...`, so those
kept arriving after the reset. `--env-file /dev/null` replaces the interpolation
source and closes it.

The empty exports are a third layer, deliberately redundant: they cover the
variables that *do* have an explicit `${VAR:-}` entry, so even if both compose
mechanisms regressed, `TELEGRAM_MODE` would still be empty and no poller would
start. Belt, braces, and a third thing — because this is the channel that touched
the user's real bot.

### Not addressed

Making the smoke work without any `.env` at all is already true, but the base
compose still *requires* `POSTGRES_USER`/`POSTGRES_PASSWORD` to interpolate to
something. The smoke exports them. A developer running `docker compose up` with no
`.env` still gets blank credentials — that is the base file's behaviour and out of
scope here.

## Out of scope

- **Restructuring `docker-compose.yml`** so the dev stack does not need overrides
  at all (e.g. named volumes by default, a `dev` override for the bind mounts).
  That is the real fix for the class, but it changes how the user runs the stack
  every day and deserves its own change.
- **Auditing the other four host-reaching paths** (`./watched_folders`,
  `./EVI_WORKSPACE`, `./tests/fixtures`, `./logs`). The first two are mounted
  read-only or write-only-to-workspace in the smoke; fixtures is `:ro`. None hold
  state the smoke can corrupt.
- **Docker layer caching in CI**, still deferred from #32.
