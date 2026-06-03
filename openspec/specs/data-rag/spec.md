# Data — university RAG (secondary priority)

## Purpose

Vector search over university PDFs via Qdrant; secondary to productivity tools.

## Requirements

### Requirement: Collection
The system SHALL use Qdrant collection `university_notes` with 768-dim COSINE vectors.

#### Scenario: SCN-RAG-01
- **WHEN** ingest or query runs against university notes
- **THEN** collection name is `university_notes` with 768-dimensional vectors

### Requirement: Ingest
The tool `ingest_university_pdf` SHALL chunk PDFs (512/64) and embed via `nomic-embed-text`.

#### Scenario: SCN-RAG-02
- **WHEN** a PDF is ingested successfully
- **THEN** chunks are stored with embedding metadata in Qdrant

### Requirement: Query
The tool `query_university_notes` SHALL return top-k chunks with source metadata.

#### Scenario: SCN-RAG-03
- **WHEN** query runs with a natural-language question
- **THEN** response includes ranked chunks with source references
