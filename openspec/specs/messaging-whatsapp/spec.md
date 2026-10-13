# WhatsApp message processing

## Purpose

Extract calendar tasks and events from WhatsApp text via fixtures and Evolution API webhooks.
## Requirements
### Requirement: Fixture pipeline
The processor SHALL read `tests/fixtures/whatsapp/messages.jsonl` and extract commitments without live WhatsApp API.

#### Scenario: SCN-WA-01
- **GIVEN** message w001 (meeting tomorrow 14h)
- **WHEN** extract runs
- **THEN** type=event, date=2026-06-04, time=14:00

#### Scenario: SCN-WA-02
- **GIVEN** message w002 (report by Friday)
- **WHEN** extract runs
- **THEN** type=task, due=2026-06-05 (Friday after ref date 2026-06-03)

#### Scenario: SCN-WA-03
- **GIVEN** message w004 ("Ok, combinado")
- **WHEN** extract runs
- **THEN** no commitment is produced

#### Scenario: SCN-WA-04
- **WHEN** `./scripts/evi-test whatsapp` runs
- **THEN** results match `tests/golden/whatsapp_commitments.json` and JSONL log is written

### Requirement: Evolution API live adapter
The system SHALL accept Evolution API webhooks at `POST /webhooks/evolution` and extract commitments.

#### Scenario: SCN-WA-05
- **WHEN** `evi-test evolution` runs with fixture payload
- **THEN** at least one message is parsed and commitment extracted

### Requirement: WhatsApp group whitelist
When `EVI_WHATSAPP_SKIP_GROUPS` is true, the Evolution filter SHALL allow messages from group JIDs listed in `EVI_WHATSAPP_GROUP_WHITELIST` (comma-separated `@g.us` ids) and SHALL ignore other groups.

#### Scenario: SCN-WA-06
- **GIVEN** whitelist contains `120363012345678901@g.us`
- **WHEN** filter runs on a group message with that JID
- **THEN** message is retained for processing

#### Scenario: SCN-WA-07
- **GIVEN** whitelist contains `120363012345678901@g.us`
- **WHEN** filter runs on a different `@g.us` JID
- **THEN** message is skipped as a group

### Requirement: Evolution groupsIgnore coordination
When `EVI_WHATSAPP_GROUP_WHITELIST` is non-empty, `setup-evolution.sh` SHALL set `groupsIgnore=false` so whitelisted groups reach the webhook.

#### Scenario: SCN-WA-08
- **WHEN** setup script runs with non-empty whitelist in environment
- **THEN** Evolution instance config disables `groupsIgnore`

### Requirement: Pending commitment queue
Extracted commitments from Evolution webhooks SHALL be persisted to Postgres `pending_commitments` with status `pending` and priority classification.

#### Scenario: SCN-WA-10
- **WHEN** Evolution webhook extracts a commitment
- **THEN** a row is inserted (or deduped by source_id) and response includes `queued` count

#### Scenario: SCN-WA-11
- **WHEN** commitment text contains urgency keywords
- **THEN** priority is classified as `urgent`, `work`, or `university` when matched

### Requirement: Evolution webhook log observability
Evolution webhook processing SHALL write JSONL audit lines with processing timestamp `ts` and WhatsApp message time `message_ts` when available.

#### Scenario: SCN-WA-13
- **WHEN** a message is ingested after filtering
- **THEN** log line includes `step: ingest`, `message_ts`, `sender`, `from_me`, `is_group`

#### Scenario: SCN-WA-14
- **WHEN** a parsed message is dropped by `evolution_filter`
- **THEN** log line includes `step: filtered_out`, `reason`, and `message_ts`

#### Scenario: SCN-WA-15
- **WHEN** `messages.upsert` yields zero parsed messages
- **THEN** skip log MAY include `hint: parser_empty_text_or_unsupported_type`

### Requirement: Pending commitment notifications
The system SHALL notify via Telegram when configured and either 5+ unnotified pending items exist or a new item has high priority.

#### Scenario: SCN-WA-12
- **WHEN** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set and notification threshold is met
- **THEN** a digest message is sent via Telegram Bot API

### Requirement: LLM fallback extraction
When `EVI_WHATSAPP_LLM_EXTRACT` is true and heuristic extraction returns no commitment, the processor SHALL attempt Ollama structured extraction before discarding the message.

#### Scenario: SCN-WA-16
- **GIVEN** fixture message w005 (consultation scheduling) and `EVI_WHATSAPP_LLM_EXTRACT=true`
- **WHEN** `extract_commitment_with_fallback` runs with mocked LLM returning valid JSON
- **THEN** a commitment with `type`, `title`, and date/time fields is produced

### Requirement: Evolution filter hardening
The Evolution filter SHALL drop messages without valid timestamps when `EVI_WHATSAPP_REQUIRE_TS=true`, honor `EVI_WHATSAPP_PROCESS_AFTER`, and mark all received message ids as seen.

#### Scenario: SCN-UX-WA-ING-01
- **WHEN** Evolution sends a burst after long downtime
- **THEN** messages outside age/watermark are not extracted

### Requirement: Conservative commitment extraction
Heuristic and LLM extract SHALL reject generic titles and casual group chat without schedule signals.

#### Scenario: SCN-UX-WA-ING-02
- **WHEN** casual group message is processed
- **THEN** no pending commitment is created

### Requirement: Seen-id eviction keeps the newest ids
The WhatsApp dedupe store SHALL evict in insertion order, so trimming to `_MAX_SEEN_IDS` drops the oldest ids and always retains the most recently seen. Trimming an unordered `set` is not permitted — which ids survive is arbitrary, so a just-seen message can be evicted while an older one is kept, letting a duplicate through. The on-disk JSON array format is unchanged, so existing `evolution_seen_ids.json` files keep loading.

#### Scenario: SCN-WA-17
- **GIVEN** `_MAX_SEEN_IDS` seen ids already stored
- **WHEN** a new id is claimed and the store is trimmed
- **THEN** the newest id is still present and the oldest was the one dropped
- **AND** re-claiming the newest id returns False (still deduped)

### Requirement: Direct conversations track who spoke last
For every direct WhatsApp conversation (not a group, not a control chat, not a one-way channel or broadcast — `@newsletter`, `@broadcast`), the webhook SHALL record the time, id and a 160-character preview of the last inbound message and the time of the last message sent by the user (`fromMe`, excluding EVI's own echoes) in `wa_conversation_state`, before the processing filter runs. Recording `fromMe` messages SHALL NOT feed them into commitment extraction. One-way channels SHALL NOT be listed as reply debts.

#### Scenario: SCN-DEBT-02
- **WHEN** a `fromMe` message arrives for a direct conversation
- **THEN** `last_out_at` is updated, no pending commitment is created from it by the existing extraction, and a group message updates no state

#### Scenario: SCN-DEBT-09
- **GIVEN** a WhatsApp Channel (`…@newsletter`) posted 10 hours ago
- **WHEN** reply debts are listed
- **THEN** that channel is not listed

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

### Requirement: Only dated commitments are surfaced
When `EVI_REPLY_DEBTS_ENABLED=true`, a commitment extracted from an inbound message without a resolved event or due date SHALL be stored with `status='undated'` and SHALL NOT be listed, briefed or notified.

#### Scenario: SCN-DEBT-05
- **WHEN** a contact sends "Jantar" with no date
- **THEN** no pending commitment is listed for it

### Requirement: Only the user's own WhatsApp audio is transcribed
`audioMessage` SHALL be parsed and fetched (`getBase64FromMediaMessage`) only when the sender is a configured control JID; it SHALL then be transcribed and handled like a control-chat text message, with the same echo line. Audio from any other sender SHALL NOT be downloaded or transcribed.

#### Scenario: SCN-VOICE-02
- **WHEN** the user sends a voice note to the control chat asking "quais meus compromissos de amanhã?"
- **THEN** the reply lists tomorrow's events and starts with "🎙️ Entendi:"

#### Scenario: SCN-VOICE-05
- **WHEN** a contact sends a voice note in a direct conversation
- **THEN** no media download or transcription happens and nothing is sent to anyone

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

