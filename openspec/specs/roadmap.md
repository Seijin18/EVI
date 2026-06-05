# EVI roadmap (not yet implemented)

| Item | Type | Notes |
|------|------|-------|
| Commitment close-loop | Done | SCN-CHAT-04 task confirm; `evi-test commitments` |
| n8n spec removed | Done | Use `integrations-windmill` only; SCN-DEP-02 |
| Windmill live verify (Gmail/tasks) | Done | SCN-EMAIL-05, SCN-TASK-05 live harness |
| Telegram digest E2E | Done | SCN-WA-12 + SCN-TG-02 reply loop |
| Neo4j + graph_tool.py | Architecture | When study/reasoning priority rises |
| MCP isolated servers | Architecture | After 3+ stable tools need isolated restart |
| Llava + Whisper | Feature | Multimodal remote |
| Redis embedding cache | Performance | Optional |
| Prometheus metrics | Ops | agent-api + compose |
| Unify tool registry only | DX | Done via `tools/registry.py` |
| Compose healthchecks | Done | SCN-OPS-01 healthchecks + depends_on healthy |
| WhatsApp live adapter | Integration | Meta / Twilio / export — see remote-access design |
| GitHub Actions CI | Ops | Optional; local `evi-test smoke` for now |
