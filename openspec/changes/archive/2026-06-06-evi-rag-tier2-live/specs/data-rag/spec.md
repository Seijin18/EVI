## ADDED Requirements

### Requirement: Live RAG harness
The project SHALL provide `./scripts/evi-test rag --live-qdrant` to ingest a fixture PDF and query Qdrant when the stack is up.

#### Scenario: SCN-RAG-04
- **WHEN** `./scripts/evi-test rag --live-qdrant` runs with Qdrant and Ollama embeddings available
- **THEN** ingest succeeds and query returns chunks or a documented empty result without failure prefix
