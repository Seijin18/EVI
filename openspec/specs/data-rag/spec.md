# Data — university RAG (secondary priority)

## ADDED Requirements

### Requirement: Collection
The system SHALL use Qdrant collection `university_notes` with 768-dim COSINE vectors.

### Requirement: Ingest
The tool `ingest_university_pdf` SHALL chunk PDFs (512/64) and embed via `nomic-embed-text`.

### Requirement: Query
The tool `query_university_notes` SHALL return top-k chunks with source metadata.

Priority: **secondary** vs productivity features.
