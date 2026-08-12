## ADDED Requirements

### Requirement: Heartbeat staleness compares dates
`_contacts_needing_synthesis` SHALL determine whether a contact needs re-synthesis by parsing the date out of the `## Síntese (YYYY-MM-DD, …)` heading and comparing it to the newest timeline timestamp as dates. Comparing a timestamp against a raw markdown slice is not permitted — `'2' > '#'` makes it unconditionally true, which flagged every contact with a recent timeline. A profile whose heading cannot be parsed SHALL be treated as stale, since a false "needs synthesis" is noise while a false "already synthesised" hides real work.

#### Scenario: SCN-MEM-11
- **GIVEN** a contact whose profile carries `## Síntese (2026-08-12, últimos 7 dias)` and whose newest timeline entry is from 2026-08-10
- **WHEN** `run_heartbeat` evaluates staleness
- **THEN** the contact is NOT reported as needing synthesis
- **AND** the same contact with a timeline entry from 2026-08-13 IS reported
