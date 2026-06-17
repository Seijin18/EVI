# Tools — productivity

## Purpose

Inbox organization, manual notes, and Windmill-backed task and email tools.

## Requirements

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

#### Scenario: SCN-NOTE-02
- **WHEN** `./scripts/evi-test notes` runs
- **THEN** a note file is created or validated under inbox_ia

### Requirement: Tasks
The tool `create_task` SHALL POST to `WINDMILL_WEBHOOK_TASKS` with title and optional due_date.

#### Scenario: SCN-TASK-04
- **WHEN** task tool runs with mock or live Windmill webhook
- **THEN** success message is returned

### Requirement: Email summary
The tool `summarize_inbox` SHALL request summary via `WINDMILL_WEBHOOK_EMAIL`.

#### Scenario: SCN-EMAIL-03
- **WHEN** email tool runs with mock or live Windmill webhook
- **THEN** summary or success message is returned

### Requirement: Email live harness
The productivity test harness SHALL invoke `summarize_inbox` when `--live-windmill` is passed to the email feature.

#### Scenario: SCN-EMAIL-05
- **WHEN** `./scripts/evi-test email --live-windmill` runs
- **THEN** `summarize_inbox` is invoked and summary content is validated in the result

### Requirement: Delete emails by Gmail query
The tool `delete_emails_by_query` SHALL trash messages matching a Gmail search query via Windmill.

#### Scenario: SCN-UX-INBOX-02
- **WHEN** user asks to delete emails by sender/domain
- **THEN** agent can call `delete_emails_by_query` without requesting message IDs
