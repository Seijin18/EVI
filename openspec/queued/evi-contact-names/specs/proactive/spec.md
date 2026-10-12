## ADDED Requirements

### Requirement: The Monday briefing asks for missing contact names
The Monday briefing SHALL list at most 3 direct conversations with at least 3 messages in the last 14 days and no name, each with the number, an excerpt of the contact's last message (wrapped as external data) and, when available, a suggested name. Replying "nomeia N <nome>" SHALL set that name as user-defined; "ignora N" SHALL stop asking about it for 90 days.

#### Scenario: SCN-NAME-05
- **GIVEN** an unnamed contact with 5 messages this week
- **WHEN** the Monday briefing is sent and the user replies "nomeia 1 Hollmann"
- **THEN** the contact is named "Hollmann" and is not asked about again

### Requirement: Suggested names need literal evidence
A suggested name SHALL come from the structured LLM task `CONTACT_NAME_HINT` only when the contact introduced or signed themselves, and SHALL be discarded unless its evidence appears literally in one of the contact's messages. A suggestion SHALL never be stored without the user's confirmation.

#### Scenario: SCN-NAME-06
- **GIVEN** the contact wrote "Abs, Pedro" and the LLM suggests "Paulo"
- **WHEN** the suggestion is validated
- **THEN** it is discarded
