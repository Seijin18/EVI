## Why

WhatsApp control bypassed LLM; ingest produced false positives and backlog after downtime.

## What Changes

- `evolution_filter`: require ts, watermark, mark all ids seen
- Control channel → grafo (`EVI_DIRECT_HANDLERS=false`)
- Extract with contact memory context; stricter heuristics

**Out of scope:** ack in origin chat.
