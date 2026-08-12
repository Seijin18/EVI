## ADDED Requirements

### Requirement: Provider selection without global state mutation
`build_llm` SHALL accept an explicit `provider` argument that takes precedence over `EVI_LLM_PROVIDER`, and `build_background_llm` SHALL use it instead of temporarily writing `os.environ["EVI_LLM_PROVIDER"]`. Building a background LLM SHALL NOT be observable by a concurrent chat turn.

#### Scenario: SCN-PROV-04
- **WHEN** `tests/unit/test_llm_factory.py` builds a background LLM with `EVI_BACKGROUND_LLM_PROVIDER` set to a non-Ollama provider
- **THEN** `os.environ["EVI_LLM_PROVIDER"]` is unchanged before, during and after the call

### Requirement: Pinned runtime dependencies
The agent image SHALL install from a pinned `agent/requirements.txt` (`==` versions) rather than unpinned `pip install` arguments, and SHALL NOT run `uvicorn --reload` as its default command.

#### Scenario: SCN-OPS-05
- **WHEN** `agent/Dockerfile` is inspected
- **THEN** dependencies come from `requirements.txt` with pinned versions and `CMD` has no `--reload`

### Requirement: Soft failures are logged
Non-fatal `except Exception` paths that intentionally continue SHALL log a warning with a stable context label via a shared helper, instead of silently passing.

#### Scenario: SCN-OPS-06
- **WHEN** an optional side effect (contact memory, graph sync, capture notify, profile update) raises
- **THEN** the request still succeeds and a warning line identifying the failing context is emitted
