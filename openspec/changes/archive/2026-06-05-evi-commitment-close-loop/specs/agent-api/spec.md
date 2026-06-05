## MODIFIED Requirements

### Requirement: Pending commitment review tools
The agent SHALL expose tools to list, confirm, and dismiss pending commitments from the Postgres queue.

#### Scenario: SCN-CHAT-02
- **WHEN** user asks to see pending WhatsApp commitments via `/chat`
- **THEN** agent can call `list_pending_commitments` and return structured results

#### Scenario: SCN-CHAT-03
- **WHEN** user confirms commitment ids for `type=event`
- **THEN** agent calls `confirm_commitments` which schedules events via Windmill calendar

#### Scenario: SCN-CHAT-04
- **WHEN** user confirms commitment ids for `type=task`
- **THEN** agent calls `confirm_commitments` which creates Google Tasks via Windmill `create_task`
