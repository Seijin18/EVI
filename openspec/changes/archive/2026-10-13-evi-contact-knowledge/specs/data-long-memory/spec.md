## MODIFIED Requirements

### Requirement: Cold filesystem per contact
The system SHALL store per-contact long memory under `EVI_CONTACT_MEMORY_DIR/contacts/{jid_sanitized}/` with `profile.md`, `timeline.jsonl`, and optional `summaries/YYYY-MM-DD.md` and `history.md`, only for direct conversations (never for groups, `@newsletter` channels or `@broadcast`). Evolution webhook SHALL append timeline entries when commitments are queued, and SHALL append every direct message of the conversation — received and sent by the user (`fromMe`, as `[eu] …`, excluding EVI echoes) — without feeding `fromMe` messages into commitment extraction.

#### Scenario: SCN-MEM-02
- **WHEN** `./scripts/evi-test contact-memory` runs
- **THEN** a timeline line is written under the contact directory contract

#### Scenario: SCN-MEM-02b
- **WHEN** `./scripts/evi-test daily-summary` runs
- **THEN** `summaries/YYYY-MM-DD.md` is created for contacts with activity

#### Scenario: SCN-MEM-14
- **WHEN** the user sends "te mando a modelagem quando terminar" in a direct conversation
- **THEN** the contact's timeline gets a `[eu] te mando a modelagem quando terminar` entry and no commitment is extracted from it by the inbound extraction

#### Scenario: SCN-MEM-15
- **WHEN** a WhatsApp Channel (`…@newsletter`) posts a message
- **THEN** no contact directory is created for it

## ADDED Requirements

### Requirement: Contact knowledge is structured and replaced, not appended
`profile.md` SHALL keep EVI-managed sections `## Fatos` (stable facts, each with the date of the message that supports it, at most 15) and `## Em aberto` (open items, at most 5), and a `## Notas` section owned by the user that EVI SHALL never modify. `read_contact_knowledge(jid)` SHALL return those three sections without the file header, and SHALL be the profile source for contact info, LLM commitment extraction and promise evaluation.

#### Scenario: SCN-MEM-16
- **GIVEN** a profile with facts, open items and a user note
- **WHEN** the knowledge is updated twice
- **THEN** the file has one `## Fatos` and one `## Em aberto` section, the note is byte-identical, and `read_contact_knowledge` returns the latest facts and no header line

### Requirement: Contact knowledge updates are incremental and evidence-bound
Updating a contact's knowledge SHALL send the LLM only the current facts and open items and the conversation messages (both sides) newer than the last update, never file metadata, through the structured LLM task `CONTACT_KNOWLEDGE`, and SHALL apply a structured answer (facts to add with a date, current facts to remove by their id, the complete list of open items). A fact without a date inside the message window SHALL be discarded; an invalid answer SHALL leave the profile unchanged.

#### Scenario: SCN-MEM-17
- **GIVEN** a profile created at 05:00 and no message mentioning a meeting
- **WHEN** the knowledge is updated
- **THEN** no fact or open item mentions a meeting

#### Scenario: SCN-MEM-18
- **GIVEN** the LLM returns invalid JSON
- **WHEN** the knowledge is updated
- **THEN** `profile.md` is unchanged

### Requirement: Contact knowledge is refreshed daily
A scheduled job SHALL update, once a day, the knowledge of the direct contacts with timeline entries newer than their last update, most recent first, at most 15 per run, resolving contacts by JID.

#### Scenario: SCN-MEM-19
- **GIVEN** 20 contacts with new messages and 5 without
- **WHEN** the daily job runs
- **THEN** the 15 most recently active contacts with new messages are updated and the 5 without are not

### Requirement: Legacy syntheses are migrated out of the profile
A one-off migration SHALL move every `## Síntese (…)` section from `profile.md` to `history.md` in the same directory, unchanged, with a dry-run by default.

#### Scenario: SCN-MEM-20
- **GIVEN** a profile with a `## Síntese (2026-06-17, últimos 7 dias)` section
- **WHEN** the migration runs with `--apply`
- **THEN** the section is in `history.md` and no longer in `profile.md`

### Requirement: One contact identity across LID and phone JIDs
When Evolution reports a phone JID for a `…@lid` chat (`remoteJidAlt`), the pair SHALL be stored and the phone JID SHALL be the canonical identity for the contact's timeline, knowledge, reply debts and WhatsApp summaries.

#### Scenario: SCN-MEM-21
- **GIVEN** messages from the same person arrive as `…@lid` and as `…@s.whatsapp.net`
- **WHEN** the WhatsApp summary is built and the contact knowledge is updated
- **THEN** the summary shows one conversation and one contact directory holds both timelines
