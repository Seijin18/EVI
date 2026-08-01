## 1. Implementation

- [ ] 1.1 Group tools into `TOOL_GROUPS`, `core` always included
  - SCN-ROUTE-01
  - Files: `agent/tools/registry.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_routing.py::test_core_always_included -q`

- [ ] 1.2 `channel_from_session()` helper
  - Files: `agent/services/session_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_routing.py::test_channel_from_session -q`

- [ ] 1.3 `services/tool_routing.py` — regex heuristic groups (email/whatsapp/rag/graph/dev)
  - SCN-ROUTE-02
  - Files: `agent/services/tool_routing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_routing.py::test_heuristic_matches_groups -q`

- [ ] 1.4 LLM fallback (`EVI_TOOL_ROUTING_LLM`) when heuristic matches nothing beyond core
  - SCN-ROUTE-03
  - Files: `agent/services/tool_routing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_routing.py::test_llm_fallback_when_ambiguous -q`

- [ ] 1.5 `AgentState.channel` + compute `select_tools()` once per turn (not per ReAct iteration)
  - SCN-ROUTE-04
  - Files: `agent/graph.py`, `agent/main.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_routing.py::test_selected_once_per_turn tests/unit/test_chat_invoke.py -q`

- [ ] 1.6 `agent_node` binds selected subset; `SYSTEM_PROMPT` tool list + rules 9/10 trimmed to selection
  - Files: `agent/graph.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_tool_routing.py::test_system_prompt_trimmed -q`

- [ ] 1.7 Channel handlers (WhatsApp/Telegram) pass `channel` into `initial_state`
  - Files: `agent/services/whatsapp_control.py`, `agent/services/telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_control.py tests/unit/test_telegram_handler.py -q`

- [ ] 1.8 `evi-test tool-routing` offline harness check
  - Files: `agent/testing/cli.py`
  - Verify: `./scripts/evi-test tool-routing`

- [ ] 1.9 Docs + env
  - Files: `.env.example`, `docs/dev-workflow.md`
  - Verify: manual read-through
