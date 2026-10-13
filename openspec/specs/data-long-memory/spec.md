# Data — long-term memory

## Purpose

Long-term memory for EVI: hot Postgres, cold per-contact filesystem, and optional Neo4j knowledge graph (compose profile `graph`).
## Requirements
### Requirement: Hot memory layer
The system SHALL persist recent chat turns in Postgres `messages` and structured commitments in `pending_commitments` including `source_chat`, `source_label`, and `raw_text`.

#### Scenario: SCN-MEM-01
- **WHEN** an Evolution webhook queues a commitment
- **THEN** `pending_commitments` row includes `source_chat` and `raw_text`

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

### Requirement: Knowledge graph layer (optional)
When `NEO4J_URI` is set, the system SHALL sync `Contact` and `Commitment` nodes with `ORIGINATED_FROM` edges and expose `query_conversation_graph` tool.

#### Scenario: SCN-MEM-03
- **WHEN** `./scripts/evi-test graph` runs offline
- **THEN** `graph_tool.py` and `graph_sync.py` wiring is validated

#### Scenario: SCN-MEM-03b
- **WHEN** `docker compose --profile graph up -d neo4j` runs with `NEO4J_URI` on agent-api
- **THEN** queued commitments create graph nodes (best-effort sync)

### Requirement: External episodic memory excluded
The EVI repository MUST NOT depend on Graphiti or external episodic-memory MCP for long-term storage.

#### Scenario: SCN-MEM-04
- **WHEN** `.cursor/rules/evi-stack.mdc` is inspected
- **THEN** Graphiti is explicitly excluded from project MCP

### Requirement: User-level workspace memory
The system SHALL support user-level long memory at `EVI_WORKSPACE/MEMORY.md` and daily logs at `EVI_WORKSPACE/memory/YYYY-MM-DD.md`, with memory flush before session compaction.

#### Scenario: SCN-MEM-05
- **WHEN** memory flush runs before bounded-memory trim
- **THEN** a line is appended to the current day's memory log file

### Requirement: Contact learning by name
The system SHALL expose LangGraph tools to list, inspect, and learn WhatsApp contacts by display name or phone without requiring JID from the user.

#### Scenario: SCN-MEM-06
- **WHEN** `./scripts/evi-test contact-learning` runs
- **THEN** contact resolution, mocked synthesis, and registry wiring pass offline

### Requirement: Evolution message backfill
When learning a contact with fetch enabled, the system SHALL call Evolution findMessages and append new rows to timeline.jsonl with dedupe by source_id.

#### Scenario: SCN-MEM-07
- **WHEN** `./scripts/evi-test contact-learning` or unit backfill tests run
- **THEN** timeline entries include optional `backfill` flag and respect `EVI_BACKFILL_MAX_MESSAGES`

### Requirement: Postgres contact registry
The system SHALL persist WhatsApp contact identity (display name, aliases, phone) in Postgres (`whatsapp_contacts`), synced from Evolution, and expose `set_whatsapp_contact_name` to assign a display name/alias by JID. Postgres is the canonical source for contact identity; the filesystem (`contact_filesystem`) remains canonical for timeline/narrative memory.

#### Scenario: SCN-MEM-08
- **WHEN** `tests/unit/test_contact_registry.py` runs
- **THEN** contacts can be searched by agenda name/alias and merged with filesystem-known contacts via `collect_known_contacts`

### Requirement: Evolution contact and chat discovery
The system SHALL expose tools to list and summarize recent WhatsApp chats/contacts via Evolution `findContacts`/`findChats`, independent of contacts already known to filesystem or Postgres memory.

#### Scenario: SCN-MEM-09
- **WHEN** `tests/unit/test_evolution_discovery.py` runs
- **THEN** discovery service returns contacts/chats from the Evolution API response shape without requiring prior local memory

### Requirement: Commitment replay from ingest log
The system SHALL be able to replay `evolution_webhook.jsonl` ingest lines to backfill `pending_commitments` and contact timeline entries that were missed by the live webhook filter or Evolution cache lag.

#### Scenario: SCN-MEM-10
- **WHEN** `tests/unit/test_commitment_replay.py` runs
- **THEN** commitments extracted from replayed ingest lines are queued without duplicating already-processed messages

### Requirement: Heartbeat staleness compares dates
`_contacts_needing_synthesis` SHALL determine whether a contact needs re-synthesis by parsing the date out of the `## Síntese (YYYY-MM-DD, …)` heading and comparing it to the newest timeline timestamp as dates. Comparing a timestamp against a raw markdown slice is not permitted — `'2' > '#'` makes it unconditionally true, which flagged every contact with a recent timeline. A profile whose heading cannot be parsed SHALL be treated as stale, since a false "needs synthesis" is noise while a false "already synthesised" hides real work.

#### Scenario: SCN-MEM-11
- **GIVEN** a contact whose profile carries `## Síntese (2026-08-12, últimos 7 dias)` and whose newest timeline entry is from 2026-08-10
- **WHEN** `run_heartbeat` evaluates staleness
- **THEN** the contact is NOT reported as needing synthesis
- **AND** the same contact with a timeline entry from 2026-08-13 IS reported

### Requirement: Address-book names are imported from a vCard
The system SHALL import contact names from the user's address book, because WhatsApp never transmits them: Evolution only receives `pushName`, the name the contact chose for their own profile. Sources SHALL be a local vCard export (reading only `FN`/`N` and `TEL`, handling vCard 2.1/3.0/4.0, line folding and quoted-printable) and the Google account address book (People API, read-only, only names and phone numbers), both applied by the same importer.

An imported name SHALL be written to `display_name` with its source (`vcard` or `agenda`), and any existing `pushName` SHALL be preserved as an alias so search keeps matching whichever name the user types. Resolution precedence becomes **name set by the user in chat > address book > pushName > number**; an import SHALL never overwrite a name the user set in chat, and a phone that matches two different address-book names SHALL be reported as ambiguous and left unchanged.

The import SHALL run as a local job, never routing address-book contents through an LLM, and SHALL default to a dry run that reports the changes it would make.

#### Scenario: SCN-MEM-12
- **WHEN** the importer runs in dry-run mode against a `.vcf`
- **THEN** it reports matched, unmatched and unchanged counts and writes nothing
- **AND** confirming applies only the matched entries, setting `display_name` and keeping the previous label as an alias

#### Scenario: SCN-NAME-02
- **GIVEN** the user named a contact "Hollmann" in chat and the address book calls the same number "Pedro H"
- **WHEN** the address-book sync runs
- **THEN** the contact is still "Hollmann"

#### Scenario: SCN-NAME-03
- **GIVEN** a WhatsApp contact shown as "+55 11 94826-0209" and an address-book entry "Hollmann" with "(11) 4826-0209"
- **WHEN** the address-book sync runs
- **THEN** the contact is named "Hollmann" and the previous label is kept as an alias

### Requirement: Phone matching survives the Brazilian ninth digit
Matching a vCard number to an existing WhatsApp contact SHALL use `DDD + the last 8 digits`, not string equality on the full number. A mobile number is stored with or without the ninth digit depending on when the record was created — measured on the live registry, 1104 JIDs carry 13 digits and 84 carry 12 — and a vCard may hold either form for the same person.

The key SHALL be verified as unambiguous before use: on the live registry it produced 1187 distinct keys for 1187 Brazilian contacts with zero collisions. An entry matching more than one contact SHALL be reported as ambiguous and skipped rather than guessed.

#### Scenario: SCN-MEM-13
- **GIVEN** a contact stored as `5511987654321@s.whatsapp.net` (with the ninth digit)
- **WHEN** the vCard holds `(11) 8765-4321` (without it, and formatted)
- **THEN** the two are matched
- **AND** an entry whose key matches two different JIDs is skipped and counted as ambiguous

### Requirement: Heartbeat does not send maintenance notices when the briefing is on
When `EVI_BRIEFING_ENABLED=true`, `run_heartbeat` SHALL NOT send maintenance findings (contacts needing synthesis) to the user's channels; it SHALL log them instead. Unnotified pending commitments are surfaced by the briefing and SHALL NOT be duplicated by the heartbeat.

#### Scenario: SCN-BRIEF-07
- **GIVEN** `EVI_BRIEFING_ENABLED=true`, `EVI_HEARTBEAT_ENABLED=true`, stale contacts and unnotified pending commitments
- **WHEN** `run_heartbeat` runs
- **THEN** no message is sent and the findings are written to the log
- **AND** with `EVI_BRIEFING_ENABLED=false` the previous behaviour is unchanged

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

### Requirement: The Google address book is synced daily
A scheduled job SHALL read the Google account address book once a day through Windmill (OAuth `contacts.readonly`), keep only names and phone numbers, and apply them through the address-book importer.

#### Scenario: SCN-NAME-01
- **WHEN** the daily sync runs against a fixture of two People API pages
- **THEN** all entries are read and only name and phone numbers reach the importer

### Requirement: A LID contact takes the name of its paired phone
A `…@lid` contact paired with a phone JID SHALL be shown with the name resolved for the phone JID.

#### Scenario: SCN-NAME-04
- **GIVEN** `…@lid` paired with `5511948260209@s.whatsapp.net`, named "Hollmann"
- **WHEN** the WhatsApp summary lists that LID conversation
- **THEN** it is shown as "Hollmann"

## Directory contract (Etapa 5a target)

```
EVI_CONTACT_MEMORY_DIR/
  contacts/{jid_sanitized}/
    profile.md
    timeline.jsonl
    summaries/YYYY-MM-DD.md
```

- Key: WhatsApp/Telegram JID from `pending_commitments.source_chat`
- `profile.md`: stable facts (name, relationship, preferences)
- `timeline.jsonl`: snippets with `ts`, `source_id`, `text_preview`, optional `commitment_id`
- `summaries/`: daily LLM or template digest (Windmill cron — separate change)

## Graph contract (Etapa 5b target)

| Node | Examples |
|------|----------|
| Contact | person or group JID |
| Commitment | queued/scheduled item |
| Fact | extracted preference |
| Summary | daily digest node |

| Edge | Meaning |
|------|---------|
| ORIGINATED_FROM | Commitment → Contact/Group |
| SCHEDULED_AS | Commitment → Calendar event |
| MENTIONED_IN | Fact → timeline snippet |
