## ADDED Requirements

### Requirement: User-level MEMORY.md
The system SHALL support user-level long memory at `EVI_WORKSPACE/MEMORY.md` and daily logs at `EVI_WORKSPACE/memory/YYYY-MM-DD.md`.

#### Scenario: SCN-MEM-05
- **WHEN** memory flush runs before session compaction
- **THEN** a line is appended to the current day's memory log file
