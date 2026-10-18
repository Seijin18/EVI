## MODIFIED Requirements

### Requirement: Daily read-only production probe
`POST /jobs/probe` SHALL call the production integration path for today's events, one task, one inbox message, Telegram `getMe` and the WhatsApp session state (Evolution `connectionState`, when `EVI_SOURCE_ALERTS_ENABLED` is not `false`), without the LLM and without any write operation, record each check in `probe_log` and in the per-source status, and notify the user at most once per day per failing check with its reason. The OAuth warning SHALL explain that an app in Google "Testing" mode expires access every 7 days and how to stop it (publish the app to Production).

#### Scenario: SCN-USE-06
- **WHEN** the Gmail check fails with `reason=oauth` on two probe runs in the same day
- **THEN** exactly one Telegram warning is sent, naming Gmail and the reconnect path

#### Scenario: SCN-USE-09
- **GIVEN** Evolution reports `close`
- **WHEN** the probe runs twice in the same day
- **THEN** the `whatsapp` check is recorded as failed with `reason=disconnected` and exactly one warning is sent
