## MODIFIED Requirements

### Requirement: Downtime is reported from outside the agent
`scripts/evi-watchdog`, run every minute by a user systemd timer, SHALL call the agent's `/health`; after two consecutive failures (`status` `down`, HTTP error or timeout) it SHALL send one Telegram alert directly through the Bot API, and one recovery message when health returns. When `EVI_SOURCE_ALERTS_ENABLED` is not `false`, it SHALL also read the Evolution `connectionState` of the configured instance and, after two consecutive readings other than `open` (Evolution unreachable included), send one alert per outage saying WhatsApp is disconnected and how to reconnect, and one message when it is `open` again. It SHALL read only `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EVOLUTION_API_KEY` and `EVOLUTION_INSTANCE_NAME` from `.env` and SHALL NOT depend on the agent process.

#### Scenario: SCN-REL-01
- **GIVEN** `/health` fails on three consecutive runs and then succeeds
- **WHEN** the watchdog runs four times
- **THEN** exactly one alert is sent after the second run and one recovery message after the fourth

#### Scenario: SCN-REL-03
- **GIVEN** the agent is healthy and Evolution reports `close` on three consecutive runs and then `open`
- **WHEN** the watchdog runs four times
- **THEN** exactly one WhatsApp alert is sent after the second run and one reconnection message after the fourth, and no agent-downtime alert is sent

## ADDED Requirements

### Requirement: Health reports the WhatsApp session
`/health` SHALL include a `whatsapp` check from the Evolution `connectionState`; a state other than `open` SHALL make the overall status `degraded`, never `down`.

#### Scenario: SCN-REL-04
- **GIVEN** Evolution reports `close`
- **WHEN** `/health` is called
- **THEN** the `whatsapp` check is not ok and the status is `degraded`
