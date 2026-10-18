## ADDED Requirements

### Requirement: The morning briefing suggests one unused capability
When `EVI_BRIEFING_TIPS` is not `false`, the morning briefing SHALL end with at most one tip line about a capability the user has not used in the last 14 days (reminders, voice, contact knowledge, buttons), with a ready-to-copy example, rotating daily among unused ones; when every capability was used, no tip SHALL be shown. The tip SHALL be the first line dropped when the briefing exceeds its line budget.

#### Scenario: SCN-TIP-01
- **GIVEN** no reminder was created in the last 14 days
- **WHEN** the morning briefing is assembled
- **THEN** its last line is a tip with an example reminder request

#### Scenario: SCN-TIP-02
- **GIVEN** the user created a reminder yesterday, sent a voice message last week, and used buttons and contact knowledge
- **WHEN** the morning briefing is assembled
- **THEN** it has no tip line

### Requirement: The evening preview offers a reminder for tomorrow's items
The evening briefing (`kind=evening`, scheduled at 21:00) SHALL list tomorrow's events, tasks and dated items, and each item due tomorrow SHALL offer an action that creates a reminder for 09:00 tomorrow with the item's title, through the same code as `create_reminder`.

#### Scenario: SCN-TIP-03
- **GIVEN** a task due tomorrow is item 1 of tonight's preview
- **WHEN** the user taps "1 🔔" (or replies "lembra 1")
- **THEN** a reminder for 09:00 tomorrow with the task's title is created and the tap is answered

#### Scenario: SCN-TIP-04
- **WHEN** the Windmill schedules are listed
- **THEN** `briefing_evening` runs at 21:00 America/Sao_Paulo with `kind=evening` and is enabled
