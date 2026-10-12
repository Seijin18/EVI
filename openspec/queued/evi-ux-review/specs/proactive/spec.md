## ADDED Requirements

### Requirement: What the user reads carries no model markers
Every message sent to the user (briefing, lists, direct replies) SHALL be rendered from data without `wrap_external` markers, with third-party text escaped for the Telegram format in use; the version stored in the session history that later reaches an LLM SHALL keep third-party text wrapped as external data. A residual marker found at send time SHALL be removed and logged as a soft failure.

#### Scenario: SCN-UX-02
- **GIVEN** a briefing with a calendar event titled "entrega lote 2 <isla>"
- **WHEN** it is sent to Telegram and stored in the session
- **THEN** the user sees the title escaped and without `«externo`, and the stored session text has it wrapped as external data

### Requirement: Briefing items read person-first in one line
Briefing items SHALL be one line each with the person (contact or sender name) first and emphasized, then the subject, then short metadata (age, due date); a truncated section SHALL say what kind of items are hidden and which reply lists them; the briefing SHALL end with the reply commands valid for the items shown. If Telegram rejects the formatting, the same content SHALL be resent as plain text.

#### Scenario: SCN-UX-03
- **GIVEN** a pending promise "Mandar a modelagem" to Eliana due Friday and 11 more promises
- **WHEN** the morning briefing is assembled
- **THEN** its line reads with "Eliana" first, the task and "até sex", and the section ends with "+11 promessas" and the command to list them

### Requirement: Long briefings collapse low-priority sections
When the assembled briefing would exceed about 25 lines, lower-priority sections SHALL be replaced by a one-line summary with the command that lists them.

#### Scenario: SCN-UX-04
- **GIVEN** 8 events, 5 tasks, 9 emails and 15 WhatsApp items
- **WHEN** the briefing is assembled
- **THEN** it has at most about 25 lines and each collapsed section shows its count and command
