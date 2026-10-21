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

### Requirement: A failed booking never marks a commitment scheduled
`confirm_commitments` SHALL gate `update_commitment_status(..., "scheduled", ...)` on the structured outcome of `schedule_event_result` / `create_task_result`. Deciding from the returned prose is not permitted: the previous `_tool_succeeded` matched the substring `"criad"`, so a Windmill error whose *detail* contained "criada" — or any English "created" — flipped the row to `scheduled` with nothing booked.

#### Scenario: SCN-CHAT-05
- **GIVEN** a pending commitment
- **WHEN** the booking returns `{"status": "error", "detail": "A tarefa nao pode ser criada: quota exceeded"}`
- **THEN** the row stays `pending`, `update_commitment_status` is not called, and the reply marks the line as failed
- **AND** the same holds for a transport sentinel (`Missing WINDMILL_*`) and for an unparseable body
- **AND** a genuine `{"status": "created"}` still schedules

### Requirement: Complete Google Tasks
The tool `complete_tasks` SHALL mark open Google Tasks as completed through the Windmill `complete_task` script (`WINDMILL_WEBHOOK_COMPLETE_TASK`), only on an explicit request in the user's own turn (write tool). Targets SHALL be resolved in code from the open tasks by case-insensitive title substring or short ID (`match`), or all open tasks (`all_open`), minus those matching `except_match`. With neither `match` nor `all_open` nothing SHALL be completed. The result SHALL list the tasks completed, kept and not matched, and any failure per task. `list_tasks` SHALL show a short ID per task. When a requested capability is missing the agent SHALL say so instead of inventing a restriction.

#### Scenario: SCN-TASK-06
- **GIVEN** open tasks "Avaliar PowerPoint do mestrado", "Implementar A" and "Implementar B"
- **WHEN** the user asks to finish all open tasks except the mestrado one
- **THEN** "Implementar A" and "Implementar B" are completed in Google Tasks and the mestrado task stays open

#### Scenario: SCN-TASK-07
- **WHEN** `complete_tasks` is called without `match` and without `all_open`
- **THEN** no task is completed and the tool asks which tasks to finish

#### Scenario: SCN-TASK-08
- **WHEN** a job, scheduled or external-content turn calls `complete_tasks`
- **THEN** the write guard blocks it and no task changes

