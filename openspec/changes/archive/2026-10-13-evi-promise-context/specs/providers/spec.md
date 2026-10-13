## ADDED Requirements

### Requirement: Structured LLM tasks choose their provider per task
Background tasks that need a structured LLM answer SHALL go through `run_structured(task, prompt, schema)`, which SHALL pick provider (`openrouter`, `ollama` or `gemini`) and model list from `EVI_LLM_TASK_<TASK>_PROVIDER` and `EVI_LLM_TASK_<TASK>_MODEL`, request native structured output (OpenRouter `response_format` `json_schema` strict, Ollama `format`, Gemini `responseSchema` with field order), validate the answer against the schema and return nothing on timeout, provider error or invalid output. It SHALL NOT fall back to a different provider unless `EVI_LLM_TASK_<TASK>_FALLBACK` names it.

#### Scenario: SCN-LLM-TASK-01
- **GIVEN** `EVI_LLM_TASK_PROMISE_PROVIDER=gemini`
- **WHEN** the promise task runs
- **THEN** the request goes to Gemini with a response schema, and no other task changes provider

#### Scenario: SCN-LLM-TASK-02
- **GIVEN** the task provider is Ollama, Ollama is down and no fallback is set
- **WHEN** the promise task runs
- **THEN** it returns nothing and no request leaves the machine

### Requirement: OpenRouter requests are zero-retention and capped
Every OpenRouter request SHALL carry `provider.zdr=true`, `provider.data_collection="deny"` and `provider.require_parameters=true`, with no setting to disable them. The cost reported in each response (`usage.cost`) SHALL be accumulated per day, and once `EVI_LLM_TASK_DAILY_USD` (default 0.10) is reached `run_structured` SHALL return nothing without calling the provider until the next day.

#### Scenario: SCN-LLM-TASK-03
- **WHEN** the promise task calls OpenRouter
- **THEN** the request body has `zdr: true`, `data_collection: "deny"` and a strict JSON schema

#### Scenario: SCN-LLM-TASK-04
- **GIVEN** today's accumulated cost equals the daily cap
- **WHEN** a structured task runs
- **THEN** no request is sent and the task returns nothing
