## MODIFIED Requirements

### Requirement: Direct conversations track who spoke last
For every direct WhatsApp conversation (not a group, not a control chat, not a one-way channel or broadcast — `@newsletter`, `@broadcast`), the webhook SHALL record the time, id and a 160-character preview of the last inbound message and the time of the last message sent by the user (`fromMe`, excluding EVI's own echoes) in `wa_conversation_state`, before the processing filter runs. Recording `fromMe` messages SHALL NOT feed them into commitment extraction. One-way channels SHALL NOT be listed as reply debts.

#### Scenario: SCN-DEBT-02
- **WHEN** a `fromMe` message arrives for a direct conversation
- **THEN** `last_out_at` is updated, no pending commitment is created from it by the existing extraction, and a group message updates no state

#### Scenario: SCN-DEBT-09
- **GIVEN** a WhatsApp Channel (`…@newsletter`) posted 10 hours ago
- **WHEN** reply debts are listed
- **THEN** that channel is not listed

### Requirement: The user's own promises are captured by pattern
When `EVI_REPLY_DEBTS_ENABLED=true`, a `fromMe` message in a direct conversation matching a versioned list of promise patterns SHALL trigger a promise evaluation. When `EVI_PROMISE_CONTEXT_ENABLED=true` (default), the evaluation SHALL run outside the webhook request, read up to 10 messages of that conversation from the previous 24 hours (both sides; third-party text wrapped as external data) and ask the LLM whether the user committed to something; it SHALL store a `pending_commitments` row with `type='promise'` and `source='whatsapp_from_me'` only when the LLM confirms, with a title naming what was promised and to whom and the resolved date when there is one. When the LLM fails or the flag is off, the row SHALL be stored from the pattern alone, with the message as title and a resolved date when the message has one.

#### Scenario: SCN-DEBT-04
- **WHEN** the user sends "te mando a proposta amanhã" to a contact
- **THEN** a pending promise for that contact is stored with tomorrow's date

#### Scenario: SCN-DEBT-10
- **GIVEN** the contact Ana wrote "consegue me mandar o orçamento até sexta?"
- **WHEN** the user replies "Pode deixar"
- **THEN** a pending promise is stored whose title mentions the budget and Ana, due on Friday

#### Scenario: SCN-DEBT-11
- **GIVEN** the contact wrote "valeu pela ajuda ontem!"
- **WHEN** the user replies "Pode deixar, qualquer coisa te aviso"
- **THEN** no pending promise is stored

#### Scenario: SCN-DEBT-12
- **GIVEN** the LLM times out
- **WHEN** the user sends "te mando a proposta amanhã"
- **THEN** a pending promise is stored from the pattern alone, with tomorrow's date

## ADDED Requirements

### Requirement: Existing promises can be re-evaluated with context
A one-off re-evaluation SHALL apply the contextual evaluation to every `type='promise'` row in `status='pending'`, using the conversation around the row's creation: a rejected promise SHALL become `dismissed`, a confirmed one SHALL get the contextual title and date, and a failed evaluation SHALL leave the row unchanged.

#### Scenario: SCN-DEBT-13
- **GIVEN** a pending promise "Pode deixar" whose conversation holds no request
- **WHEN** the re-evaluation runs
- **THEN** that promise is dismissed and no longer listed

### Requirement: Evolution message history is deduplicated
Messages read from Evolution (`findMessages`) SHALL be deduplicated by message id before any listing, summary or backfill uses them.

#### Scenario: SCN-WA-DEDUP-01
- **GIVEN** Evolution returns the same message twice for a chat
- **WHEN** the WhatsApp summary is built
- **THEN** that message appears once in the summary input
