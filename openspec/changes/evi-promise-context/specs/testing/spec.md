## ADDED Requirements

### Requirement: Structured LLM tasks have an offline-reproducible benchmark
Each structured LLM task SHALL have a benchmark (`./scripts/evi-test llm-eval <task>`) over versioned synthetic cases and optional real cases stored only under `data/eval/` (never committed, never sent to Gemini, and sent to a zero-retention OpenRouter endpoint only with `--allow-cloud-real`), reporting accuracy, false positives and negatives, field quality and latency per model. Changing a task's default model or prompt SHALL be justified by this benchmark.

#### Scenario: SCN-LLM-EVAL-01
- **WHEN** `./scripts/evi-test llm-eval promise --provider gemini --cases all` runs
- **THEN** only the synthetic cases are sent to Gemini and the report says the real cases were skipped
