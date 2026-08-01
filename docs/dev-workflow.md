# EVI vs IDE assistants

| Task | Use |
|------|-----|
| Organize files, RAG notes, calendar/tasks via n8n | **EVI** `/chat` or tools |
| WhatsApp commitment extraction (dev/test) | `./scripts/evi-test whatsapp` |
| Implement/refactor this repo remotely (WhatsApp/Telegram) | **Dev bridge** — `dev: <descrição>` → `dev approve <job_id>`; CLI backend selected via `EVI_DEV_CLI` (default `claude`, `agent/devcli/`) |
| Explain Docker logs, scaffold tests | `scripts/copilot-dev-runner.sh` (standalone, not wired into the dev bridge) |
| Heavy codegen in other repos | Copilot CLI or Claude in IDE |

EVI runs locally (Ollama); IDE tools are for implementation. Do not duplicate cloud LLM APIs inside `agent-api` unless you need a single remote endpoint.

## Dev bridge

Gated by `EVI_DEV_BRIDGE_ENABLED=true` and only reachable from `EVI_WHATSAPP_CONTROL_JIDS`/Telegram control chat:

- `dev: <descrição> [--cli=<backend>]` — registra um job pendente (backend default: `EVI_DEV_CLI`).
- `dev approve <job_id> [--cli=<backend>]` — executa o job em modo `apply` (edita arquivos, commita numa branch `dev/job-*`, nunca faz merge sozinho).
- `dev status` / `dev jobs` — lista jobs recentes com backend/modo/branch.
- `dev mode plan` / `dev mode default` — liga/desliga preview síncrono (modo `plan`) ao propor, no espírito do `/plan` do Claude Code.

Backends vivem em `agent/devcli/` (`Protocol` + factory, ver `agent/devcli/factory.py`). Adicionar um novo CLI é um novo módulo + uma entrada em `resolve_dev_cli` — não requer tocar em `agent/services/dev_bridge.py`.
