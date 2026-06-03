# Tasks: evi-windmill-orchestration

- [x] 1.1 Windmill compose + postgres windmill DB
  - Files: docker-compose.yml, scripts/postgres-init/01-windmill-db.sql
  - Verify: docker compose config

- [x] 1.2 windmill_client + tool URL migration
  - Files: agent/tools/windmill_client.py, calendar_tool.py, task_tool.py, email_tool.py
  - Verify: ./scripts/evi-test calendar

- [x] 1.3 windmill/f scripts + README
  - Files: windmill/README.md, windmill/f/integrations/*.py
  - Verify: manual

- [x] 1.4 integrations-windmill spec + .env.example
  - Files: openspec/specs/integrations-windmill/spec.md, .env.example
  - Verify: openspec validate evi-windmill-orchestration
