## ADDED Requirements

### Requirement: A failed booking never marks a commitment scheduled
`confirm_commitments` SHALL gate `update_commitment_status(..., "scheduled", ...)` on the structured outcome of `schedule_event_result` / `create_task_result`. Deciding from the returned prose is not permitted: the previous `_tool_succeeded` matched the substring `"criad"`, so a Windmill error whose *detail* contained "criada" — or any English "created" — flipped the row to `scheduled` with nothing booked.

#### Scenario: SCN-CHAT-05
- **GIVEN** a pending commitment
- **WHEN** the booking returns `{"status": "error", "detail": "A tarefa nao pode ser criada: quota exceeded"}`
- **THEN** the row stays `pending`, `update_commitment_status` is not called, and the reply marks the line as failed
- **AND** the same holds for a transport sentinel (`Missing WINDMILL_*`) and for an unparseable body
- **AND** a genuine `{"status": "created"}` still schedules
