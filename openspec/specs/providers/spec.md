# Modular Providers

## Purpose

Abstract the three hard-coupling axes in EVI — LLM, orchestration, and messaging — so
each can be swapped via environment variable without changing tool or service code.
## Requirements
### Requirement: LLM factory
`build_llm()` in `agent/llm.py` SHALL return a `BaseChatModel` instance selected by
`EVI_LLM_PROVIDER` (default `ollama`). Supported: `ollama`, `gemini`, `openai`, `anthropic`.

#### Scenario: SCN-PROV-01
- **GIVEN** `EVI_LLM_PROVIDER` is unset or `ollama`
- **WHEN** `build_llm()` is called
- **THEN** a `ChatOllama` instance is returned using `OLLAMA_MODEL` and `OLLAMA_BASE_URL`

#### Scenario: SCN-PROV-02
- **GIVEN** `EVI_LLM_PROVIDER=gemini` and `GEMINI_API_KEY` is set
- **WHEN** `build_llm()` is called
- **THEN** a `ChatGoogleGenerativeAI` instance is returned

### Requirement: Embeddings factory
`build_embeddings()` SHALL return an `Embeddings` instance selected by `EVI_EMBED_PROVIDER`
(default `ollama`). Supported: `ollama`, `google`, `openai`.

#### Scenario: SCN-PROV-03
- **GIVEN** `EVI_EMBED_PROVIDER` is unset or `ollama`
- **WHEN** `build_embeddings()` is called
- **THEN** an `OllamaEmbeddings` instance is returned

### Requirement: LLM consumer decoupling
`graph.py`, `rag_tool.py`, and `whatsapp_llm_extract.py` SHALL call `build_llm()` /
`build_embeddings()` instead of hardcoding provider imports.

#### Scenario: SCN-PROV-04
- **WHEN** `EVI_LLM_PROVIDER` changes between restarts
- **THEN** the LangGraph agent uses the new provider without code changes

#### Scenario: SCN-PROV-04b
- **WHEN** `./scripts/evi-test smoke` runs with `EVI_LLM_PROVIDER` unset
- **THEN** all 13 smoke checks pass (Ollama default path)

### Requirement: Integration protocol
`agent/integrations/base.py` SHALL define `BaseIntegrationClient` as a `Protocol`.
`get_integration()` SHALL return a `WindmillClient` when `EVI_ORCHESTRATOR=windmill` (default).

#### Scenario: SCN-PROV-05
- **GIVEN** `EVI_ORCHESTRATOR=windmill` (default)
- **WHEN** `get_integration()` is called
- **THEN** a `WindmillClient` instance is returned

#### Scenario: SCN-PROV-06
- **GIVEN** `EVI_ORCHESTRATOR` is set to an unknown value
- **WHEN** `get_integration()` is called
- **THEN** a `ValueError` is raised

### Requirement: Windmill backend
`WindmillClient.post()` SHALL resolve Windmill URLs from env vars, apply OAuth retry
on HTTP 401/422, and support `wait_result` URL rewriting.

#### Scenario: SCN-PROV-07
- **WHEN** `WindmillClient.post("schedule_event", payload)` is called
- **THEN** the request targets the URL from `WINDMILL_WEBHOOK_CALENDAR`

### Requirement: Orchestration consumer decoupling
`calendar_tool.py`, `task_tool.py`, and `email_tool.py` SHALL call `get_integration().post(...)`
instead of importing `post_windmill` directly.

#### Scenario: SCN-PROV-07b
- **WHEN** `python -m pytest tests/unit/test_integration_factory.py -q` runs
- **THEN** all factory and delegation tests pass

### Requirement: Messaging protocol
`agent/messaging/base.py` SHALL define `BaseMessagingClient` as a `Protocol`.
`get_messaging()` SHALL return an `EvolutionClient` when `EVI_WHATSAPP_PROVIDER=evolution` (default).

#### Scenario: SCN-PROV-08
- **GIVEN** `EVI_WHATSAPP_PROVIDER=evolution` (default)
- **WHEN** `get_messaging()` is called
- **THEN** an `EvolutionClient` instance is returned

#### Scenario: SCN-PROV-09
- **GIVEN** `EVI_WHATSAPP_PROVIDER` is set to an unknown value
- **WHEN** `get_messaging()` is called
- **THEN** a `ValueError` is raised

### Requirement: Messaging backward compat shim
`agent/services/evolution_client.py` SHALL remain as a re-exporter so existing callers
(`send_whatsapp_text`, `format_evi_whatsapp`, `is_evi_bot_message`) continue to work
without modification.

#### Scenario: SCN-PROV-10
- **WHEN** existing code calls `from services.evolution_client import send_whatsapp_text`
- **THEN** the call succeeds and delegates to `messaging.evolution.EvolutionClient`

### Requirement: Provider selection without global state mutation
`build_llm` SHALL accept an explicit `provider` argument that takes precedence over `EVI_LLM_PROVIDER`, and `build_background_llm` SHALL use it instead of temporarily writing `os.environ["EVI_LLM_PROVIDER"]`. Building a background LLM SHALL NOT be observable by a concurrent chat turn. Callers that parse a background response SHALL pass `provider=background_provider()` to `extract_llm_text`, so the content shape matches the model that produced it.

#### Scenario: SCN-PROV-04
- **WHEN** `tests/unit/test_llm_factory.py` builds a background LLM with `EVI_BACKGROUND_LLM_PROVIDER` set to a non-Ollama provider
- **THEN** `os.environ["EVI_LLM_PROVIDER"]` is unchanged before, during and after the call, and the chat provider is never consulted

### Requirement: Pinned runtime dependencies
The agent image SHALL install from a pinned `agent/requirements.txt` (`==` versions) rather than unpinned `pip install` arguments, and SHALL NOT run `uvicorn --reload` as its default command.

#### Scenario: SCN-OPS-05
- **WHEN** `agent/Dockerfile` is inspected
- **THEN** dependencies come from `requirements.txt` with pinned versions and `CMD` has no `--reload`

### Requirement: Soft failures are logged
Non-fatal `except Exception` paths that intentionally continue SHALL log a warning through `services/soft_fail.py` with a stable `module.function` context label, instead of silently passing. No such path may start raising.

#### Scenario: SCN-OPS-06
- **WHEN** an optional side effect (contact memory, graph sync, capture notify, profile update) raises
- **THEN** the request still succeeds and a `soft-fail <context>: <ExcType>: <message>` warning is emitted
- **AND** `grep -rzoP "except Exception:\s*\n\s*pass" agent/` returns nothing

