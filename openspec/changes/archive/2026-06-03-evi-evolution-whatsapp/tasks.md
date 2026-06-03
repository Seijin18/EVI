# Tasks: evi-evolution-whatsapp

- [x] 2.1 evolution-api service + global webhook URL
  - Files: docker-compose.yml
  - Verify: docker compose config

- [x] 2.2 evolution_parser + webhook route
  - SCN-WA-04
  - Files: agent/services/evolution_parser.py, agent/main.py
  - Verify: ./scripts/evi-test evolution

- [x] 2.3 Fixture + message_sources evolution
  - Files: tests/fixtures/evolution/messages_upsert.json, message_sources.py
  - Verify: ./scripts/evi-test evolution
