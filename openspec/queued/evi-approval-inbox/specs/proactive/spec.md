## ADDED Requirements

### Requirement: Every action prepared by the EVI waits in one approval inbox
Actions that need the user's approval SHALL be stored as proposals with kind, title, payload, origin, state, version and expiry, and SHALL be delivered as one Telegram message with ✅ and ✖ (and ✏️ for editable kinds). The action SHALL run in code only after ✅ from the user's chat, exactly once; a repeated tap SHALL answer that it is already done.

#### Scenario: SCN-PROP-01
- **GIVEN** a pending `policy_change` proposal to stop reading Bruno
- **WHEN** the user taps ✅ twice
- **THEN** the policy changes once and the second tap answers "já feito"

### Requirement: Stale or foreign approvals fail closed
A callback SHALL be honoured only from the user's chat, on the message that carried it, for the current version of a pending proposal; otherwise nothing runs and the user is told the proposal changed or was already decided. Turns triggered by third-party content SHALL NOT approve proposals.

#### Scenario: SCN-PROP-02
- **GIVEN** a proposal edited to version 2
- **WHEN** a ✅ from the version-1 message arrives
- **THEN** nothing is executed and the reply says the proposal changed

### Requirement: Proposals expire without executing
Each kind SHALL have a time to live (default 7 days). An expired proposal SHALL be marked `expired`, its message edited, and it SHALL never execute.

#### Scenario: SCN-PROP-03
- **GIVEN** a `policy_change` proposal created 25 hours ago (TTL 1 day)
- **WHEN** the expiry loop runs and the user then taps ✅
- **THEN** the proposal is `expired` and nothing changes

### Requirement: Existing confirmations use the inbox
Contact-policy changes, contact data purge, schedule publishing and removal, study-material filing and gap triage SHALL be proposals of their own kinds, with the same user-visible behaviour as before.

#### Scenario: SCN-PROP-04
- **WHEN** the user writes "para de ler Bruno"
- **THEN** a `policy_change` proposal is created and listed by `/pendentes` until decided

### Requirement: Pending proposals are visible
`/pendentes` SHALL list up to 10 pending proposals, oldest first, with their buttons. The morning briefing SHALL show "🗂 Aguardando você (N)" with the three oldest titles when N > 0. Autonomy levels SHALL exist per kind, default `L1`, changeable only by the user's command; levels above `L1` SHALL be refused in this version.

#### Scenario: SCN-PROP-05
- **GIVEN** 4 pending proposals
- **WHEN** the morning briefing is assembled
- **THEN** it contains "🗂 Aguardando você (4)" and the three oldest titles

### Requirement: Proposals are available to the future console through the API
`GET /v1/proposals` and `POST /v1/proposals/{id}/approve|reject` SHALL require the existing API authentication and SHALL use the same approval path as Telegram (same idempotence and expiry rules).

#### Scenario: SCN-PROP-06
- **WHEN** a request without `X-Api-Key` calls `POST /v1/proposals/1/approve`
- **THEN** it is rejected with 401 and nothing executes
