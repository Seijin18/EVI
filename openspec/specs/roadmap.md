# EVI roadmap (not yet implemented)

| Item | Type | Notes |
|------|------|-------|
| n8n spec removed | Done | Use `integrations-windmill` only; SCN-DEP-02 |
| Neo4j + graph_tool.py | Architecture | When study/reasoning priority rises |
| MCP isolated servers | Architecture | After 3+ stable tools need isolated restart |
| Llava + Whisper | Feature | Multimodal remote |
| Redis embedding cache | Performance | Optional |
| Prometheus metrics | Ops | agent-api + compose |
| Unify tool registry only | DX | Done via `tools/registry.py` |
| Compose healthchecks | Ops | depends_on + Ollama retry |
| WhatsApp live adapter | Integration | Meta / Twilio / export — see remote-access design |
| GitHub Actions CI | Ops | Optional; local `evi-test smoke` for now |
