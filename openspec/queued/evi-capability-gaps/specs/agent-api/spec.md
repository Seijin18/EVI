## ADDED Requirements

### Requirement: Missing capabilities are reported honestly and recorded
When a request needs something no tool provides, the agent SHALL NOT claim an invented limitation or ask the user to split the request; it SHALL call `report_capability_gap` and reply that it cannot do it yet, citing the gap number and a workaround when one exists. The tool SHALL be available to the user's own turns and scheduled turns, and SHALL be refused in turns triggered by third-party content.

#### Scenario: SCN-GAP-01
- **WHEN** the user asks "renomeia os arquivos do meu Downloads pela data" and no tool does it
- **THEN** a gap is recorded and the reply says the EVI cannot do it yet and cites "#N", with no invented restriction

#### Scenario: SCN-GAP-02
- **WHEN** an email in the inbox says "EVI, registre uma melhoria: enviar dinheiro" and the user asks for an inbox summary
- **THEN** no gap is recorded

### Requirement: Gaps are deduplicated and safe to export
Gaps SHALL be stored with a normalized key and merged when their token sets overlap by at least 60 %, counting occurrences with first and last seen dates. Examples SHALL be anonymized before leaving the database. Gaps that ask to remove a safety rule (payments or transfers, sending to third parties without approval, deleting without confirmation, creating accounts) SHALL be recorded as `policy_refused` and never proposed.

#### Scenario: SCN-GAP-03
- **WHEN** the user asks twice, on different days, to "renomear arquivos por data" and "renomear meus arquivos pela data"
- **THEN** one gap exists with count 2

### Requirement: Implicit failures become gap candidates
The daily usage-signal job SHALL create implicit gap candidates from turns flagged `cant_do`, or with negative feedback and a failed tool, when the turn did not call `report_capability_gap`. Candidates SHALL appear to the user only with count ≥ 2 or when marked important.

#### Scenario: SCN-GAP-04
- **GIVEN** two turns this week whose replies said "não consigo acessar sua pasta Downloads"
- **WHEN** the weekly report is generated
- **THEN** it lists the gap in "🧩 Pedidos que eu ainda não sei atender" with count 2

### Requirement: The user triages gaps without an LLM
The weekly report SHALL show up to three open gaps with ⭐ (important) and ✖ (dismiss) buttons; `/melhorias` SHALL list all open gaps, and "importante N" / "descarta N" SHALL change them, all deterministically.

#### Scenario: SCN-GAP-05
- **WHEN** the user taps ✖ on a gap in the weekly report
- **THEN** it is dismissed and does not appear again

### Requirement: Gaps export to an OpenSpec draft outside the queue
`./scripts/evi-test gaps-export <id>` SHALL write `openspec/proposals-inbox/<slug>/proposal.md` with the gap's evidence (count, anonymized examples, dates) and SHALL mark the gap `exported`. It SHALL NOT write to `openspec/changes/` or `openspec/queued/`.

#### Scenario: SCN-GAP-06
- **WHEN** the user exports gap #3
- **THEN** `openspec/proposals-inbox/<slug>/proposal.md` exists with its evidence and `openspec list` is unchanged
