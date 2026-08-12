## Design

### Send result

`agent/services/send_result.py` (new):

```python
@dataclass(frozen=True)
class SendResult:
    sent: bool
    reason: str = ""       # "", transport, http_4xx, not_configured, empty_text
    attempts: int = 0
    detail: str = ""       # truncated exception/body text, for logs only
    def __bool__(self) -> bool: return self.sent
```

`__bool__` is the whole compatibility story: every existing call site is either
`if send_telegram_message(...)` or `sent = send_...(...)` feeding a
`telegram_sent`/`whatsapp_sent` boolean in a JSON body. Truthiness keeps the first
group working untouched; the second group gets `bool(result)` so the wire format
does not change type. Nothing downstream has to learn about the dataclass to keep
behaving as it does today.

### Retry policy

One shared helper, `_post_with_retry(request, *, timeout, attempts, backoff)`, used
by both senders:

- Retry only `URLError`/`OSError`/timeout — transport-level failures, which is what
  a 2-minute network blip produces.
- Never retry `HTTPError` with a 4xx: a bad token, a wrong `chat_id` or a closed
  Evolution instance will fail identically on attempt two, and retrying only delays
  the (now visible) error. 5xx is retried.
- Defaults: `attempts=2`, `backoff=1.5s`, overridable via
  `EVI_SEND_RETRY_ATTEMPTS` / `EVI_SEND_RETRY_BACKOFF_SEC`. Ceiling is deliberately
  low — a Telegram webhook reply happens inside a request the user is waiting on,
  so the worst case must stay well under the harness's timeout.

`soft_fail` is called once, on the final failure, with the reason and attempt count
— not per attempt, to avoid three log lines for one dropped message.

### Why not make the send raise

Tempting, but wrong here: the caller has already persisted the turn and computed a
reply, and a failed delivery must not turn a successful `/chat` into a 500. The
contract stays "never raises"; what changes is that failure is now attributable.

### Heartbeat date comparison

`contact_learning` writes `## Síntese (YYYY-MM-DD, últimos N dias)`.
`contact_memory_audit._last_synthesis_heading` already reads that line; extract the
shared parse into `services/contact_filesystem.py` as
`last_synthesis_date(jid) -> str` (empty when absent or unparseable) and have both
callers use it. Heartbeat then compares `last_ts[:10] > last_synthesis_date(jid)` —
two ISO dates, where lexicographic comparison is correct.

An unparseable heading returns `""`, and `last_ts > ""` is true, so a malformed
profile still flags as stale. That is the safe direction: a false "needs synthesis"
is noise, a false "already synthesised" hides real work.

### Seen-id eviction

`_load_seen_ids`/`_save_seen_ids` keep the JSON array on disk (unchanged format, so
existing `evolution_seen_ids.json` files load as-is) but hold it in a `dict`-backed
ordered set in memory. `claim_message_id` and `filter_for_processing` move newly
seen ids to the end; the trim drops from the front. Same `_MAX_SEEN_IDS` ceiling.

This does not attempt to fix the read-modify-write race between concurrent webhook
threads — that needs a lock or a move into Postgres, and is a different change.

## Out of scope

- **Dev bridge `_REPO_ROOT`** (BACKLOG #33) — still a product decision, not a fix.
- **Structured tool result contract** (#34) — the `if "failed" in result.lower()`
  problem. `SendResult` is deliberately scoped to the two outbound senders; it is
  not a first instalment of the tool contract, which touches all 26 tools.
- **The remaining `except …: return <default>` sites.** Only the two that drop a
  user-visible message are in scope. The rest (contact lookups, parsers) return a
  default that the caller handles sensibly and are not silently losing work.
- **Retry/queue for a persistently unreachable channel.** If Telegram is down for
  minutes, the reply is still lost — a durable outbox is its own change.
- **The `evolution_seen_ids.json` concurrency race**, per above.
