## MODIFIED Requirements

### Requirement: Reply debts are computed deterministically
A conversation SHALL be a reply debt when its last inbound message is newer than the user's last outbound message and than its acknowledgement, is older than `EVI_REPLY_DEBT_HOURS` (default 4) and younger than 7 days, and is not a message that needs no reply. Rules SHALL decide first: a closing-only message (vocabulary version 3: "ok", "valeu", "obrigado", "joia", "tranquilo", "fechou", "boa", "massa", "demorou", "isso", "uhum", laughter, approval emoji only, or a thanks followed by a short vocative) is never a debt; a message with a question mark or request wording is always a debt; a message of at most 3 words without request wording sent within 10 minutes after the user's last outbound message is an acknowledgement and is never a debt. Only the remaining ambiguous messages SHALL be judged by the structured LLM task `DEBT` (when `EVI_DEBT_JUDGE` is not `false`), outside the read path, with up to 8 recent messages of the conversation (both sides; third-party text wrapped as external data), and the verdict SHALL be stored for that inbound message id. A message without a verdict (judge off, failed, capped or not yet run) SHALL remain a debt. Listing debts SHALL never call an LLM. A listed debt SHALL carry the user's last outbound message (truncated) as context. `dismiss_reply_debt` SHALL acknowledge a debt until a new inbound message arrives.

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

#### Scenario: SCN-PREC-01
- **GIVEN** the user wrote "Vou esperar essa terminar e aí já subo" and 22 seconds later the contact wrote "Boa"
- **WHEN** reply debts are listed 5 hours later
- **THEN** that conversation is not listed and no LLM was called

#### Scenario: SCN-PREC-02
- **GIVEN** the contact wrote "boa" 3 hours after the user's last message, with no request wording
- **WHEN** reply debts are listed (judge unavailable)
- **THEN** the conversation is not listed because "boa" is a closing word

#### Scenario: SCN-PREC-03
- **GIVEN** a listed debt whose last user message was "Te mando o orçamento hoje"
- **WHEN** the briefing is assembled
- **THEN** the item shows the contact, the inbound preview and `você: "Te mando o orçamento hoje"`

#### Scenario: SCN-PREC-04
- **GIVEN** an ambiguous inbound message the judge answered with `needs_reply=false`
- **WHEN** reply debts are listed
- **THEN** the conversation is not listed, and a second listing does not call the LLM again

#### Scenario: SCN-PREC-05
- **GIVEN** an ambiguous inbound message and the LLM is unavailable
- **WHEN** reply debts are listed
- **THEN** the conversation is listed (fail-safe)

## ADDED Requirements

### Requirement: Pattern-extracted tasks are evaluated with context
When `EVI_TASK_JUDGE` is not `false`, a `task` produced by the extraction pattern SHALL be stored as `needs_eval` (never listed, briefed or notified) and evaluated outside the webhook request like promises (delay `EVI_PROMISE_EVAL_DELAY_MIN`, up to 10 previous and following messages, third-party text wrapped as external data) by the structured LLM task `TASK`, which SHALL decide whether the message is a commitment or request the user must act on. A kept task SHALL receive its final status from the pattern's date rules (`pending` or `undated`) and a title naming the action; a rejected one SHALL become `dismissed` with `confirmed_via='auto-eval'` (not counted as a user action). When evaluation fails, a row still `needs_eval` after 48 hours SHALL take the status from the pattern. Events SHALL not be evaluated.

#### Scenario: SCN-PREC-06
- **GIVEN** a contact wrote "As empresas gostam do fornecedor enviar a NF pra eles darem baixa no sistema" in a general discussion
- **WHEN** the task is evaluated
- **THEN** it becomes `dismissed` and is never listed

#### Scenario: SCN-PREC-07
- **GIVEN** the user wrote "te mando o relatório amanhã" to a contact
- **WHEN** the task is evaluated and kept
- **THEN** it becomes `pending` with tomorrow's date and a title naming the report
