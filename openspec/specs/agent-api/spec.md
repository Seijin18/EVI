# Agent API

## Purpose

HTTP surface for EVI: health, chat, tool dispatch, notes, insights, and webhooks.

## Requirements

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

#### Scenario: SCN-RESET-01
- **WHEN** client calls `POST /reset`
- **THEN** bounded memory for the session is cleared

### Requirement: Notes
The system SHALL expose `POST /note` saving Markdown notes to inbox_ia.

#### Scenario: SCN-NOTE-01
- **WHEN** valid note payload is posted
- **THEN** a Markdown file is written under inbox_ia

### Requirement: Session insight
The system SHALL expose `POST /insight` generating auto-insight Markdown.

#### Scenario: SCN-INSIGHT-01
- **WHEN** insight is requested for an active session
- **THEN** response includes generated insight content or a documented stub

### Requirement: Telegram webhook
The system SHALL expose `POST /webhooks/telegram` when `EVI_API_KEY` is set, requiring matching `X-Api-Key` header.

#### Scenario: SCN-TG-02
- **WHEN** request lacks valid `X-Api-Key` while key is configured
- **THEN** HTTP 401 is returned

### Requirement: Pending commitment review tools
The agent SHALL expose tools to list, confirm, and dismiss pending commitments from the Postgres queue.

#### Scenario: SCN-CHAT-02
- **WHEN** user asks to see pending WhatsApp commitments via `/chat`
- **THEN** agent can call `list_pending_commitments` and return structured results

#### Scenario: SCN-CHAT-03
- **WHEN** user confirms commitment ids
- **THEN** agent calls `confirm_commitments` which schedules events via Windmill calendar
