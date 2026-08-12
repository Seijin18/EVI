## Why

Tools decide success by reading their own prose. `agent/tools/calendar_tool.py:70`
is `if "failed" in result.lower():`; `:85` is
`if '"status":"created"' in result or '"status": "created"' in result:`. The same
shape repeats in `response_format.py` six times. This is not only fragile — it is
already wrong in three places:

- **`commitment_tools._tool_succeeded` matches the substring `"criad"`**
  (`agent/tools/commitment_tools.py:16-19`) and its result gates
  `update_commitment_status(..., "scheduled", ...)`. A Windmill *error* whose
  detail happens to contain "criada" marks the commitment as scheduled while no
  event exists. The comment in the code admits the stem match.
- **`"Missing {env_var}"` and `"Unknown Windmill operation:"`**
  (`agent/integrations/windmill.py:62`, `:114`) contain no `"failed"`, so every
  `if "failed" in raw.lower()` misses them and they reach the model through the
  fallthrough branches as possibly-successful.
- **`format_confirm_results` looks for `": failed"`** (`response_format.py:201`)
  but the calendar failure text starts with `"Falha ao …"`, so that line gets no
  marker at all and renders as neutral.

A fourth cost is silent: the five `_SNAPSHOT_TOOLS` all return prose, so
`persist_tool_snapshots` stores `{"raw": prose}`. The "SESSION TOOL SNAPSHOTS"
block the system prompt tells the model to use for follow-ups ("apaga o primeiro")
carries no structured ids.

## What Changes

- **`agent/services/tool_result.py` (new)** — `ToolResult` frozen dataclass
  (`ok`, `message`, `data`, `reason`, `detail`) with `__str__` → `message` and
  `__bool__` → `ok`, following the precedent `SendResult`
  (`agent/services/send_result.py:29`) set for exactly this problem on the send path.
- **The LangChain boundary does not change.** Tools stay declared `-> str` and
  return `str(result)`; `ToolNode` puts that in a `ToolMessage`, so altering the
  return type would change what the model reads. The structure is consumed inside
  the agent.
- **`parse_windmill_result(raw) -> ToolResult`** in the same module, reusing
  `_parse_json_blob` (`response_format.py:40`, already more tolerant than the
  three inline copies in `calendar_tool.py`) and `format_windmill_oauth_error`
  (`:11`) for the OAuth prose. It tolerates the four envelopes the Windmill
  scripts actually emit — `created` vs `ok`, `http_status` vs `http`,
  `list_calendars` without `action`, and the cron trio whose `**body` splat can
  overwrite `status` — and classifies the two sentinels that currently escape.
- **Consumers of the structure**: `commitment_tools` uses `result.ok` instead of
  `_tool_succeeded` (kills the `"criad"` bug); `session_context.persist_tool_snapshots`
  stores `result.data`; `agent/testing/cli.py` replaces ~15 substring assertions.
- Migration one tool at a time, suite green between each: `calendar_tool` →
  `email_tool` + `task_tool` → `commitment_tools` → `response_format`.

The Windmill scripts are **not** touched (decision recorded 2026-08-12): the push
is one-way, triggers and resources live only in the UI, and the adapter has to
tolerate the variants anyway.

## Impact

`agent/services/tool_result.py` (new), `agent/tools/calendar_tool.py`,
`agent/tools/email_tool.py`, `agent/tools/task_tool.py`,
`agent/tools/commitment_tools.py`, `agent/services/response_format.py`,
`agent/services/session_context.py`, `agent/testing/cli.py`.
Tests: `tests/unit/test_tool_result.py` (new) plus the existing tool tests.
Specs: `tools-productivity`, `integrations-windmill`.

Out of scope: the non-Windmill tools (`rag_tool`, `graph_tool`, `note_manager`,
`file_organizer`, `contact_tool`) — they signal with their own prose and have no
upstream envelope to normalise; and normalising the Windmill scripts themselves.
