## ADDED Requirements

### Requirement: Core tools always available
`select_tools()` SHALL always include the `core` tool group (calendar, tasks, commitments) regardless of message content or channel, so the most common product surface never depends on detection succeeding.

#### Scenario: SCN-ROUTE-01
- **WHEN** `select_tools("oi", channel="whatsapp")` runs
- **THEN** the returned tool list is a superset of `TOOL_GROUPS["core"]`

### Requirement: Heuristic group matching
`select_tools()` SHALL match additional tool groups (email, whatsapp, rag, graph, dev) via regex against the user message, mirroring `skill_loader.match_skills`, with no LLM call on the default path.

#### Scenario: SCN-ROUTE-02
- **WHEN** `select_tools("apagar emails da promoção", channel="api")` runs
- **THEN** the returned tools include the `email` group and the reported method is `"heuristic"`

### Requirement: LLM fallback for ambiguous intent
When the heuristic matches no group beyond `core` and `EVI_TOOL_ROUTING_LLM=true`, `select_tools()` SHALL fall back to a `build_background_llm()` classification over the fixed group names, mirroring `extract_commitment_with_fallback`'s heuristic-then-LLM shape. On any error the fallback SHALL degrade to `core`-only rather than raise.

#### Scenario: SCN-ROUTE-03
- **WHEN** the message matches no heuristic group and `EVI_TOOL_ROUTING_LLM=true`
- **THEN** `select_tools()` calls the background LLM once and returns method `"llm"`; if the LLM call raises, the result is `core`-only tools with no exception propagated

### Requirement: Tool selection computed once per turn
Tool selection SHALL run once per user turn (before entering the LangGraph loop), not once per ReAct iteration inside `agent_node`, to avoid repeated heuristic/LLM cost within a single multi-step tool-calling turn.

#### Scenario: SCN-ROUTE-04
- **WHEN** a turn triggers 3 sequential tool calls (3 `agent_node` invocations)
- **THEN** `select_tools()` is invoked exactly once for that turn, with the result reused across all `agent_node` invocations via `AgentState`
