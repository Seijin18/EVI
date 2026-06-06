## Context

Heuristic extractor in `whatsapp_processor.py` covers w001–w003 golden fixtures. Evolution webhook calls `process_messages` synchronously; LLM must be opt-in to keep Tier 1 offline and avoid webhook latency by default.

## Decisions

1. **Opt-in** — `EVI_WHATSAPP_LLM_EXTRACT=false` default; enable in production `.env` when Ollama is up.
2. **Direct ChatOllama** — same model/env as `graph.py`; no LangGraph round-trip.
3. **JSON prompt** — single-turn: `{type, title, date, time, due, confidence}`; parse defensively.
4. **Threshold** — `EVI_WHATSAPP_LLM_MIN_CONFIDENCE=0.6`; below → skip with log.
5. **Timeout** — `EVI_WHATSAPP_LLM_TIMEOUT_SEC=30`; exception → `llm_extract_skip`, no queue impact.

## RAM / ports

No new containers. One Ollama inference per failed heuristic message when enabled; fits 16 GB + GTX 1060 3GB with `OLLAMA_MAX_LOADED_MODELS=1`.

## Out of scope

Control chat `/chat` path; changing golden w001–w003 behavior without LLM flag.
