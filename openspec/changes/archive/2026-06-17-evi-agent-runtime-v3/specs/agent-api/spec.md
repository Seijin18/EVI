## ADDED Requirements

### Requirement: Context assembly before chat
The system SHALL assemble project context from workspace bootstrap files, session tool snapshots, and memory files before invoking the LangGraph agent.

#### Scenario: SCN-RT-01
- **WHEN** `POST /chat` runs with `session_id` set
- **THEN** the agent system prompt includes workspace bootstrap content when files exist

### Requirement: Session tool snapshots
The system SHALL persist structured JSON results from tool calls per session for follow-up turns.

#### Scenario: SCN-RT-02
- **WHEN** a chat turn completes with tool results
- **THEN** snapshots are stored in Postgres `session_tool_snapshots`
