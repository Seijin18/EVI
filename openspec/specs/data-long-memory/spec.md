# Data — long-term memory (planned)

## Purpose

Define phased long-term memory for EVI: hot Postgres, cold per-contact filesystem, and deferred Neo4j knowledge graph. Not yet implemented beyond hot layer.

## Requirements

### Requirement: Hot memory layer
The system SHALL persist recent chat turns in Postgres `messages` and structured commitments in `pending_commitments` including `source_chat`, `source_label`, and `raw_text`.

#### Scenario: SCN-MEM-01
- **WHEN** an Evolution webhook queues a commitment
- **THEN** `pending_commitments` row includes `source_chat` and `raw_text`

### Requirement: Cold filesystem per contact (planned)
Future implementation SHALL store per-contact long memory under `EVI_CONTACT_MEMORY_DIR/contacts/{jid_sanitized}/` with `profile.md`, `timeline.jsonl`, and optional `summaries/YYYY-MM-DD.md`.

#### Scenario: SCN-MEM-02
- **WHEN** `openspec/specs/data-long-memory/spec.md` is inspected
- **THEN** the directory contract and file roles are documented

### Requirement: Knowledge graph layer (deferred)
Future Neo4j integration SHALL model `Contact`, `Group`, `Commitment`, `Fact`, and `Summary` nodes with relational edges; it MUST NOT ship before Etapa 5a filesystem memory is stable.

#### Scenario: SCN-MEM-03
- **WHEN** roadmap is reviewed
- **THEN** `evi-conversation-graph-neo4j` is listed after `evi-contact-filesystem-memory`

### Requirement: External episodic memory excluded
The EVI repository MUST NOT depend on Graphiti or external episodic-memory MCP for long-term storage.

#### Scenario: SCN-MEM-04
- **WHEN** `.cursor/rules/evi-stack.mdc` is inspected
- **THEN** Graphiti is explicitly excluded from project MCP

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
