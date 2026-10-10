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

import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field

from services.soft_fail import soft_fail

PENDING_TOOL = "pending_delete"
TTL_SEC = 600
MAX_DELETE = 50
MAX_CONFIRM_CHARS = 60

_CONFIRM_RE = re.compile(
    r"\b(sim|confirma|confirmo|confirmado|pode apagar|apaga|pode|ok pode|manda ver)\b"
)
_NEGATION_RE = re.compile(r"\b(nao|espera|aguarda|cancela|cancelar|para|pare|calma)\b")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def is_confirmation(text: str | None) -> bool:
    """True for a short, explicit yes ("sim", "pode apagar", "manda ver") with no
    negation ("não", "espera", "cancela"). Accent/case-insensitive."""
    raw = str(text or "")
    if not raw.strip() or len(raw.strip()) > MAX_CONFIRM_CHARS:
        return False
    norm = _normalize(raw)
    if _NEGATION_RE.search(norm):
        return False
    return bool(_CONFIRM_RE.search(norm))


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
    return token


def clear_pending(session_id: str) -> None:
    try:
        from db import init_db, save_tool_snapshot

        init_db()
        save_tool_snapshot(session_id, PENDING_TOOL, {"cleared": True})
    except Exception as exc:
        soft_fail("write_guard.clear_pending", exc)


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
    if not secrets.compare_digest(str(pending["token"]), str(token or "")):
        return Check(False, "token de confirmação desconhecido; peça a prévia primeiro")
    if (now if now is not None else time.time()) > float(pending.get("expires_at", 0)):
        return Check(False, "a confirmação expirou (10 min); peça a prévia novamente")
    if turn_seq <= int(pending.get("created_turn", 0)):
        return Check(False, "preciso da confirmação do usuário em uma nova mensagem")
    if not is_confirmation(user_text):
        return Check(False, "a mensagem do usuário neste turno não é uma confirmação explícita")
    ids = [str(i) for i in pending.get("ids") or []]
    if not ids:
        return Check(False, "exclusão pendente sem e-mails")
    return Check(True, ids=ids)
