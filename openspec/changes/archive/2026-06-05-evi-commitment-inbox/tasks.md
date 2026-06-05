# Tasks

- [x] 1.1 Postgres pending_commitments + db helpers
  - Files: agent/db.py
  - Verify: PYTHONPATH=agent python3 tests/unit/test_commitment_priority.py

- [x] 1.2 Priority on Commitment
  - Files: agent/services/commitment_priority.py, agent/services/whatsapp_processor.py
  - Verify: ./scripts/evi-test whatsapp

- [x] 1.3 Evolution webhook queue insert
  - Files: agent/main.py
  - Verify: ./scripts/evi-test evolution

- [x] 1.4 Spec SCN-WA-10/11
  - Files: openspec/specs/messaging-whatsapp/spec.md
  - Verify: openspec validate --specs
