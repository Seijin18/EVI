## ADDED Requirements

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
