# Remote access

## Purpose

Telegram and API-key gated access to EVI chat from outside the LAN.

## Requirements

### Requirement: Telegram webhook
The system SHALL accept Telegram updates at `POST /webhooks/telegram` and route text to `/chat` with session `telegram-{chat_id}`.

#### Scenario: SCN-TG-01
- **GIVEN** fixture `tests/fixtures/telegram/update.json`
- **WHEN** `evi-test telegram` runs
- **THEN** parse validates message.text exists

#### Scenario: SCN-TG-02
- **WHEN** `POST /webhooks/telegram` processes a text message with `TELEGRAM_BOT_TOKEN` set
- **THEN** agent replies via Telegram `sendMessage` to the update `chat.id` (`telegram_sent: true`)

### Requirement: API key
When `EVI_API_KEY` is set, protected routes SHALL require `X-Api-Key` header.

#### Scenario: SCN-AUTH-01
- **WHEN** protected route is called without matching key
- **THEN** HTTP 401 is returned

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

### Requirement: Live WhatsApp API deferred
The system SHALL NOT require Meta Cloud or Twilio for current verification; Evolution + fixtures cover WhatsApp.

#### Scenario: SCN-WA-DEF-01
- **WHEN** OpenSpec archive for messaging is validated
- **THEN** fixture and Evolution paths are sufficient without live carrier API
