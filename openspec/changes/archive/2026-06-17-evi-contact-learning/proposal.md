## Why

Users need WhatsApp contact knowledge by name/phone (not JID), with Evolution backfill into filesystem memory and LLM synthesis into profile.md. During implementation this grew to also cover a Postgres contact registry (display names/aliases searchable independently of JID), Evolution-side contact/chat discovery (`findContacts`/`findChats`), and replaying commitments/timeline entries from the webhook ingest log when the Evolution cache lags.

## What Changes

- Tools: `list_whatsapp_contacts`, `get_whatsapp_contact_info`, `learn_whatsapp_contact`, `set_whatsapp_contact_name`
- Services: `whatsapp_backfill`, `contact_learning`, `contact_registry` (Postgres `whatsapp_contacts`), `evolution_discovery`, `whatsapp_activity`, `message_timeline`, `commitment_replay`, expanded `contact_filesystem`
- Evolution client: `findMessages`, `findContacts`, `findChats`
- Skill `contact-learning`; `evi-test contact-learning`

**Out of scope:** Neo4j required; auto-commit; Gemini for synthesis (uses background Ollama).

## Impact

`agent/tools/contact_tool.py`, `agent/services/contact_learning.py`, `agent/services/contact_registry.py`, `agent/services/evolution_discovery.py`, `agent/services/commitment_replay.py`, `agent/services/message_timeline.py`, `openspec/specs/data-long-memory`.
