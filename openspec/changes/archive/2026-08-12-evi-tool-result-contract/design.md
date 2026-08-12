## Design

### `ToolResult`

```python
@dataclass(frozen=True)
class ToolResult:
    ok: bool
    message: str               # pt-BR prose — what the model reads
    data: dict[str, Any] | None = None
    reason: str = ""           # "", oauth, not_configured, upstream_error,
                               # unparseable, http_error
    detail: str = ""
    def __str__(self) -> str: return self.message
    def __bool__(self) -> bool: return self.ok
```

`__bool__` and `__str__` are the whole compatibility story, exactly as with
`SendResult`: a call site that does `if result:` or embeds it in an f-string keeps
working, and `str(result)` at the tool's `return` keeps the LangChain boundary a
plain string.

### Why the tools keep returning `str`

`ToolNode` writes the tool's output into `ToolMessage.content`, which is what the
model sees. Returning a dataclass would change that text (or force LangChain to
serialise it), altering model behaviour for no gain — the structure is wanted by
*our* code, not by the model. So: build a `ToolResult` internally, `return str(it)`.

### `parse_windmill_result`

One function replaces the three inline JSON parsers in `calendar_tool.py` and the
six `if "failed" in raw.lower()` prefixes in `response_format.py`. It must handle,
in order:

1. **Transport sentinels from our own client**, which are the ones that currently
   escape: `"Missing {env_var}"`, `"Unknown Windmill operation:"` → `ok=False`,
   `reason="not_configured"`. And `"Windmill request failed: …"` →
   `reason="http_error"`.
2. **OAuth prose** via the existing `format_windmill_oauth_error`; when it returns
   a hint, that becomes `message` with `reason="oauth"`.
3. **The JSON envelope**, tolerating all four shapes the scripts emit:
   `status == "error"` → failure; `status in ("ok", "created")` → success;
   error code under `http_status` *or* `http`; `action` may be absent.
4. **Unparseable body** → `ok=False`, `reason="unparseable"`, message keeps the
   current "Resposta inesperada" wording. This is a real change: today an
   unparseable body falls through as neither success nor failure, and the model
   sees an ambiguous string.

The `"ok"` literal returned by `_windmill_post` for an empty 2xx body
(`windmill.py:78`) counts as success with no data.

### What the structure unlocks

- `commitment_tools`: `_tool_succeeded(out)` → `result.ok`. This is the change
  with user-visible consequence — a failed `schedule_event` can no longer flip a
  commitment to `scheduled`.
- `session_context.persist_tool_snapshots`: stores `result.data` when present, so
  the SNAPSHOTS block finally carries ids for "apaga o primeiro" follow-ups
  instead of `{"raw": prose}`.
- `agent/testing/cli.py`: `ok = '"status":"created"' in text` and friends become
  `ok = parse_windmill_result(text).ok`.

### Prose is deliberately unchanged

Every user-facing string keeps its current wording, so the ~35 substring
assertions in `tests/unit/` should keep passing. Any that break means the prose
moved by accident — useful signal, not churn. New tests assert on `ToolResult`
fields, which is the contract going forward.

### Migration order

`calendar_tool` (3 sniffs + 3 parser copies) → `email_tool` + `task_tool` (thin,
delegate to `response_format`) → `commitment_tools` (the bug) → `response_format`
(6 formatters lose the duplicated prefix). Suite green between each step so a
regression is attributable to one tool.

## Out of scope

- **Normalising the 12 Windmill scripts** into one envelope. Decision recorded:
  the sync is a one-way push, triggers/resources/variables live only in the UI,
  the metadata is already inconsistent (5 of 12 in `wmill-lock.yaml`), and the
  adapter must tolerate the variants regardless — old jobs and cached responses
  do not get rewritten. Optional cleanup later, not a prerequisite.
- **The non-Windmill tools.** `rag_tool`, `graph_tool`, `note_manager`,
  `file_organizer`, `contact_tool` signal through their own prose sentinels with
  no upstream envelope. Converting them is mechanical but buys nothing until
  something consumes their structure.
- **`windmill.py` truncating bodies to 500/2000 chars** (`:78`), which can cut a
  large JSON mid-object so it will not parse. Real, but it is a change to the
  transport layer with its own risk; `reason="unparseable"` at least makes it
  visible now instead of silent.
- **Making tools raise instead of returning failures.** The graph would surface a
  raised exception as a broken turn; returning a failed result keeps the model
  able to explain and retry.
