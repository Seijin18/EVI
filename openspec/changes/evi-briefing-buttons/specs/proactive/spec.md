## ADDED Requirements

### Requirement: Briefing items can be acted on with one tap
When `EVI_BRIEFING_BUTTONS` is not `false`, the Telegram briefing SHALL carry inline buttons for each visible actionable item (reply debts, promises and dated commitments, unnamed conversations) and a 👍/👎 row. A button's data SHALL contain only the briefing day, the item number and the action; tapping it SHALL run the same deterministic action as the equivalent numbered text reply, without the LLM, answer the tap and remove that item's buttons. Taps from chats outside the allowlist or for a briefing other than the current one SHALL change nothing.

#### Scenario: SCN-UX-06
- **GIVEN** a morning briefing with one reply debt (item 1) and one promise (item 2)
- **WHEN** it is sent
- **THEN** the message has a button row for item 1, one for item 2 and a 👍/👎 row, and no button data contains a JID, an id or message text

#### Scenario: SCN-UX-07
- **WHEN** the user taps "1 ✅" on today's briefing
- **THEN** the reply debt of item 1 is acknowledged, the tap is answered, item 1's buttons are removed and the briefing counts as replied

#### Scenario: SCN-UX-08
- **WHEN** a tap arrives for yesterday's briefing, or from a chat outside the allowlist
- **THEN** nothing is changed and, for the old briefing, the tap is answered saying it is old

### Requirement: Briefing feedback is recorded
Tapping 👍 or 👎 on a briefing SHALL store the rating for that briefing's day and kind (last tap wins) and the weekly report SHALL show the count of each.

#### Scenario: SCN-UX-09
- **WHEN** the user taps 👎 and then 👍 on today's briefing
- **THEN** today's briefing is stored with feedback `up`
