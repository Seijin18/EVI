# Remote access

## Purpose

Telegram and API-key gated access to EVI chat from outside the LAN.
## Requirements
### Requirement: Telegram webhook
The system SHALL accept Telegram updates at `POST /webhooks/telegram` and route text to `/chat` with session `telegram-{chat_id}`.

#### Scenario: SCN-TG-01
- **GIVEN** fixture `tests/fixtures/telegram/update.json`
- **WHEN** `evi-test telegram` runs
- **THEN** parse validates message.text exists

#### Scenario: SCN-TG-02
- **WHEN** `POST /webhooks/telegram` processes a text message with `TELEGRAM_BOT_TOKEN` set
- **THEN** agent replies via Telegram `sendMessage` to the update `chat.id` (`telegram_sent: true`)

### Requirement: API key
When `EVI_API_KEY` is set, protected routes SHALL require `X-Api-Key` header.

#### Scenario: SCN-AUTH-01
- **WHEN** protected route is called without matching key
- **THEN** HTTP 401 is returned

### Requirement: Telegram long polling
When `TELEGRAM_MODE=polling`, agent-api SHALL poll Telegram `getUpdates` and route text messages through the same handler as the webhook.

#### Scenario: SCN-TG-04
- **WHEN** `TELEGRAM_MODE=polling` and `TELEGRAM_BOT_TOKEN` are set at startup
- **THEN** `telegram_poller` runs and `process_telegram_update` handles text updates

### Requirement: Telegram direct calendar bypass
For list/review intents, Telegram handler SHALL call calendar or commitment tools directly without invoking the LLM when regex intent matches.

#### Scenario: SCN-TG-05
- **WHEN** user sends "revise agendamentos" or "listar compromissos pendentes" via Telegram
- **THEN** handler returns `list_calendar_events` or `list_pending_commitments` result with `listed_direct: true`

### Requirement: Live WhatsApp API deferred
The system SHALL NOT require Meta Cloud or Twilio for current verification; Evolution + fixtures cover WhatsApp.

#### Scenario: SCN-WA-DEF-01
- **WHEN** OpenSpec archive for messaging is validated
- **THEN** fixture and Evolution paths are sufficient without live carrier API

### Requirement: All mutating routes gated by API key
When `EVI_API_KEY` is set, every route that mutates state or invokes the agent SHALL require a matching `X-Api-Key` header: `/chat`, `/run-task`, `/reset`, `/note`, `/insight`, `/tools`, `/jobs/*` and both webhooks. `GET /` and `GET /health` SHALL remain unauthenticated so the container healthcheck and scrapers keep working.

#### Scenario: SCN-AUTH-02
- **WHEN** `POST /note`, `POST /insight`, `POST /reset` or `GET /tools` is called without a valid key while `EVI_API_KEY` is set
- **THEN** HTTP 401 is returned

### Requirement: Optional startup enforcement of API key
The system SHALL support `EVI_REQUIRE_API_KEY` (default `false`). When `true` and `EVI_API_KEY` is empty, startup SHALL fail with an explicit error instead of serving unauthenticated routes.

#### Scenario: SCN-AUTH-03
- **WHEN** `EVI_REQUIRE_API_KEY=true` and `EVI_API_KEY` is empty at startup
- **THEN** the application refuses to start and logs the missing-key reason

### Requirement: Data services not published to the LAN
Compose SHALL bind Postgres, Qdrant, Evolution API and Neo4j to `127.0.0.1`, and Qdrant SHALL accept `QDRANT_API_KEY` (passed to the container as `QDRANT__SERVICE__API_KEY` and sent as the `api-key` header by `rag_tool`, the health check and the RAG harness). Only `agent-api` and `windmill-server` may publish on all interfaces. Postgres SHALL use host port 5433 — 5432 is taken by an unrelated container on this machine — while the compose-internal port stays 5432.

#### Scenario: SCN-OPS-04
- **WHEN** `docker compose config` is inspected
- **THEN** postgres (5433), qdrant, evolution-api and neo4j published ports carry host IP `127.0.0.1`, and only agent-api and windmill-server publish without one

### Requirement: Outbound replies survive a transient network failure
Sending a reply to Telegram or WhatsApp SHALL retry transport-level failures (connection refused, network unreachable, timeout, 5xx) up to `EVI_SEND_RETRY_ATTEMPTS` (default 2) with a short backoff, and SHALL NOT retry a 4xx — a bad token, chat id or instance fails identically on the next attempt. A send SHALL never raise: a failed delivery must not turn a successful turn into an HTTP 500.

Both senders SHALL return a `SendResult` that is truthy on success, so existing `if send_...(...)` call sites and the `telegram_sent` / `whatsapp_sent` booleans keep working without change.

#### Scenario: SCN-SEND-01
- **WHEN** the first send attempt raises `URLError`/`OSError` and the second succeeds
- **THEN** the reply is delivered and the result reports `sent: true` with `attempts: 2`
- **AND** a 4xx response is returned immediately with `reason: http_4xx` and exactly one attempt
- **AND** a 5xx is retried, while a missing token or empty body short-circuits to `not_configured` / `empty_text` without any HTTP call

### Requirement: A dropped reply says why
When a reply cannot be delivered, the system SHALL record the reason (`transport`, `http_4xx`, `http_5xx`, `not_configured`, `empty_text`) via `soft_fail` exactly once per dropped message — not once per attempt — and SHALL surface it as `send_error` in the handler response alongside the existing `telegram_sent` / `whatsapp_sent` booleans, whose type and meaning are unchanged and which remain absent-on-success for `send_error`. `./scripts/evi-test telegram --live-telegram` SHALL print the reason rather than only the boolean.

#### Scenario: SCN-SEND-02
- **WHEN** `api.telegram.org` is unreachable for the whole retry budget
- **THEN** `_reply_direct` returns `telegram_sent: false` (a plain bool) with `send_error: "transport"`, and exactly one `soft-fail` line names the failing sender, the reason and the attempt count
- **AND** on success `send_error` is absent from the response

