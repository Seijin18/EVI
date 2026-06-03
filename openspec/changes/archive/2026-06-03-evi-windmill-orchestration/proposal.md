## Why

Replace n8n with Windmill for code-first orchestration (wmill sync).

## What Changes

- docker-compose: windmill-server + worker; remove n8n
- windmill/f/integrations scripts
- agent tools use WINDMILL_* webhooks
- spec integrations-windmill

## Out of scope

- Full Google OAuth setup (manual in Windmill UI once)
