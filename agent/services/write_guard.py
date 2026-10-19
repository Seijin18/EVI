"""Guards for destructive write tools (evi-prompt-injection-model).

Two-step deletion: the first call stores a ``pending_delete`` snapshot for the
session (token, exact ids, creating turn, expiry) and deletes nothing. A second
call only executes when, in code, (a) the token matches the session's pending
snapshot and is unexpired, (b) the current turn is *later* than the one that
created it, and (c) the user's own message of THIS turn (taken from the turn
collector, never from the model) is an explicit confirmation without negation.
Content read from e-mail/WhatsApp cannot satisfy (b)+(c): it needs a new user
message.
"""

from __future__ import annotations

import functools
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field

from services.soft_fail import soft_fail

# Write tools by turn origin (design §2): the allowlist is checked in code, not in
# the prompt. A tool called from a turn whose channel is not user-initiated is blocked.
WRITE_TOOLS = frozenset(
    {
        "schedule_event",
        "create_task",
        "delete_emails",
        "delete_emails_by_query",
        "confirm_commitments",
        "dismiss_commitments",
        "set_whatsapp_contact_name",
        "learn_whatsapp_contact",
        "create_reminder",
        "cancel_reminder",
        "snooze_reminder",
        "complete_reminder",
        "create_scheduled_task",
        "cancel_scheduled_task",
        "pause_scheduled_task",
        "resume_scheduled_task",
        "dismiss_reply_debt",
        "organize_inbox",
        "save_note_manual",
        "ingest_university_pdf",
        "ingest_university_folder",
    }
)
USER_CHANNELS = frozenset({"telegram", "whatsapp_control", "api"})
# Turns run by the scheduler (evi-scheduled-tasks): read-only, refused here even if a
# write tool were ever bound to that graph (defense in depth, independent of USER_CHANNELS).
SCHEDULED_CHANNEL = "scheduled"
BLOCKED_MESSAGE = "ação bloqueada: turno não iniciado pelo usuário"

PENDING_TOOL = "pending_delete"
TTL_SEC = 600
MAX_DELETE = 50
MAX_CONFIRM_CHARS = 30

# Closed set of accepted confirmations (normalized: no accents/case/punctuation),
# optionally followed by "por favor"/"pfv". Anything else is NOT a confirmation.
_CONFIRM_RE = re.compile(
    r"^(sim|s|confirmo|confirma|pode apagar|sim pode apagar|ok pode apagar|sim pode"
    r"|manda ver|pode sim)( (por favor|pfv))?$"
)
_DELETE_INTENT_RE = re.compile(r"apag|delet|exclu|lixeira|limp|remov|jog\w* fora|joga fora")
NO_INTENT_MESSAGE = "Só apago e-mails quando você pede."


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def is_confirmation(text: str | None) -> bool:
    """True only when the whole (normalized) message is one of the closed-set yes
    phrases ("sim", "pode apagar", "manda ver"...). Quoted text, qualifiers
    ("sim, mas só os de ontem") and everything else are False."""
    raw = str(text or "").strip()
    if not raw or len(raw) > MAX_CONFIRM_CHARS:
        return False
    return bool(_CONFIRM_RE.match(_normalize(raw)))


def pending_created_this_turn():
    """Re-export of turn_log.pending_created_this_turn (lazy: avoids an import cycle)."""
    from services.turn_log import pending_created_this_turn as _p

    return _p()


def has_delete_intent(text: str | None) -> bool:
    """True when the user's own message of this turn talks about deleting."""
    return bool(_DELETE_INTENT_RE.search(_normalize(text or "")))


# In-process bookkeeping so a confirmation only counts in the turn IMMEDIATELY after
# the staging turn (fail-closed after a restart: unknown last turn -> refuse).
_staged: dict[str, int] = {}  # session -> turn that created the pending delete
_last_turn: dict[str, int] = {}  # session -> seq of the last completed turn
_MAX_SESSIONS = 2000


def on_turn_end(session_id: str | None, turn_seq: int | None) -> None:
    """Called by turn_log.end_turn. Records the completed turn and clears a pending
    delete created in an EARLIER turn and not consumed in this one."""
    if not session_id or turn_seq is None:
        return
    if len(_last_turn) > _MAX_SESSIONS:
        _last_turn.clear()
    _last_turn[session_id] = turn_seq
    staged = _staged.get(session_id)
    if staged is not None and staged < turn_seq:
        _staged.pop(session_id, None)
        clear_pending(session_id)


@dataclass
class Check:
    ok: bool
    reason: str = ""
    ids: list[str] = field(default_factory=list)


def new_token() -> str:
    return secrets.token_urlsafe(8)


def _load_latest(session_id: str) -> dict | None:
    from db import init_db, load_tool_snapshots

    init_db()
    for row in load_tool_snapshots(session_id, limit=50):
        if row.get("tool_name") == PENDING_TOOL:
            return row.get("payload") or None
    return None


def create_pending(
    session_id: str, ids: list[str], turn_seq: int, query: str = ""
) -> str | None:
    """Store a pending deletion; returns the token, or None if it can't be persisted."""
    token = new_token()
    payload = {
        "token": token,
        "ids": list(ids),
        "query": query,
        "created_turn": turn_seq,
        "expires_at": time.time() + TTL_SEC,
        "count": len(ids),
    }
    try:
        from db import init_db, save_tool_snapshot

        init_db()
        save_tool_snapshot(session_id, PENDING_TOOL, payload)
    except Exception as exc:
        soft_fail("write_guard.create_pending", exc)
        return None
    _staged[session_id] = turn_seq
    return token


def clear_pending(session_id: str) -> None:
    _staged.pop(session_id, None)
    try:
        from db import init_db, save_tool_snapshot

        init_db()
        save_tool_snapshot(session_id, PENDING_TOOL, {"cleared": True})
    except Exception as exc:
        soft_fail("write_guard.clear_pending", exc)


def _token_matches(expected: str, given: str) -> bool:
    """Constant-time compare on bytes; never raises on non-ASCII input."""
    try:
        return secrets.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))
    except Exception:
        return False


def check_confirmation(
    session_id: str | None,
    token: str,
    user_text: str,
    turn_seq: int | None,
    now: float | None = None,
) -> Check:
    """Validate a confirm call. Never raises; a failure is a refusal."""
    if not session_id or turn_seq is None:
        return Check(False, "sem turno do usuário em andamento")
    try:
        pending = _load_latest(session_id)
    except Exception as exc:
        soft_fail("write_guard.check_confirmation", exc)
        return Check(False, "não consegui verificar a confirmação pendente")
    if not pending or pending.get("cleared") or not pending.get("token"):
        return Check(False, "não há exclusão pendente para confirmar; peça a prévia primeiro")
    if not _token_matches(str(pending["token"]), str(token or "")):
        return Check(False, "token de confirmação desconhecido; peça a prévia primeiro")
    if (now if now is not None else time.time()) > float(pending.get("expires_at", 0)):
        return Check(False, "a confirmação expirou (10 min); peça a prévia novamente")
    created = int(pending.get("created_turn", 0))
    if turn_seq <= created:
        return Check(False, "preciso da confirmação do usuário em uma nova mensagem")
    if _last_turn.get(session_id) != created:
        return Check(False, "a confirmação precisa ser a mensagem logo após a prévia")
    if not is_confirmation(user_text):
        return Check(False, "a mensagem do usuário neste turno não é uma confirmação explícita")
    ids = [str(i) for i in pending.get("ids") or []]
    if not ids:
        return Check(False, "exclusão pendente sem e-mails")
    return Check(True, ids=ids)


def check_write(tool_name: str) -> str | None:
    """Blocked message when a write tool runs in a turn the user did not start.

    Channel ``None`` means no turn is in progress (unit tests, internal callers such
    as confirm_commitments -> schedule_event_result): it is NOT an LLM turn, so it is
    allowed. Any known channel outside USER_CHANNELS (``job`` or other) is blocked.
    """
    from services.turn_log import current_channel

    channel = current_channel()
    if channel == SCHEDULED_CHANNEL:
        return f"{BLOCKED_MESSAGE} (canal: {channel}; ferramenta: {tool_name})"
    if channel is None or channel in USER_CHANNELS:
        return None
    return f"{BLOCKED_MESSAGE} (canal: {channel}; ferramenta: {tool_name})"


def guarded_write(fn):
    """Decorator for write tools (apply under ``@tool``): runs check_write first.

    functools.wraps keeps name, docstring and signature, so LangChain's schema is
    unchanged."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        blocked = check_write(fn.__name__)
        if blocked:
            return blocked
        return fn(*args, **kwargs)

    return wrapper
