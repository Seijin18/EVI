## Why

Bringing the stack up on 2026-08-12 to test Telegram surfaced the cost of three
known-but-deferred defects. `./scripts/evi-telegram-verify.sh` failed at step 2
with `telegram_sent=False` during a ~2 minute window where the container could not
reach `api.telegram.org`. The agent had computed the correct answer — the same
request replayed minutes later returned the real pending commitments — but
`send_telegram_message` swallows any network error into a bare `return False`,
with no retry and no log line. The user's reply was silently discarded and nothing
said why. `evolution.py`'s `send_text` has the identical shape, so WhatsApp drops
replies the same way.

These are the `except …: return <default>` sites that `evi-runtime-hardening`
explicitly left out of its `soft_fail` sweep — the scoping was right (mixing a
mechanical rename with data-flow changes would have been unreviewable) but the
remainder is now demonstrably costing delivered messages. Two other small
always-wrong behaviours ride along, since all four are single-function fixes in
the same "quietly wrong" family.

## What Changes

- **Outbound replies retry and report.** `send_telegram_message`
  (`services/telegram_notify.py`) and `EvolutionClient.send_text`
  (`messaging/evolution.py`) get a bounded retry (2 attempts, short backoff) for
  transport errors only — never for a 4xx, which is a configuration problem that
  retrying cannot fix. Both log through `soft_fail` on the final failure.
- **The failure reason becomes visible.** Both return a small result carrying
  `sent: bool` plus a `reason` (`transport`, `http_4xx`, `not_configured`,
  `empty_text`). `process_telegram_update` and `process_whatsapp_control_message`
  surface it as `send_error` next to the existing `telegram_sent`/`whatsapp_sent`
  booleans, which keep their current type and meaning. `evi-test telegram
  --live-telegram` prints the reason instead of only `telegram_sent=False`.
- **Heartbeat stops flagging every contact.** `_contacts_needing_synthesis`
  (`services/heartbeat.py`) compares `last_ts[:10]` against a 40-char raw slice of
  markdown starting with `## Síntese (`. Since `'2' > '#'`, the comparison is
  always true and every contact with a recent timeline is reported as
  un-synthesised. It parses the date out of the heading and compares dates.
- **Dedupe eviction becomes ordered.** `_save_seen_ids`
  (`services/evolution_filter.py`) does `list(seen)[-_MAX_SEEN_IDS:]` on a `set`,
  so which ids survive a trim is arbitrary — a recently-seen message can be
  evicted while an old one stays, letting a duplicate through. Backed by an
  insertion-ordered structure so the trim keeps the newest ids.

## Impact

`agent/services/telegram_notify.py`, `agent/messaging/evolution.py`,
`agent/services/evolution_client.py`, `agent/services/telegram_handler.py`,
`agent/services/whatsapp_control.py`, `agent/services/heartbeat.py`,
`agent/services/evolution_filter.py`, `agent/testing/cli.py`.
Tests: `test_telegram_notify_retry.py`, `test_heartbeat.py`,
`test_evolution_filter.py`, `test_whatsapp_control.py`.
Specs: `remote-access`, `messaging-whatsapp`, `data-long-memory`.
