# Design

## Deploy

- `docker-compose.yml`: `EVI_WORKSPACE=/workspace`, volume `./EVI_WORKSPACE:/workspace`, `WINDMILL_WEBHOOK_EMAIL_DELETE_QUERY`, `EVI_DIRECT_HANDLERS`, `EVI_WHATSAPP_REQUIRE_TS`.
- `.env` local: alinhar vars v3 (não commitar).

## Tier 2

- `run_runtime_v3`: workspace files, context assembly, skills, heartbeat dry, registry wiring.
- `run_inbox_ux`: format inbox messages[], delete_by_query mock, snapshot round-trip (DB ou mock).
- Smoke: 14 checks incluindo `runtime-v3`.

## Tier 1

- `test_whatsapp_control` / `test_telegram_handler`: direct handlers só com `EVI_DIRECT_HANDLERS=true`; LLM-first default.
- `test_chat_invoke`: mock graph, extra_context, tools[], snapshots.

## Live

- `scripts/evi-inbox-ux-verify.sh`: inbox-ux + runtime-v3 + email live + chat.
