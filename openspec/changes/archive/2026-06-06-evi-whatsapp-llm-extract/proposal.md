## Why

WhatsApp commitment extraction is heuristic-only; messages outside regex patterns (e.g. "marcar consulta dia 12 às 10h") are dropped. Product priority requires optional LLM fallback without breaking offline golden tests.

## What Changes

- New `whatsapp_llm_extract.py` with opt-in Ollama JSON extraction
- `extract_commitment_with_fallback()` in processor; log `llm_extract` / `llm_extract_skip`
- SCN-WA-16 unit test with mocked LLM; fixture w005
- Env flags in `.env.example`

**Out of scope:** LangGraph in webhook path; multimodal; retraining heuristics; LLM in control chat.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `messaging-whatsapp`: LLM fallback requirement SCN-WA-16
- `testing`: map SCN-WA-16 to unit test

## Impact

`agent/services/whatsapp_processor.py`, new LLM module, tests, docs.
