## ADDED Requirements

### Requirement: Agent clock uses EVI_TIMEZONE
The date/time context the agent reasons over SHALL be computed in `ZoneInfo(EVI_TIMEZONE)`, not the container's system clock. This covers the `CALENDAR LOOKUP TABLE` and "Today is ..." line built by `graph._calendar_block()` and the default event date in `calendar_time.iso_event_range()`.

#### Scenario: SCN-CAL-07
- **GIVEN** the process runs with `TZ=UTC` and `EVI_TIMEZONE=America/Sao_Paulo`
- **WHEN** the calendar block is built at a UTC instant whose local date differs (e.g. 01:00Z)
- **THEN** the "Today is" line and the lookup table use the `America/Sao_Paulo` date, not the UTC date
