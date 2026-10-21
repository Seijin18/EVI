## ADDED Requirements

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
