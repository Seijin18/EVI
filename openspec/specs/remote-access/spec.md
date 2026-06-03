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

### Requirement: API key
When `EVI_API_KEY` is set, protected routes SHALL require `X-Api-Key` header.

#### Scenario: SCN-AUTH-01
- **WHEN** protected route is called without matching key
- **THEN** HTTP 401 is returned

### Requirement: Live WhatsApp API deferred
The system SHALL NOT require Meta Cloud or Twilio for current verification; Evolution + fixtures cover WhatsApp.

#### Scenario: SCN-WA-DEF-01
- **WHEN** OpenSpec archive for messaging is validated
- **THEN** fixture and Evolution paths are sufficient without live carrier API
