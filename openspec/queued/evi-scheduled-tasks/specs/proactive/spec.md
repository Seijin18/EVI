## ADDED Requirements

### Requirement: Read-only scheduled tasks run a question on a schedule
When `EVI_SCHEDULED_TASKS_ENABLED` is not `false`, the user SHALL be able to create, list, pause and cancel scheduled tasks in conversation, each with a question, a first time and a recurrence from the reminder presets, only on an explicit request in the user's own message. A due task SHALL run as its own turn (`channel='scheduled'`, separate session) with only read tools bound, and its answer SHALL be delivered to Telegram with the task title. At most 10 tasks SHALL be active and at most 6 runs SHALL happen per local day; a failed or capped run SHALL be reported once and retried at the next occurrence.

#### Scenario: SCN-SCHED-01
- **WHEN** the user says "toda sexta às 18h, resuma meus e-mails da semana"
- **THEN** an active weekly task is stored for the next Friday 18:00 with that question

#### Scenario: SCN-SCHED-02
- **GIVEN** that task and the clock reaching Friday 18:00
- **WHEN** the reminder loop ticks
- **THEN** the email summary is delivered to Telegram with the task title, and the next run is the following Friday 18:00

#### Scenario: SCN-SCHED-03
- **GIVEN** a scheduled task whose question is "apague meus e-mails de promoção"
- **WHEN** it runs
- **THEN** no write tool is available or called and no email is deleted

#### Scenario: SCN-SCHED-04
- **GIVEN** 6 scheduled runs already happened today
- **WHEN** a seventh task is due
- **THEN** it is not run today, the user is told once, and it runs at its next occurrence
