## ADDED Requirements

### Requirement: The Monday briefing lists people who have not replied to the user
When `EVI_AWAITING_ENABLED` is not `false`, the Monday morning briefing SHALL list, oldest first and at most 3, direct conversations where the user spoke last between `EVI_AWAITING_DAYS` (default 3) and 30 days ago with a question or request, excluding closings, channels, the control chat and messages the user chose to ignore. Each item SHALL show the person, how long ago and a short excerpt of the user's message, and SHALL offer "ignore" and "remind me tomorrow". The EVI SHALL NOT send any message to the contact.

#### Scenario: SCN-AWAIT-01
- **GIVEN** the user asked Bruno "consegue me mandar o contrato?" 4 days ago and Bruno has not written since
- **WHEN** the Monday briefing is assembled
- **THEN** it lists Bruno with "há 4 d" and the excerpt of the question

#### Scenario: SCN-AWAIT-02
- **GIVEN** the user's last message to Carla 5 days ago was "valeu, abraço!"
- **WHEN** the Monday briefing is assembled
- **THEN** Carla is not listed

#### Scenario: SCN-AWAIT-03
- **WHEN** the user taps "N ✖" on Bruno's item
- **THEN** Bruno is not listed again until the user sends him a new message

#### Scenario: SCN-AWAIT-04
- **WHEN** the user taps "N 🔔" on Bruno's item
- **THEN** a reminder for 09:00 tomorrow to follow up with Bruno is created and no message is sent to Bruno
