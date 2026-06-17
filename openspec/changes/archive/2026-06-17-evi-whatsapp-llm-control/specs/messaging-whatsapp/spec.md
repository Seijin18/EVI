## ADDED Requirements

### Requirement: Evolution filter hardening
The Evolution filter SHALL drop messages without valid timestamps when `EVI_WHATSAPP_REQUIRE_TS=true`, honor `EVI_WHATSAPP_PROCESS_AFTER`, and mark all received message ids as seen.

#### Scenario: SCN-UX-WA-ING-01
- **WHEN** Evolution sends a burst after long downtime
- **THEN** messages outside age/watermark are not extracted

### Requirement: Conservative commitment extraction
Heuristic and LLM extract SHALL reject generic titles and casual group chat without schedule signals.

#### Scenario: SCN-UX-WA-ING-02
- **WHEN** casual group message is processed
- **THEN** no pending commitment is created
