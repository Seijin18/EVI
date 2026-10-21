## ADDED Requirements

### Requirement: The class schedule is imported from a standard CSV
The EVI SHALL accept a `.csv` sent in the user's Telegram chat with columns `disciplina;data;inicio;fim;descricao;tipo;local;curso` (`;` or `,`, dates `DD/MM/AAAA` or ISO, one row per class), SHALL report row-level errors and a summary before publishing, and SHALL publish only after ✅. Re-importing SHALL update changed rows, create new ones and ask before removing rows that disappeared, keyed by discipline + date + start time. `/grade modelo` SHALL return the example CSV. No LLM call SHALL be made.

#### Scenario: SCN-STUDY-01
- **WHEN** the user sends a CSV with 41 valid rows and one row whose end time is before its start
- **THEN** the EVI replies with the summary and "linha 7: fim antes do início", and creates nothing until ✅

#### Scenario: SCN-STUDY-02
- **GIVEN** a published schedule
- **WHEN** the user sends the same CSV with one class moved to 20:00 and one row removed
- **THEN** the moved class is updated in place, and the EVI asks before removing the other

### Requirement: Classes are published to the user's "Estudos" calendar
Published classes SHALL be created in the Google calendar whose name contains "Estudos" and SHALL be tracked locally in `study_sessions` with the calendar event id. The EVI SHALL only update or delete events it created there. `sem_aula` SHALL remove that date's class; `prova` and `entrega` SHALL create reminders 7 days and 1 day before at 09:00.

#### Scenario: SCN-STUDY-03
- **WHEN** the CSV has "Estatística;27/11/2026;08:00;10:00;P1;prova"
- **THEN** an event is created in "Estudos" and reminders are set for 20/11 and 26/11 at 09:00

### Requirement: Study material sent on Telegram is filed under the right class
A document or photo sent in the user's Telegram chat (other than a `.csv`) SHALL be associated with a class without an LLM: with no caption, today's class or the nearest one within ±3 days; with a caption, the named discipline (prefix or alias), optional `DD/MM` and optional type (`aula`, `leitura`, `plano`, `enunciado`, `anotacao`). The EVI SHALL ask for confirmation (✅, another class, another discipline, not study material) before storing it under `estudos/<curso>/<disciplina>/<data>/`, SHALL not duplicate a file with the same hash, and SHALL refuse files over 20 MB with guidance.

#### Scenario: SCN-STUDY-04
- **GIVEN** Metodologia has class today at 19:00
- **WHEN** the user sends `slides.pdf` with no caption
- **THEN** the EVI proposes "Metodologia, hoje" and stores the file only after ✅

#### Scenario: SCN-STUDY-05
- **WHEN** the user sends a PDF with caption "estat 27/11 leitura"
- **THEN** it is proposed for Estatística on 27/11 as `leitura`

### Requirement: Stored material is searchable by discipline and date
Text extracted from stored PDF, DOCX and PPTX material SHALL be indexed in the study knowledge base with discipline, class date and type, so that study questions can be answered from it.

#### Scenario: SCN-STUDY-06
- **GIVEN** a stored PDF for Estatística mentioning "regressão linear"
- **WHEN** the user asks what the material says about regressão linear
- **THEN** the answer is grounded on that PDF's chunks

### Requirement: Class days appear in the morning briefing
On a day with classes, the morning briefing SHALL show one line per class with time, discipline, description and the number of materials received (or "sem material ainda"). `/estudos` SHALL list, per discipline, the next classes and how many past classes have no material.

#### Scenario: SCN-STUDY-07
- **GIVEN** Metodologia today at 19:00 with 2 materials
- **WHEN** the morning briefing is assembled
- **THEN** it contains "📚 19:00 Metodologia — Revisão bibliográfica · 2 materiais"
