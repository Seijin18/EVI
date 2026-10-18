## MODIFIED Requirements

### Requirement: A failing source degrades one section, not the briefing
Each source SHALL be collected independently. When a source fails (OAuth expired, Windmill unreachable, timeout), its section SHALL render as `⚠ <fonte> indisponível — <motivo>` using the `ToolResult.reason`/`detail`, and the remaining sections SHALL be delivered. When `EVI_SOURCE_ALERTS_ENABLED` is not `false`, every source that is down SHALL also be listed in one line per source (Google sources grouped) right below the header, with the date it went down and the action to restore it; this banner SHALL never be collapsed by the volume rule.

#### Scenario: SCN-BRIEF-02
- **GIVEN** the Gmail source returns an OAuth error and the other sources succeed
- **WHEN** the briefing is assembled
- **THEN** the email section shows the warning with the reason and the calendar, tasks and WhatsApp sections are complete

#### Scenario: SCN-BRIEF-05
- **GIVEN** WhatsApp has been disconnected since 2026-10-14 and the Google OAuth expired on 2026-10-18
- **WHEN** the morning briefing of 2026-10-18 is assembled
- **THEN** the first lines after the header say WhatsApp is disconnected since 14/10 with how to reconnect, and Google access expired on 18/10 with how to reconnect
