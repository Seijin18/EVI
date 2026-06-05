## Context

Commitment inbox, review tools, and Windmill Calendar/Tasks/Gmail scripts landed in `cff17bb`. Chat list flow was validated manually; confirm only schedules `type=event` and marks `type=task` as scheduled without Windmill. Tier 2 harness lacks a `commitments` feature and live task assertion is outdated.

## Goals / Non-Goals

**Goals:**
- Close the WhatsApp → review → Calendar **or** Google Tasks loop in `confirm_commitments`.
- Add reproducible Tier 1/2 tests for SCN-CHAT-02/03 and SCN-WA-10.
- Align live Windmill task verification with `create_task.py` JSON response.

**Non-Goals:**
- Telegram digest E2E (SCN-WA-12), Windmill `telegram_to_evi` live test.
- Compose healthchecks, Prometheus, Neo4j, Meta WhatsApp.
- Auto-confirm without user review in chat.

## Decisions

1. **Task confirm path:** `confirm_commitments` calls `create_task.invoke` with `title`, `due_date` from row; mark `scheduled` only when response contains `created` (same pattern as calendar).
2. **Tier 2 `commitments`:** offline — seed Postgres via `db` helpers, call tools directly; optional `--live-windmill` skips calendar/tasks HTTP if env unset.
3. **Unit tests:** mock `schedule_event` / `create_task` in `test_commitment_tools.py` — no Ollama in Tier 1.
4. **Live tasks fix:** `run_tasks(live)` checks `"status":"created"` like calendar, not `"Successfully"` only.

## Risks / Trade-offs

- **[Risk]** LLM may not call tools reliably in chat E2E → **Mitigation:** Tier 2 tests tools directly; chat remains `--full` optional.
- **[Risk]** Duplicate Google Tasks on re-confirm → **Mitigation:** only `status=pending` rows are confirmable (existing guard).
- **[Risk]** No new containers; RAM unchanged.

## Migration Plan

1. Implement code + tests.
2. `pytest tests/unit -q && ./scripts/evi-test commitments && ./scripts/evi-test smoke`.
3. Optional live: `./scripts/evi-test tasks --live-windmill` with `WINDMILL_GTASKS_RESOURCE` set.
4. Archive change; sync delta specs to main.
