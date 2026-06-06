## ADDED Requirements

### Requirement: LLM fallback extraction
When `EVI_WHATSAPP_LLM_EXTRACT` is true and heuristic extraction returns no commitment, the processor SHALL attempt Ollama structured extraction before discarding the message.

#### Scenario: SCN-WA-16
- **GIVEN** fixture message w005 (consultation scheduling) and `EVI_WHATSAPP_LLM_EXTRACT=true`
- **WHEN** `extract_commitment_with_fallback` runs with mocked LLM returning valid JSON
- **THEN** a commitment with `type`, `title`, and date/time fields is produced
