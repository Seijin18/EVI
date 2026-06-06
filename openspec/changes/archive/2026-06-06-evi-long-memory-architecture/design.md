## Memory layers (target)

| Layer | Store | As-built |
|-------|-------|----------|
| Hot | Postgres `messages`, `pending_commitments`; JSONL Evolution logs | Yes |
| Cold FS | `EVI_CONTACT_MEMORY_DIR/contacts/{jid}/` | Etapa 5a |
| Graph | Neo4j `Contact`, `Commitment`, `Fact` | Etapa 5b |

## RAM

Neo4j deferred (~1–1.5 GB). Etapa 5a is filesystem-only.

## Out of scope

Graphiti MCP in this repo; full WhatsApp message archive without filter.
