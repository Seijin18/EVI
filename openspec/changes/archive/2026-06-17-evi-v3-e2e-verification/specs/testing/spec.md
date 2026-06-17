## ADDED Requirements

### Requirement: Runtime v3 offline harness
The project SHALL provide `./scripts/evi-test runtime-v3` validating workspace bootstrap, context assembly, skills, and tool registry wiring without network.

#### Scenario: SCN-UX-RUNTIME
- **WHEN** `./scripts/evi-test runtime-v3` runs offline
- **THEN** workspace files exist and `build_context` returns non-empty text

### Requirement: Inbox UX harness
The project SHALL provide `./scripts/evi-test inbox-ux` covering inbox format, delete_by_query mock, and session snapshot follow-up.

#### Scenario: SCN-UX-INBOX-01
- **WHEN** inbox-ux runs with `email_summary_messages.json`
- **THEN** formatted output includes message ids

#### Scenario: SCN-UX-INBOX-02
- **WHEN** delete_by_query is invoked with mocked Windmill
- **THEN** response reports deleted count without requiring user ids

#### Scenario: SCN-UX-INBOX-04
- **WHEN** tool snapshots exist for a session
- **THEN** `build_context` includes SESSION TOOL SNAPSHOTS block

### Requirement: LLM-first control channels
When `EVI_DIRECT_HANDLERS=false`, Telegram and WhatsApp control SHALL route inbox/review phrases through `invoke_chat`.

#### Scenario: SCN-UX-WA-CTRL-01
- **WHEN** `tests/unit/test_whatsapp_control.py` runs with default env
- **THEN** direct handler mocks are not called for review/inbox phrases
