## MODIFIED Requirements

### Requirement: Briefing feedback is recorded
Tapping 👍 or 👎 on a briefing, or reacting 👍 or 👎 to the briefing message in Telegram, SHALL store the rating for that briefing's day and kind (last one wins) and the weekly report SHALL show the count of each. Reactions SHALL be accepted only from the authorised chat; other emojis and unknown messages SHALL be ignored.

#### Scenario: SCN-UX-09
- **WHEN** the user taps 👎 and then 👍 on today's briefing
- **THEN** today's briefing is stored with feedback `up`

#### Scenario: SCN-PREC-08
- **WHEN** the user reacts 👎 to today's briefing message and later changes the reaction to 👍
- **THEN** today's briefing is stored with feedback `up`, and a reaction from another chat changes nothing
