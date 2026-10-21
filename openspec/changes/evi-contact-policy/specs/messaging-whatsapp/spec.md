## MODIFIED Requirements

### Requirement: WhatsApp group whitelist
Group ingestion SHALL be decided by the contact policy: a group JID is ingested only when its `contact_policy` row has `ingest=true`. A group without a row SHALL be ignored. `EVI_WHATSAPP_GROUP_WHITELIST` (comma-separated `@g.us` ids) SHALL only seed rows with `ingest=true, send=false` that do not exist yet. `EVI_WHATSAPP_SKIP_GROUPS=false` SHALL keep its legacy meaning of ingesting every group.

#### Scenario: SCN-WA-06
- **GIVEN** the policy has `120363012345678901@g.us` with `ingest=true` (set by command or seeded from the whitelist)
- **WHEN** filter runs on a group message with that JID
- **THEN** message is retained for processing

#### Scenario: SCN-WA-07
- **GIVEN** no policy row exists for a different `@g.us` JID
- **WHEN** filter runs on a message from that group
- **THEN** message is skipped as a group

### Requirement: Evolution groupsIgnore coordination
`setup-evolution.sh` SHALL always set `groupsIgnore=false`, so that groups the user enables later reach the webhook without reconfiguring Evolution; groups that are not enabled SHALL be dropped by the ingestion gate.

#### Scenario: SCN-WA-08
- **WHEN** the setup script runs, with or without a whitelist in the environment
- **THEN** Evolution instance config disables `groupsIgnore`

## ADDED Requirements

### Requirement: Contact policy gates ingestion before anything is stored
The Evolution webhook SHALL check `contact_policy.ingest_allowed` on the canonical JID of every non-control message right after parsing, before conversation state, promise capture, the processing filter, extraction, timeline or any trace that carries message text. A blocked message (inbound or `fromMe`) SHALL be dropped with trace `reason: policy` and no text preview. Without a policy row, direct conversations SHALL be ingested and groups SHALL NOT.

#### Scenario: SCN-POL-01
- **GIVEN** the user blocked reading Bruno (`ingest=false`)
- **WHEN** Bruno sends "me liga amanhã?" and the user replies to him
- **THEN** nothing about either message is written to the timeline, `wa_conversation_state`, `pending_commitments` or the trace text, and the trace has `reason: policy`
- **AND** after "volta a ler Bruno", his next message is ingested normally

#### Scenario: SCN-POL-02
- **GIVEN** a group with no policy row
- **WHEN** a member writes in the group
- **THEN** the message is dropped with `reason: policy`
- **AND** after the user enables the group, its next message is ingested

### Requirement: WhatsApp sends honour the contact policy
`send_whatsapp_text` SHALL refuse any recipient that is not a control JID and whose policy has `send=false`, and any group without a policy row allowing sends, returning a failure with reason `policy_send_blocked` and sending nothing. This guard SHALL NOT by itself authorize sending to third parties.

#### Scenario: SCN-POL-03
- **WHEN** code calls `send_whatsapp_text` for a contact with `send=false` or for a group that was never enabled
- **THEN** no request reaches Evolution and the result is `ok=false, reason=policy_send_blocked`
- **AND** a send to the control JID still goes through

### Requirement: Policy changes are deterministic Telegram commands with confirmation
The user SHALL change the policy only through deterministic Telegram commands (`para de ler`, `volta a ler`, `não envia para`, `pode enviar para`, `libera o grupo`, `bloqueia o grupo`) and SHALL list it with `/privacidade`, with no LLM call. The target (name, phone number or group name) SHALL be resolved in code: no match → "não achei"; several → numbered choice; one → confirmation showing name and number/JID with ✅/✖ buttons. The policy SHALL change only after ✅ from the user's chat, never from a turn triggered by third-party content.

#### Scenario: SCN-POL-04
- **GIVEN** two contacts named "Ana"
- **WHEN** the user writes "para de ler Ana"
- **THEN** the EVI lists both with their numbers and changes nothing until the user picks one and taps ✅

#### Scenario: SCN-POL-05
- **WHEN** the user sends `/privacidade`
- **THEN** the reply lists contacts with reading or sending blocked and the groups that are enabled, with no LLM call

### Requirement: Blocking reading offers to delete what was stored
After the user confirms blocking a contact's reading, the EVI SHALL offer to delete what it already stored about that contact. Only after ✅ it SHALL delete the contact's directory (timeline and profile), and the rows for the contact's JID and aliases in `wa_conversation_state`, `pending_commitments`, `awaiting_dismissed` and the judges' verdicts, and SHALL record counts without content in the trace.

#### Scenario: SCN-POL-06
- **GIVEN** Bruno has a timeline, a profile and a pending reply debt
- **WHEN** the user blocks reading Bruno and taps ✅ on "apagar o que já guardei?"
- **THEN** the timeline, profile and debt are gone, and the trace records `purge` with counts
- **AND** tapping ✖ instead keeps the data and only stops new ingestion
