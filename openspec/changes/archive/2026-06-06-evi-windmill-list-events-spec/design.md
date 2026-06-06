## Context

`list_calendar_events` in `calendar_tool.py` already POSTs to Windmill with OAuth retry. Telegram bypass unit test mocks the tool; live verification mirrors `run_calendar(live)`.

## Decisions

1. **Subcommand** `calendar-list` — distinct from `calendar` (schedule_event).
2. **Live PASS** — response contains `Próximos eventos` or `Nenhum evento`; fail on `Falha` / `422`.
3. **Mock mode** — invoke with patched `list_calendar_events` returning fixture string (offline smoke optional).

## Out of scope

Windmill script changes; smoke suite expansion (document only).
