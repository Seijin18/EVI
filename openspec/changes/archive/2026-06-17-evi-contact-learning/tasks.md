## 1. Implementation

- [x] 1.1 Contact tools + backfill + learning services
  - Files: `agent/tools/contact_tool.py`, `agent/services/whatsapp_backfill.py`, `agent/services/contact_learning.py`
  - Verify: `./scripts/evi-test contact-learning`

- [x] 1.2 Skill + registry + graph prompt
  - Files: `agent/services/skill_loader.py`, `agent/tools/registry.py`, `agent/graph.py`
  - Verify: `./scripts/evi-test runtime-v3`

- [x] 1.3 Spec delta + docs
  - Files: `docs/evolution.md`, `openspec/changes/evi-contact-learning/specs/data-long-memory/spec.md`
  - Verify: `openspec validate evi-contact-learning`

- [x] 1.4 Evolution contact/chat discovery
  - Files: `agent/services/evolution_discovery.py`, `agent/services/whatsapp_activity.py`, `agent/messaging/evolution.py`
  - Verify: `tests/unit/test_evolution_discovery.py`

- [x] 1.5 Webhook-ingest backfill + commitment replay
  - Files: `agent/services/message_timeline.py`, `agent/services/whatsapp_backfill.py`, `agent/services/commitment_replay.py`
  - Verify: `tests/unit/test_whatsapp_backfill.py`, `tests/unit/test_commitment_replay.py`

- [x] 1.6 Postgres contact registry (display names + LLM aliases)
  - Files: `agent/db.py`, `agent/services/contact_registry.py`, `agent/tools/contact_tool.py`
  - Verify: `tests/unit/test_contact_registry.py`
