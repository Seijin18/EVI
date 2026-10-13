## MODIFIED Requirements

### Requirement: Reply debts are computed deterministically
A conversation SHALL be a reply debt when its last inbound message is newer than the user's last outbound message and than its acknowledgement, is older than `EVI_REPLY_DEBT_HOURS` (default 4) and younger than 7 days, and is not a closing-only message ("ok", "valeu", "obrigado", "joia", "tranquilo", "fechou", approval emoji only, or a thanks followed by a short vocative such as "obrigado, Marcão!"). No LLM SHALL be used. `dismiss_reply_debt` SHALL acknowledge a debt until a new inbound message arrives.

#### Scenario: SCN-DEBT-01
- **GIVEN** a contact wrote "consegue me mandar o orçamento?" 6 hours ago and the user did not reply
- **WHEN** reply debts are listed
- **THEN** that conversation is listed with the contact name and the preview

#### Scenario: SCN-DEBT-03
- **GIVEN** the last inbound message of a conversation is "valeu 👍"
- **WHEN** reply debts are listed
- **THEN** that conversation is not listed

#### Scenario: SCN-UX-05
- **GIVEN** the last inbound messages of two conversations are "Joia" and "obrigado, Marcão!"
- **WHEN** reply debts are listed
- **THEN** neither conversation is listed
