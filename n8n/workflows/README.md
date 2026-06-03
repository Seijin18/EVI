# n8n workflows

Export workflows from the n8n UI (http://localhost:5678) and save JSON here:

| File | Webhook path | Purpose |
|------|--------------|---------|
| `calendar.json` | `/webhook/calendar` | Google Calendar events |
| `tasks.json` | `/webhook/tasks` | Google Tasks create |
| `email.json` | `/webhook/email` | Gmail summarize |
| `telegram.json` | — | Telegram → agent-api `/webhooks/telegram` |

Test webhooks: `./scripts/evi-test calendar --live-n8n`
