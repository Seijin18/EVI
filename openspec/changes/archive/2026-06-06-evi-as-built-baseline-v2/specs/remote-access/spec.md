## ADDED Requirements

### Requirement: Telegram long polling
When `TELEGRAM_MODE=polling`, agent-api SHALL poll Telegram `getUpdates` and route text messages through the same handler as the webhook.

#### Scenario: SCN-TG-04
- **WHEN** `TELEGRAM_MODE=polling` and `TELEGRAM_BOT_TOKEN` are set at startup
- **THEN** `telegram_poller` runs and `process_telegram_update` handles text updates

### Requirement: Telegram direct calendar bypass
For list/review intents, Telegram handler SHALL call calendar or commitment tools directly without invoking the LLM when regex intent matches.

#### Scenario: SCN-TG-05
- **WHEN** user sends "revise agendamentos" or "listar compromissos pendentes" via Telegram
- **THEN** handler returns `list_calendar_events` or `list_pending_commitments` result with `listed_direct: true`
