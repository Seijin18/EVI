## Why

`agent/graph.py` binds all ~25 tools on every LLM call, in every channel, regardless
of intent — the single biggest avoidable token cost in the interactive chat path.
Product priority is productivity (calendar/tasks/email/WhatsApp) > Telegram > dev
bridge > RAG, so the core group must never be gated, and any misdetection must
fail open (model just says it lacks a tool) rather than break a turn.

## What Changes

- `tools/registry.py`: group tools into `TOOL_GROUPS` (core/email/whatsapp/rag/graph/dev); `core` always included.
- New `services/tool_routing.py`: `select_tools(user_message, channel)` — regex heuristic first (mirrors `skill_loader.match_skills`); when the heuristic matches nothing beyond `core`, optional LLM fallback via `build_background_llm()` (mirrors `whatsapp_llm_extract.extract_commitment_with_fallback`), gated by `EVI_TOOL_ROUTING_LLM` (default off).
- `AgentState` gains `channel`; tool selection computed once per turn (in `_chat_impl`/channel handlers), not once per ReAct iteration inside `agent_node`.
- `SYSTEM_PROMPT`'s tool list/rules trimmed to match the selected subset.

**Out of scope:** per-tool argument-level filtering; regex beyond pt-BR/en; changing what `ToolNode` can execute (it keeps the full tool set — only what's *offered* to the model is filtered).
