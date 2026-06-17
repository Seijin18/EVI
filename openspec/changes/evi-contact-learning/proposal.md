## Why

Users need WhatsApp contact knowledge by name/phone (not JID), with Evolution backfill into filesystem memory and LLM synthesis into profile.md.

## What Changes

- Tools: `list_whatsapp_contacts`, `get_whatsapp_contact_info`, `learn_whatsapp_contact`
- Services: `whatsapp_backfill`, `contact_learning`, expanded `contact_filesystem`
- Evolution `findMessages`; skill `contact-learning`; `evi-test contact-learning`

**Out of scope:** Neo4j required; auto-commit; Gemini for synthesis (uses background Ollama).

## Impact

`agent/tools/contact_tool.py`, `agent/services/contact_learning.py`, `openspec/specs/data-long-memory`.
