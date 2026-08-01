## Design

### Tool groups (`agent/tools/registry.py`)

```python
TOOL_GROUPS = {
    "core": [schedule_event, list_calendar_events, list_calendars, create_task,
             list_tasks, save_note_manual, list_pending_commitments,
             list_scheduled_today, confirm_commitments, dismiss_commitments],
    "email": [summarize_inbox, delete_emails, delete_emails_by_query, organize_inbox],
    "whatsapp": [list_whatsapp_contacts, get_whatsapp_contact_info,
                 learn_whatsapp_contact, set_whatsapp_contact_name,
                 list_recent_whatsapp_messages, summarize_whatsapp_messages],
    "rag": [ingest_university_pdf, ingest_university_folder, query_university_notes],
    "graph": [query_conversation_graph],
    "dev": [propose_dev_task_tool, status_dev_jobs_tool],
}
```
`get_all_tools()` stays unchanged (still returns the full flat list) — `ToolNode` is
built from it once at startup in `build_agent_graph()` and keeps executing whatever
the model calls. Only `bind_tools()` inside `agent_node` uses the filtered subset.

### Channel resolution

`services/session_context.py` gains `channel_from_session(session_id) -> str`,
generalizing the existing `extract_jid_from_session` prefix check
(`whatsapp-` / `telegram-` / else `"api"`).

### `services/tool_routing.py` (new)

```python
def select_tools(user_message: str, channel: str) -> tuple[list, str]:
    """Returns (tools, method) where method is 'heuristic' | 'llm'."""
    selected = list(TOOL_GROUPS["core"])
    matched_group = False
    for pattern, group in _ROUTING_RULES:  # same shape as skill_loader._SKILL_RULES
        if pattern.search(user_message):
            selected += TOOL_GROUPS[group]
            matched_group = True
    if not matched_group and os.getenv("EVI_TOOL_ROUTING_LLM", "false").lower() in ("1","true","yes"):
        groups = _llm_select_groups(user_message)  # build_background_llm(), constrained output
        for g in groups:
            selected += TOOL_GROUPS.get(g, [])
        return _dedup(selected), "llm"
    return _dedup(selected), "heuristic"
```
`_llm_select_groups` prompts the background LLM with the fixed list of group names
and asks for a comma-separated subset (few-shot, low temperature) — same call shape
as `contact_learning._llm_synthesize`. On any exception, falls back to `core` only
(fail open, never raises into `agent_node`).

### State plumbing

`AgentState` (`agent/graph.py`) gains `channel: str`. `_chat_impl` (`agent/main.py`)
and the WhatsApp/Telegram handlers compute `select_tools(...)` once when building
`initial_state`, store the resulting tool list in a new state field
`selected_tools_names: list[str]`. `agent_node` looks up the actual tool objects
by name from the full registry instead of recomputing `select_tools` — this is what
avoids re-running the heuristic/LLM on every ReAct iteration within one turn.

### System prompt

`SYSTEM_PROMPT.format(tool_names=...)` uses the filtered subset's names. Rules 9
(WhatsApp contact tools) and 10 (list_calendars/dev bridge) become conditional
paragraphs, only included when `whatsapp`/`dev` groups are in the selection —
trims the fixed ~600-token rule block further, not just the tool schemas.

### RAM / infra impact

None — no new containers, no new ports. `EVI_TOOL_ROUTING_LLM=true` adds an extra
`build_background_llm()` call (Ollama, already running on host) only on the
ambiguous-message path, same resource profile as existing background jobs
(heartbeat, contact learn, daily summary).

## Out of scope

- Per-tool argument-level filtering (only group-level on/off).
- Regex coverage beyond pt-BR/en phrasing.
- Changing `ToolNode`'s registered set — it stays the full registry; only what's
  offered to the LLM via `bind_tools()` is filtered.
- Caching/memoizing `select_tools()` results across turns (each turn re-evaluates).
