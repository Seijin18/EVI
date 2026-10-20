## ADDED Requirements

### Requirement: Telegram reactions are feedback on a chat reply
The Telegram poller and webhook SHALL request and accept `message_reaction` updates. A 👍 or 👎 reaction on a chat reply SHALL set `feedback` (`bom` or `ruim`) on the turn that produced that message, identified by the stored Telegram message id, and the weekly report SHALL count it with `/bom` and `/ruim`. Other emojis, unknown messages and reactions from other chats SHALL be ignored.

#### Scenario: SCN-PREC-09
- **GIVEN** the EVI answered a scheduling turn with Telegram message 4321
- **WHEN** the user reacts 👎 to message 4321
- **THEN** that turn has `feedback='ruim'`
