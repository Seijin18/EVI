# EVI vs IDE assistants

| Task | Use |
|------|-----|
| Organize files, RAG notes, calendar/tasks via n8n | **EVI** `/chat` or tools |
| WhatsApp commitment extraction (dev/test) | `./scripts/evi-test whatsapp` |
| Implement/refactor this repo | **Cursor Agent** + codebase-memory MCP |
| Explain Docker logs, scaffold tests | `scripts/copilot-dev-runner.sh` |
| Heavy codegen in other repos | Copilot CLI or Claude in IDE |

EVI runs locally (Ollama); IDE tools are for implementation. Do not duplicate cloud LLM APIs inside `agent-api` unless you need a single remote endpoint.
