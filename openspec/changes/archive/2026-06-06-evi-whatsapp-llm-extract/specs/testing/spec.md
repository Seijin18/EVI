## ADDED Requirements

### Requirement: LLM extract unit traceability
The project SHALL map SCN-WA-16 to a unit test with mocked Ollama (no network).

#### Scenario: SCN-WA-16 trace
- **WHEN** `pytest tests/unit/test_whatsapp_llm_extract.py` runs
- **THEN** fallback extraction for w005 passes with mocked LLM
