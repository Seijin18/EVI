# Data — long-term memory (planned)

## Purpose

Define phased long-term memory for EVI: hot Postgres, cold per-contact filesystem, and optional Neo4j knowledge graph (compose profile `graph`).

## Requirements

### Requirement: Hot memory layer
The system SHALL persist recent chat turns in Postgres `messages` and structured commitments in `pending_commitments` including `source_chat`, `source_label`, and `raw_text`.

#### Scenario: SCN-MEM-01
- **WHEN** an Evolution webhook queues a commitment
- **THEN** `pending_commitments` row includes `source_chat` and `raw_text`

### Requirement: Cold filesystem per contact
The system SHALL store per-contact long memory under `EVI_CONTACT_MEMORY_DIR/contacts/{jid_sanitized}/` with `profile.md`, `timeline.jsonl`, and optional `summaries/YYYY-MM-DD.md`. Evolution webhook SHALL append timeline entries when commitments are queued.

#### Scenario: SCN-MEM-02
- **WHEN** `./scripts/evi-test contact-memory` runs
- **THEN** a timeline line is written under the contact directory contract

#### Scenario: SCN-MEM-02b
- **WHEN** `./scripts/evi-test daily-summary` runs
- **THEN** `summaries/YYYY-MM-DD.md` is created for contacts with activity

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
