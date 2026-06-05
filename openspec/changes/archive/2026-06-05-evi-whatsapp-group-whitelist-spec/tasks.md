# Tasks: evi-whatsapp-group-whitelist-spec

- [x] 1.1 Apply messaging-whatsapp delta to main spec
  - Files: openspec/specs/messaging-whatsapp/spec.md
  - Verify: openspec validate evi-whatsapp-group-whitelist-spec

- [x] 1.2 Apply testing delta
  - Files: openspec/specs/testing/spec.md
  - Verify: pytest tests/unit/test_evolution_filter.py -q

- [x] 1.3 Note whitelist in .env.example
  - Files: .env.example
  - Verify: ./scripts/evi-test evolution
