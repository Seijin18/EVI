## ADDED Requirements

### Requirement: Direct conversations track who spoke last
For every direct WhatsApp conversation (not a group, not a control chat), the webhook SHALL record the time, id and a 160-character preview of the last inbound message and the time of the last message sent by the user (`fromMe`, excluding EVI's own echoes) in `wa_conversation_state`, before the processing filter runs. Recording `fromMe` messages SHALL NOT feed them into commitment extraction.

#### Scenario: SCN-DEBT-02
- **WHEN** a `fromMe` message arrives for a direct conversation
- **THEN** `last_out_at` is updated, no pending commitment is created from it by the existing extraction, and a group message updates no state

### Requirement: Reply debts are computed deterministically
A conversation SHALL be a reply debt when its last inbound message is newer than the user's last outbound message and than its acknowledgement, is older than `EVI_REPLY_DEBT_HOURS` (default 4) and younger than 7 days, and is not a closing-only message ("ok", "valeu", "obrigado", emoji only). No LLM SHALL be used. `dismiss_reply_debt` SHALL acknowledge a debt until a new inbound message arrives.

#### Scenario: SCN-DEBT-01
- **GIVEN** a contact wrote "consegue me mandar o orçamento?" 6 hours ago and the user did not reply
- **WHEN** reply debts are listed
- **THEN** that conversation is listed with the contact name and the preview

#### Scenario: SCN-DEBT-03
- **GIVEN** the last inbound message of a conversation is "valeu 👍"
- **WHEN** reply debts are listed
- **THEN** that conversation is not listed

### Requirement: The user's own promises are captured by pattern
When `EVI_REPLY_DEBTS_ENABLED=true`, a `fromMe` message in a direct conversation matching a versioned list of promise patterns SHALL create a `pending_commitments` row with `type='promise'` and `source='whatsapp_from_me'`, with a resolved date when the message has one. No LLM SHALL be used.

#### Scenario: SCN-DEBT-04
- **WHEN** the user sends "te mando a proposta amanhã" to a contact
- **THEN** a pending promise for that contact is stored with tomorrow's date

### Requirement: Only dated commitments are surfaced
When `EVI_REPLY_DEBTS_ENABLED=true`, a commitment extracted from an inbound message without a resolved event or due date SHALL be stored with `status='undated'` and SHALL NOT be listed, briefed or notified.

#### Scenario: SCN-DEBT-05
- **WHEN** a contact sends "Jantar" with no date
- **THEN** no pending commitment is listed for it
