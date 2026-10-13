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
`EVI_API_KEY` SHALL be required: the agent SHALL refuse to start without it unless explicitly running in an offline test mode, and every route except `/` and `/health` SHALL require a matching `X-Api-Key` header.

#### Scenario: SCN-AUTH-01
- **WHEN** protected route is called without matching key
- **THEN** HTTP 401 is returned

#### Scenario: SCN-SEC-05
- **GIVEN** `EVI_API_KEY` is empty and no offline test mode is set
- **WHEN** the agent starts
- **THEN** startup fails with an error naming the missing key

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

### Requirement: No official WhatsApp carrier API
The system SHALL NOT require Meta Cloud or Twilio; Evolution + fixtures cover WhatsApp. The official Business API forbids general-purpose assistants since 2026-01-15, so no carrier adapter is planned.

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
Compose SHALL bind every published port (Postgres, Qdrant, Evolution API, Neo4j, `agent-api` and `windmill-server`) to `127.0.0.1`, and Qdrant SHALL accept `QDRANT_API_KEY` (passed to the container as `QDRANT__SERVICE__API_KEY` and sent as the `api-key` header by `rag_tool`, the health check and the RAG harness). Postgres SHALL use host port 5433 — 5432 is taken by an unrelated container on this machine — while the compose-internal port stays 5432. Remote access SHALL go through an SSH tunnel or `tailscale serve`, never through a wider bind.

#### Scenario: SCN-OPS-04
- **WHEN** `docker compose config` is inspected
- **THEN** every published port carries host IP `127.0.0.1`

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

### Requirement: Services are not published beyond the host by default
Every port published in `docker-compose.yml` SHALL be bound to `127.0.0.1`; access from other machines SHALL go only through a path recorded in the threat model (Tailscale) and SHALL still require authentication.

#### Scenario: SCN-SEC-01
- **WHEN** another machine on the LAN connects to ports 8001 or 8002 of the host
- **THEN** the connection is refused

### Requirement: No default secrets in use
Services SHALL NOT run with the default secrets shipped in examples (`evi-dev-key`, `changeme`, `windmill`), Qdrant SHALL require an API key, and `.env`, `data/` and `logs/` SHALL be readable only by the owner.

#### Scenario: SCN-SEC-04
- **WHEN** `./scripts/evi-security-scan` runs
- **THEN** it reports no default secret in use and no group/world-readable secret or data path

