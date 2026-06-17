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
