## ADDED Requirements

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
