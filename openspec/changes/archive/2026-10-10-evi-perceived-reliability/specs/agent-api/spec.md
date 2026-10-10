## ADDED Requirements

### Requirement: Downtime is reported from outside the agent
`scripts/evi-watchdog`, run every minute by a user systemd timer, SHALL call the agent's `/health`; after two consecutive failures (`status` `down`, HTTP error or timeout) it SHALL send one Telegram alert directly through the Bot API, and one recovery message when health returns. It SHALL read only `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `.env` and SHALL NOT depend on the agent process.

#### Scenario: SCN-REL-01
- **GIVEN** `/health` fails on three consecutive runs and then succeeds
- **WHEN** the watchdog runs four times
- **THEN** exactly one alert is sent after the second run and one recovery message after the fourth

### Requirement: Help is deterministic
`/ajuda`, `/help` and the question "o que você pode fazer?" SHALL be answered without an LLM call, with 6–8 example requests for the features currently enabled.

#### Scenario: SCN-REL-02
- **WHEN** the user sends "/ajuda" with reminders enabled and voice disabled
- **THEN** the reply lists a reminder example, no voice example, and no LLM call is made

### Requirement: Slow tools are acknowledged
When `EVI_SLOW_ACK_SEC` is greater than 0 and a tool call in a Telegram or control-chat turn runs longer than it, the user SHALL receive "⏳ fazendo…" once per turn before the final reply. API and test turns SHALL NOT receive it.

#### Scenario: SCN-REL-03
- **GIVEN** `EVI_SLOW_ACK_SEC=5` and a Windmill call that takes 12 s
- **WHEN** the user asks to summarize the inbox on Telegram
- **THEN** one "⏳" message arrives before the summary

### Requirement: Expired OAuth is reported when the user hits it
When a tool result is classified `reason=oauth`, the user SHALL be told which integration needs reconnection and how, at most once per integration per day, sharing the daily claim used by the probe.

#### Scenario: SCN-REL-04
- **WHEN** two turns on the same day hit an expired Gmail credential and the probe also fails Gmail that morning
- **THEN** exactly one reconnection warning for Gmail is sent that day
