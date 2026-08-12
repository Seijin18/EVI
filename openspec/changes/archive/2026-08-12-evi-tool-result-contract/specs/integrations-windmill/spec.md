## ADDED Requirements

### Requirement: Windmill responses are classified structurally
Tools SHALL decide whether a Windmill operation succeeded by parsing its response into a `ToolResult` (`agent/services/tool_result.py`), never by inspecting their own prose. Substring tests such as `if "failed" in result.lower()` or `'"status":"created"' in result` are not a valid success signal.

The parser SHALL tolerate every envelope the deployed scripts emit, since the scripts are not being normalised: `status` of `"created"` **or** `"ok"` for success; the error code under `http_status` **or** `http`; `action` optionally absent; and a `status` value it does not recognise treated as failure, not success — the cron scripts can overwrite `status` through their `**body` splat.

It SHALL also classify the sentinels the client returns as plain strings, which carry no `"failed"` token and therefore escaped every previous check: `Missing <ENV_VAR>` and `Unknown Windmill operation:` are configuration failures, and a body that does not parse is a failure rather than an ambiguous pass-through.

Parsing SHALL happen before any prose heuristic, so an envelope whose `status` value merely contains `"failed"` is not misread as a transport error.

#### Scenario: SCN-TOOL-01
- **WHEN** `tests/unit/test_tool_result.py` runs
- **THEN** `created` and `ok` both read as success; `http_status` and `http` are both recognised; `Missing WINDMILL_*`, `Unknown Windmill operation:`, an unparseable body and an unrecognised `status` all read as failure with a distinct `reason`

### Requirement: Tools keep a string at the LangChain boundary
Tools SHALL remain declared `-> str` and return `str(result)`. `ToolNode` writes that text into `ToolMessage.content`, which is what the model reads, so the structured value is for the agent's own code only. Callers that must branch on success SHALL use the `*_result` variant (`schedule_event_result`, `create_task_result`) rather than re-inspecting the rendered prose.

#### Scenario: SCN-TOOL-02
- **WHEN** a tool succeeds or fails
- **THEN** the user-facing wording is unchanged from before this contract existed, and `bool(result)` / `str(result)` keep existing call sites working
