# Tools — productivity

## ADDED Requirements

### Requirement: Inbox organizer
The tool `organize_inbox` SHALL classify files in `/watched_folders/inbox` and only move when `confirm=true`.

#### Scenario: SCN-FO-01
- **GIVEN** `lecture_notes.pdf`
- **WHEN** classify runs
- **THEN** destination is `/watched_folders/university`

#### Scenario: SCN-FO-02
- **GIVEN** dry-run (`confirm=false`)
- **WHEN** organizer runs
- **THEN** files are not moved

### Requirement: Manual notes
The tool `save_note_manual` SHALL write frontmatter Markdown under `inbox_ia/`.

### Requirement: Tasks
The tool `create_task` SHALL POST to n8n tasks webhook with title and optional due_date.

### Requirement: Email summary
The tool `summarize_inbox` SHALL request summary via n8n email webhook.
