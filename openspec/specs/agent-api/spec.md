# Agent API

## ADDED Requirements

### Requirement: Health
The system SHALL expose `GET /` returning status and service list.

#### Scenario: SCN-API-01
- **WHEN** client calls `GET /`
- **THEN** response status is 200 with `status` field

### Requirement: Chat
The system SHALL expose `POST /chat` accepting `message` and optional `session_id`.

#### Scenario: SCN-CHAT-01
- **WHEN** valid message posted and graph initialized
- **THEN** response includes `response` text

### Requirement: Tools dispatch
The system SHALL expose `POST /run-task` with `task` name and `params` object.

#### Scenario: SCN-TASK-01
- **WHEN** unknown task name is sent
- **THEN** HTTP 404 is returned

### Requirement: Memory reset
The system SHALL expose `POST /reset` clearing bounded in-memory history.

### Requirement: Notes
The system SHALL expose `POST /note` saving Markdown notes to inbox_ia.

### Requirement: Session insight
The system SHALL expose `POST /insight` generating auto-insight Markdown.

### Requirement: Telegram webhook
The system SHALL expose `POST /webhooks/telegram` when `EVI_API_KEY` is set, requiring matching `X-Api-Key` header.
