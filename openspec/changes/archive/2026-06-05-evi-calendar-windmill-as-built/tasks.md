# Tasks: evi-calendar-windmill-as-built

- [x] 1.1 Delta spec integrations-windmill
  - Files: openspec/changes/evi-calendar-windmill-as-built/specs/integrations-windmill/spec.md
  - Verify: openspec validate evi-calendar-windmill-as-built

- [x] 1.2 Sync main spec from delta
  - Files: openspec/specs/integrations-windmill/spec.md
  - Verify: openspec validate --specs

- [x] 1.3 Harden evi-test calendar live check
  - Files: agent/testing/cli.py
  - Verify: ./scripts/evi-test calendar

- [x] 1.4 Document calendar env in .env.example
  - Files: .env.example
  - Verify: ./scripts/evi-test calendar
