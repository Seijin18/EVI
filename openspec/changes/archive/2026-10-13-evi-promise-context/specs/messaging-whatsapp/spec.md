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
When `EVI_REPLY_DEBTS_ENABLED=true`, a `fromMe` message in a direct conversation matching a versioned list of promise patterns SHALL be stored at once as a `pending_commitments` row with `type='promise'`, `source='whatsapp_from_me'` and `status='needs_eval'`, which is never listed, briefed or notified. When `EVI_PROMISE_CONTEXT_ENABLED=true` (default), the row SHALL be evaluated outside the webhook request no earlier than `EVI_PROMISE_EVAL_DELAY_MIN` (default 30) minutes after the message, with up to 10 messages of the previous 24 hours and the messages that followed (both sides; third-party text wrapped as external data). The evaluation SHALL use the structured LLM task `PROMISE`; the LLM SHALL return the deadline as the expression used in the conversation and the code SHALL resolve it to a date. A confirmed, unfulfilled promise SHALL become `pending` with a title naming what was promised; a rejected one SHALL become `dismissed`; a fulfilled one SHALL become `done`. When the evaluation fails it SHALL be retried, and a row still `needs_eval` after 48 hours SHALL become `pending` with the message as title (a deadline already in the past is dropped so the row is listed). Rejections by the evaluation are not counted as user actions in usage metrics, and rows still waiting are never exposed by any listing, count or agent tool. When the flag is turned off, rows waiting for evaluation are released to `pending`. When the flag is off, the row SHALL be stored as `pending` from the pattern alone, with a resolved date when the message has one.

#### Scenario: SCN-DEBT-04
- **WHEN** the user sends "te mando a proposta amanhã" to a contact
- **THEN** a pending promise for that contact is stored with tomorrow's date

#### Scenario: SCN-DEBT-10
- **GIVEN** the contact Ana wrote "consegue me mandar o orçamento até sexta?"
- **WHEN** the user replies "Pode deixar" and the evaluation runs
- **THEN** a pending promise is stored whose title mentions the budget, due on Friday

#### Scenario: SCN-DEBT-11
- **GIVEN** the contact wrote "valeu pela ajuda ontem!"
- **WHEN** the user replies "Pode deixar, qualquer coisa te aviso" and the evaluation runs
- **THEN** no pending promise is listed

#### Scenario: SCN-DEBT-12
- **GIVEN** the LLM times out on every attempt
- **WHEN** the user sends "te mando a proposta amanhã"
- **THEN** the promise is not listed while it waits for evaluation and is listed, with the message as title, 48 hours later (its resolved date is kept only if it has not passed by then)

#### Scenario: SCN-DEBT-14
- **GIVEN** today is Monday 2026-10-12
- **WHEN** a confirmed promise says "te entrego até dia 20"
- **THEN** its due date is 2026-10-20

#### Scenario: SCN-DEBT-15
- **GIVEN** the contact asked "me passa o contato do eletricista?"
- **WHEN** the user replies "Já te passo" and sends the phone number 2 minutes later
- **THEN** no pending promise is listed

## ADDED Requirements

### Requirement: Fulfilled promises are closed daily
Once a day, before the morning briefing, each `pending` promise whose conversation has new messages from the user SHALL be re-evaluated for fulfilment only, and SHALL become `done` when the LLM finds it fulfilled.

#### Scenario: SCN-DEBT-16
- **GIVEN** a pending promise "Mandar o link do drive" from yesterday and a drive link the user sent to that contact last night
- **WHEN** the daily sweep runs
- **THEN** the promise is `done` and not in the briefing

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
