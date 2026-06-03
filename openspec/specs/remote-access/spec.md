# Remote access

## ADDED Requirements

### Requirement: Telegram webhook
The system SHALL accept Telegram updates at `POST /webhooks/telegram` and route text to `/chat` with session `telegram-{chat_id}`.

#### Scenario: SCN-TG-01
- **GIVEN** fixture `tests/fixtures/telegram/update.json`
- **WHEN** `evi-test telegram` runs
- **THEN** parse validates message.text exists

### Requirement: API key
When `EVI_API_KEY` is set, protected routes SHALL require `X-Api-Key` header.

## REMOVED Requirements

### Requirement: Live WhatsApp API
Deferred until channel selection (Meta Cloud API, Twilio, export ingest).
