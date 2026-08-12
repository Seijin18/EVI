## 1. Implementation

- [x] 1.1 `ToolResult` + `parse_windmill_result` tolerating the four envelopes
  - SCN-TOOL-01
  - Files: `agent/services/tool_result.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_result.py -q`

- [x] 1.2 Classify the transport sentinels that currently escape
  - SCN-TOOL-01
  - Files: `agent/services/tool_result.py`
  - Verify: `Missing WINDMILL_*`, `Unknown Windmill operation:` and a truncated body all yield `ok=False` with a distinct `reason`

- [x] 1.3 Migrate `calendar_tool` (3 sniffs, 3 inline parsers)
  - SCN-CAL-08
  - Files: `agent/tools/calendar_tool.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_schedule.py tests/unit/test_telegram_list.py -q && ./scripts/evi-test calendar calendar-list`

- [x] 1.4 Migrate `email_tool` + `task_tool`
  - SCN-TOOL-02
  - Files: `agent/tools/email_tool.py`, `agent/tools/task_tool.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_email_tool.py tests/unit/test_list_tasks.py tests/unit/test_delete_emails_by_query.py -q`

- [x] 1.5 **Fix the `"criad"` bug** — `commitment_tools` gates on `result.ok`
  - SCN-CHAT-05
  - Files: `agent/tools/commitment_tools.py`
  - Verify: a failing `schedule_event` whose detail contains "criada" must NOT set status `scheduled` — new test in `tests/unit/test_commitment_tools.py`

- [x] 1.6 `response_format` keeps its prose; the decision moved upstream
  - SCN-TOOL-02
  - Files: `agent/tools/email_tool.py`
  - Note: the six `if "failed" in raw.lower()` prefixes are now dead code on the
    success path — every caller classifies with `parse_windmill_result` first.
    They stay as a defensive backstop for any direct caller; deleting them is
    cleanup with no behavioural gain and would churn the prose tests.
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_response_format.py -q`

- [ ] ~~1.7 Structured session snapshots~~ — **descoped, see design**
  - Cannot be done without changing what the model reads. By the time
    `persist_tool_snapshots` sees a `ToolMessage`, the tool has already rendered
    prose and the Windmill body is gone. The clean mechanism is LangChain's
    `response_format="content_and_artifact"` (content for the model, artifact for
    our code), which changes the tool signature and `ToolNode` handling — its own
    change, tracked in `BACKLOG.md`.

- [x] 1.8 Harness asserts on `ok`, not substrings
  - SCN-TEST-12
  - Files: `agent/testing/cli.py`
  - Verify: `./scripts/evi-test smoke` 13/13

- [x] 1.9 Spec deltas
  - Files: `openspec/changes/evi-tool-result-contract/specs/{tools-productivity,integrations-windmill}/spec.md`
  - Verify: `openspec validate evi-tool-result-contract`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-test sessions runtime-v3 inbox-ux && ruff check agent/ --select E,W,F --ignore E501 && ./scripts/evi-container-smoke.sh && openspec validate --specs`

- [ ] 2.2 End-to-end check of the bug, which no unit test covers
  - Verify: with the stack up and an invalid `WINDMILL_GCAL_RESOURCE`, confirm a commitment and check the row stays `pending` in Postgres

- [x] 2.3 Update `Progress.md` + `openspec/BACKLOG.md`, then `openspec archive evi-tool-result-contract`
