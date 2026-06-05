## ADDED Requirements

### Requirement: WhatsApp group whitelist
When `EVI_WHATSAPP_SKIP_GROUPS` is true, the Evolution filter SHALL allow messages from group JIDs listed in `EVI_WHATSAPP_GROUP_WHITELIST` (comma-separated `@g.us` ids) and SHALL ignore other groups.

#### Scenario: SCN-WA-06
- **GIVEN** whitelist contains `120363012345678901@g.us`
- **WHEN** filter runs on a group message with that JID
- **THEN** message is retained for processing

#### Scenario: SCN-WA-07
- **GIVEN** whitelist contains `120363012345678901@g.us`
- **WHEN** filter runs on a different `@g.us` JID
- **THEN** message is skipped as a group

### Requirement: Evolution groupsIgnore coordination
When `EVI_WHATSAPP_GROUP_WHITELIST` is non-empty, `setup-evolution.sh` SHALL set `groupsIgnore=false` so whitelisted groups reach the webhook.

#### Scenario: SCN-WA-08
- **WHEN** setup script runs with non-empty whitelist in environment
- **THEN** Evolution instance config disables `groupsIgnore`
