## 1. LLM extract module

- [x] 1.1 Add `whatsapp_llm_extract.py`
  - Files: `agent/services/whatsapp_llm_extract.py`, `.env.example`
  - Verify: `python3 -c "from services.whatsapp_llm_extract import llm_extract_enabled"`

## 2. Processor fallback

- [x] 2.1 Wire `extract_commitment_with_fallback` in processor
  - Files: `agent/services/whatsapp_processor.py`
  - Verify: `./scripts/evi-test whatsapp --verbose`

## 3. Tests and fixtures

- [x] 3.1 Fixture w005 + unit test SCN-WA-16
  - Files: `tests/fixtures/whatsapp/messages.jsonl`, `tests/unit/test_whatsapp_llm_extract.py`, `docs/testing.md`
  - Verify: `pytest tests/unit/test_whatsapp_llm_extract.py -q`

## 4. Spec merge

- [x] 4.1 Merge delta specs into main specs
  - Files: `openspec/specs/messaging-whatsapp/spec.md`, `openspec/specs/testing/spec.md`
  - Verify: `openspec validate evi-whatsapp-llm-extract`
