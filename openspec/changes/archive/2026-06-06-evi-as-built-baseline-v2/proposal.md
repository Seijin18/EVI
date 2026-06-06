## Why

Etapa 0 da revisão de arquitetura confirmou drift: código (Telegram bypass, list events, logs Evolution, polling) à frente das specs; `Progress.md` desatualizado.

## What Changes

- Delta specs: SCN-TG-04/05, SCN-CAL-06, SCN-TASK-06, SCN-WA-13..15, SCN-OPS-02
- Enxugar `Progress.md` e cabeçalho `personal-ai-agent-server.md` → link `openspec/specs/`
- Atualizar `openspec-planning.mdc` e `docs/testing.md`

**Out of scope:** features novas (multichannel review, control chat, LLM extract).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `remote-access`: polling + direct calendar/list bypass
- `integrations-windmill`: list events + gtasks resource
- `messaging-whatsapp`: Evolution log observability
- `testing`: JSONL log retention

## Impact

Docs e specs apenas; sem mudança de runtime.
