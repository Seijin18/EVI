# Design: evi-windmill-live-verify

## Context

- `schedule_event` live path works via `run_calendar(live_windmill)` invoking the tool and checking `"status":"created"`.
- `summarize_inbox` and `create_task` tools POST to Windmill with `$res:` resource refs; scripts exist under `windmill/f/integrations/`.
- `run_email()` only parses a JSON fixture; `run_tasks` live accepts loose `"created"` substring matches.
- Hardware: 16 GB RAM — no new services.

## Goals / Non-Goals

**Goals:**

- Parity: email and tasks Tier 2 live tests mirror calendar pattern
- Strict live assertions: `"status":"created"` for tasks; non-empty `summary` for email
- Operator docs for Gmail (`gmail` resource) and Tasks (`gcloud` / `gtasks` resource) OAuth in Windmill UI

**Non-Goals:**

- Changing Windmill script logic unless live test reveals a bug
- Compose healthchecks, Telegram tunnel, CI

## Decisions

1. **Harness invokes LangChain tools** (`summarize_inbox.invoke`, `create_task.invoke`) — same code path as agent chat; no duplicate HTTP client in cli.
2. **Live flag propagation** — `run_email(live_windmill: bool)` and dispatcher `email: lambda: run_email(live_wm)`; smoke keeps offline email.
3. **Task assertion** — require `"status":"created"` or `"status": "created"` in response text; drop generic `"created"` substring to avoid false positives.
4. **Email assertion** — require `"summary"` in response with length > 0 after live call; accept `"status":"ok"` from Windmill script.
5. **Unit test** — mock `post_windmill` in `tests/unit/test_email_tool.py` (new) rather than hitting network.

## Risks / Trade-offs

- [Live tests need OAuth] → Document prerequisites; offline smoke unchanged; live is opt-in `--live-windmill`
- [Gmail API quota / empty inbox] → `summarize_inbox` returns `count: 0` with summary text; test checks summary key exists
- [Windmill down] → live test fails with clear error in `_result` message
