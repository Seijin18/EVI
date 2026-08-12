## ADDED Requirements

### Requirement: Outbound replies survive a transient network failure
Sending a reply to Telegram or WhatsApp SHALL retry transport-level failures (connection refused, network unreachable, timeout, 5xx) up to `EVI_SEND_RETRY_ATTEMPTS` (default 2) with a short backoff, and SHALL NOT retry a 4xx — a bad token, chat id or instance fails identically on the next attempt. A send SHALL never raise: a failed delivery must not turn a successful turn into an HTTP 500.

#### Scenario: SCN-SEND-01
- **WHEN** the first send attempt raises `URLError`/`OSError` and the second succeeds
- **THEN** the reply is delivered and the result reports `sent: true` with `attempts: 2`
- **AND** a 4xx response is returned immediately with `reason: http_4xx` and exactly one attempt

### Requirement: A dropped reply says why
When a reply cannot be delivered, the system SHALL record the reason (`transport`, `http_4xx`, `not_configured`, `empty_text`) via `soft_fail` once, and SHALL surface it as `send_error` in the handler response alongside the existing `telegram_sent` / `whatsapp_sent` booleans, whose type and meaning are unchanged. `./scripts/evi-test telegram --live-telegram` SHALL print the reason rather than only the boolean.

#### Scenario: SCN-SEND-02
- **WHEN** `api.telegram.org` is unreachable for the whole retry budget
- **THEN** `process_telegram_update` returns `telegram_sent: false` with `send_error: "transport"`, and one `soft-fail` line names the failing sender and attempt count
