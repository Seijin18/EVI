"""Briefing diário determinístico (sem LLM): agenda, tarefas, e-mail e WhatsApp.

Cada fonte é coletada de forma isolada (``ThreadPoolExecutor(4)``); a falha de
uma vira ``Section(error=...)`` e as demais seguem. Os itens são numerados de
forma contínua (1..N) entre seções, para que "confirma 4" possa ser resolvido
pelo snapshot ``morning_briefing`` (entrega/snapshot ficam em outra task).

Conteúdo de terceiros (assunto/remetente, texto de compromisso, nome de evento)
passa por ``wrap_external`` — nenhum LLM é construído aqui.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db
from integrations.factory import get_integration
from services.probe import _resource
from services.soft_fail import soft_fail
from services.tool_result import OAUTH, ToolResult, parse_windmill_result
from services.untrusted import wrap_external
from tools.calendar_time import evi_timezone, now_local

MAX_CHARS = 4000
LIMITS = {"calendar": 8, "tasks": 5, "email": 3, "whatsapp": 5}
_EMAIL_FETCH = 15
_EMAIL_DROP_LABELS = frozenset({"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES"})
_NOREPLY_RE = re.compile(r"no-?reply", re.IGNORECASE)
_FREE_DAY = "Dia livre: sem eventos, tarefas ou pendências"
_TRUNC = "…[truncado]"
_WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
_FIELD_MAX = 120


@dataclass(frozen=True)
class BriefItem:
    n: int  # número global exibido (1..N, contínuo entre seções)
    text: str  # linha já formatada; campos de terceiros já delimitados
    ref: dict  # {"kind": "commitment", "id": 12} | {"kind": "email", "id": "18f…"} | …
    group: str = ""  # sub-rótulo dentro da seção (WhatsApp com reply-debts); "" = sem grupo


@dataclass(frozen=True)
class Section:
    key: str  # "calendar" | "tasks" | "email" | "whatsapp"
    title: str
    items: list[BriefItem] = field(default_factory=list)
    error: str = ""  # motivo legível quando a fonte falhou
    more: int = 0  # itens omitidos pelo limite da seção ("+N")
    group_more: dict = field(default_factory=dict)  # grupo -> omitidos ("+N" por grupo)


@dataclass(frozen=True)
class Briefing:
    text: str
    sections: list[Section]
    items: list[BriefItem]


_TITLES = {"calendar": "Agenda", "tasks": "Tarefas", "email": "E-mail", "whatsapp": "WhatsApp"}


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(evi_timezone())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


def _email_max() -> int:
    try:
        return max(1, int(os.getenv("EVI_BRIEFING_EMAIL_MAX", "3")))
    except ValueError:
        return 3


# ---------------------------------------------------------------- errors


def _reason_text(out: ToolResult) -> str:
    if out.reason == OAUTH:
        return "credencial expirada — reconecte no Windmill"
    detail = " ".join((out.detail or "").split())[:100]
    labels = {
        "not_configured": "integração não configurada",
        "http_error": "erro de comunicação com o Windmill",
        "unparseable": "resposta ilegível do Windmill",
    }
    base = labels.get(out.reason, "falha na fonte")
    return f"{base} ({detail})" if detail else base


class _SourceError(Exception):
    pass


def _call(op: str, payload: dict[str, Any], *, action: str, env: str, timeout: int) -> dict:
    raw = get_integration().post(op, payload, timeout=timeout, wait_result=True)
    out = parse_windmill_result(raw, action=action, resource_env=env)
    if not out.ok:
        raise _SourceError(_reason_text(out))
    return out.data or {}


# ---------------------------------------------------------------- sources


def _parse_iso(value: str, tz: ZoneInfo) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)


def _collect_calendar(day: date) -> list[tuple[str, dict]]:
    payload = {
        "gcal": _resource("calendar"),
        "calendar_id": os.getenv("WINDMILL_CALENDAR_ID", "primary").strip() or "primary",
        "timezone": evi_timezone(),
        "days_ahead": 1,
        "max_results": 50,
        "on_date": day.isoformat(),
    }
    blob = _call(
        "list_events", payload, action="listar eventos",
        env="WINDMILL_GCAL_RESOURCE", timeout=120,
    )
    tz = _tz()
    events = []
    for ev in blob.get("events") or []:
        start_s, end_s = str(ev.get("start_iso") or ""), str(ev.get("end_iso") or "")
        timed = "T" in start_s
        start = _parse_iso(start_s, tz) if timed else None
        end = _parse_iso(end_s, tz) if timed and "T" in end_s else None
        events.append({"ev": ev, "start": start, "end": end})
    events.sort(key=lambda e: (e["start"] is None, e["start"] or datetime.max.replace(tzinfo=tz)))
    conflicts: set[int] = set()
    timed_evs = [(i, e) for i, e in enumerate(events) if e["start"] and e["end"]]
    for a in range(len(timed_evs)):
        for b in range(a + 1, len(timed_evs)):
            (i, ea), (j, eb) = timed_evs[a], timed_evs[b]
            if ea["start"] < eb["end"] and eb["start"] < ea["end"]:
                conflicts.update((i, j))
    rows = []
    for i, e in enumerate(events):
        ev = e["ev"]
        if e["start"]:
            when = e["start"].strftime("%H:%M")
            if e["end"]:
                when += "–" + e["end"].strftime("%H:%M")
        else:
            when = "dia todo"
        name = wrap_external(ev.get("summary") or "(sem título)", "agenda", _FIELD_MAX)
        line = f"{when} {name}" + (" ⚠ conflito de horário" if i in conflicts else "")
        rows.append((line, {"kind": "event", "id": ev.get("id") or ""}))
    return rows


def _collect_tasks(day: date, overdue: bool) -> list[tuple[str, dict]]:
    payload = {"gtasks": _resource("tasks"), "max_results": 100, "show_completed": False}
    blob = _call(
        "list_tasks", payload, action="listar tarefas",
        env="WINDMILL_GTASKS_RESOURCE", timeout=120,
    )
    rows = []
    for t in blob.get("tasks") or []:
        if t.get("status") == "completed":
            continue
        due = str(t.get("due") or "")[:10]
        try:
            due_d = date.fromisoformat(due)
        except ValueError:
            continue  # sem prazo
        if due_d != day and not (overdue and due_d < day):
            continue
        title = wrap_external(t.get("title") or "(sem título)", "tarefa", _FIELD_MAX)
        tag = f" (venceu {due_d.strftime('%d/%m')})" if due_d < day else ""
        rows.append((f"{title}{tag}", {"kind": "task", "id": t.get("id") or ""}, due_d))
    rows.sort(key=lambda r: r[2])
    return [(text, ref) for text, ref, _ in rows]


def _msg_time(msg: dict) -> datetime | None:
    raw = str(msg.get("date") or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def select_emails(messages: list[dict]) -> list[dict]:
    """Heurística v1: sem promoções/social/updates e sem no-reply; mais recentes primeiro.

    Sem ``labelIds`` na mensagem, vale só o filtro de remetente.
    """
    kept = []
    for m in messages:
        labels = set(m.get("labelIds") or [])
        if labels & _EMAIL_DROP_LABELS:
            continue
        if _NOREPLY_RE.search(str(m.get("from") or "")):
            continue
        kept.append(m)
    times = [_msg_time(m) for m in kept]
    if kept and all(times):
        kept = [m for _, m in sorted(zip(times, kept), key=lambda p: p[0], reverse=True)]
    return kept  # sem datas: ordem da API (Gmail lista do mais recente ao mais antigo)


def _collect_email() -> list[tuple[str, dict]]:
    payload = {"max_messages": _EMAIL_FETCH, "gmail": _resource("gmail")}
    blob = _call(
        "summarize_inbox", payload, action="acessar o Gmail",
        env="WINDMILL_GMAIL_RESOURCE", timeout=180,
    )
    rows = []
    for m in select_emails(list(blob.get("messages") or [])):
        subj = wrap_external(m.get("subject") or "(sem assunto)", "email", _FIELD_MAX)
        sender = wrap_external(m.get("from") or "", "email", _FIELD_MAX)
        rows.append((f"{subj} — {sender}", {"kind": "email", "id": m.get("id") or ""}))
    return rows


GROUP_DEBTS = "Esperando sua resposta"
GROUP_PROMISES = "Suas promessas"
GROUP_COMMITMENTS = "Combinados"
GROUP_LIMIT = 3


def _commitment_when(c: dict) -> str:
    when = c.get("event_date") or c.get("due_date") or ""
    if when:
        try:
            return date.fromisoformat(str(when)[:10]).strftime("%d/%m")
        except ValueError:
            return ""
    return ""


def _debt_age(hours: float) -> str:
    if hours < 48:
        return f"há {max(1, int(hours))} h"
    return f"há {int(hours // 24)} d"


def _collect_whatsapp() -> list[tuple]:
    from services.whatsapp_processor import reply_debts_enabled

    grouped = reply_debts_enabled()
    rows: list[tuple] = []
    debts: list[tuple] = []
    promises: list[tuple] = []
    for c in db.list_pending_commitments(limit=50):
        text = wrap_external(c.get("title") or c.get("raw_text") or "", "whatsapp", _FIELD_MAX)
        who = c.get("source_label") or c.get("source_chat") or ""
        when = _commitment_when(c)
        line = text
        if who:
            line += f" — {wrap_external(who, 'whatsapp', 60)}"
        if when:
            line += f" ({when})"
        ref = {"kind": "commitment", "id": c.get("id")}
        if not grouped:
            rows.append((line, ref))
        elif c.get("type") == "promise":
            promises.append((line, ref, GROUP_PROMISES))
        else:
            rows.append((line, ref, GROUP_COMMITMENTS))
    if not grouped:
        return rows
    from services.reply_debts import list_debts

    for d in list_debts():
        line = (
            f"{wrap_external(d.get('name') or d['jid'], 'whatsapp', 60)} — "
            f"{_debt_age(d['age_h'])}: {wrap_external(d.get('preview') or '', 'whatsapp', _FIELD_MAX)}"
        )
        debts.append((line, {"kind": "reply_debt", "id": d["jid"]}, GROUP_DEBTS))
    return debts + promises + rows


# ---------------------------------------------------------------- assembly


def _run_source(key: str, fn: Callable[[], list[tuple]]) -> Section:
    title = _TITLES[key]
    try:
        rows = fn()
    except _SourceError as exc:
        return Section(key, title, error=str(exc))
    except Exception as exc:  # isolada: nunca derruba as outras fontes
        soft_fail(f"briefing.{key}", exc)
        return Section(key, title, error=f"falha inesperada ({str(exc)[:100]})")
    if rows and len(rows[0]) == 3:  # grupos rotulados: teto e "+N" por grupo
        items: list[BriefItem] = []
        group_more: dict = {}
        counts: dict = {}
        for text, ref, group in rows:
            counts[group] = counts.get(group, 0) + 1
            if counts[group] <= GROUP_LIMIT:
                items.append(BriefItem(0, text, ref, group))
        for group, total in counts.items():
            if total > GROUP_LIMIT:
                group_more[group] = total - GROUP_LIMIT
        return Section(key, title, items=items, group_more=group_more)
    limit = _email_max() if key == "email" else LIMITS[key]
    items = [BriefItem(0, text, ref) for text, ref in rows[:limit]]
    return Section(key, title, items=items, more=max(0, len(rows) - limit))


def _header(now: datetime, day: date, kind: str) -> str:
    stamp = f"{_WEEKDAYS[day.weekday()]}, {day.strftime('%d/%m')}"
    if kind == "evening":
        return f"Boa noite! Amanhã: {stamp}"
    return f"Bom dia! {stamp}"


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    cut = text[: MAX_CHARS - len(_TRUNC)]
    cut = cut[: cut.rfind("\n")] if "\n" in cut else cut
    return cut.rstrip() + "\n" + _TRUNC


def assemble_briefing(kind: str = "morning", now: datetime | None = None) -> Briefing:
    """Monta o briefing sem LLM. ``kind="evening"`` é a prévia de amanhã."""
    now = now or now_local()
    evening = kind == "evening"
    day = now.date() + timedelta(days=1) if evening else now.date()
    sources: list[tuple[str, Callable[[], list[tuple]]]] = [
        ("calendar", lambda: _collect_calendar(day)),
        ("tasks", lambda: _collect_tasks(day, overdue=not evening)),
        ("email", _collect_email),
        ("whatsapp", _collect_whatsapp),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_source, key, fn) for key, fn in sources]
        raw_sections = [f.result() for f in futures]

    n = 0
    sections: list[Section] = []
    for sec in raw_sections:
        numbered = []
        for it in sec.items:
            n += 1
            numbered.append(replace(it, n=n))
        sections.append(replace(sec, items=numbered))
    items = [it for sec in sections for it in sec.items]

    lines = [_header(now, day, kind)]
    if not items and not any(s.error for s in sections):
        lines.append(_FREE_DAY)
    for sec in sections:
        if sec.error:
            lines.append(f"⚠ {sec.title} indisponível — {sec.error}")
        elif sec.items:
            lines.append(f"\n{sec.title}")
            cur = None
            for i, it in enumerate(sec.items):
                if it.group and it.group != cur:
                    cur = it.group
                    lines.append(f"{cur}:")
                lines.append(f"{it.n}. {it.text}")
                nxt = sec.items[i + 1].group if i + 1 < len(sec.items) else None
                if it.group and nxt != it.group and sec.group_more.get(it.group):
                    lines.append(f"+{sec.group_more[it.group]}")
            if sec.more:
                lines.append(f"+{sec.more}")
    return Briefing(_truncate("\n".join(lines)), sections, items)


REPLY_WINDOW = timedelta(hours=3)
_KINDS = ("morning", "evening")


def _telegram_session_id(chat_id: str) -> str:
    # Mesmo formato de services/telegram_handler.py (`f"telegram-{chat_id}"`).
    return f"telegram-{chat_id}"


NO_BRIEFING_TODAY = "não há briefing de hoje para resolver os números"


def resolve_briefing_items(
    numbers: list[int], session_id: str | None = None, kind: str = "commitment"
) -> tuple[list, list[str]]:
    """Mapeia números do briefing de hoje ("confirma 2") para ids reais.

    Lê o último snapshot ``morning_briefing`` do dia local da sessão (padrão: a do
    turno atual; fallback: a sessão Telegram configurada). Retorna ``(ids, erros)``.
    """
    if session_id is None:
        from services.turn_log import current_session_id

        session_id = current_session_id()
    if not session_id:
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        session_id = _telegram_session_id(chat_id) if chat_id else None
    nums = [int(n) for n in numbers]
    refs: dict | None = None
    if session_id:
        try:
            today = now_local().date()
            tz = now_local().tzinfo
            for row in db.load_tool_snapshots(session_id, limit=50):
                if row.get("tool_name") != "morning_briefing":
                    continue
                created = datetime.fromisoformat(str(row.get("created_at")))
                if created.tzinfo is not None and tz is not None:
                    created = created.astimezone(tz)
                if created.date() == today:
                    refs = (row.get("payload") or {}).get("refs") or {}
                break
        except Exception as exc:
            soft_fail("briefing.resolve_items", exc)
    if refs is None:
        return [], [NO_BRIEFING_TODAY] if nums else []
    label = {"commitment": "um compromisso", "reply_debt": "uma conversa esperando resposta"}.get(kind, f"do tipo {kind}")
    ids: list = []
    errors: list[str] = []
    for n in nums:
        ref = refs.get(str(n))
        if ref is None:
            errors.append(f"item {n} não existe no briefing")
            continue
        ref_kind, _, ref_id = str(ref).partition(":")
        if kind == "reply_debt":
            if ref_kind != kind or not ref_id:
                errors.append(f"item {n} do briefing não é {label}")
            elif ref_id not in ids:
                ids.append(ref_id)
            continue
        if ref_kind != kind or not ref_id.lstrip("-").isdigit():
            errors.append(f"item {n} do briefing não é {label}")
            continue
        if int(ref_id) not in ids:
            ids.append(int(ref_id))
    return ids, errors


def deliver_briefing(kind: str = "morning", force: bool = False, now: datetime | None = None) -> dict:
    """Monta e envia o briefing ao Telegram; só o envio propaga falha.

    Idempotente por ``(dia local, kind)``: com ``force=False`` um envio ``ok``
    anterior vira ``already_sent``; uma falha (``ok=false``) pode ser repetida.
    Antes de montar, reivindica o slot de forma atômica (``db.claim_briefing``): uma
    segunda chamada concorrente recebe ``in_progress``. ``force=True`` ignora o claim.
    """
    from services.telegram_notify import send_telegram_message

    now = now or now_local()
    day = now.date()
    try:
        if not force and db.claim_briefing(day, kind, stale_minutes=10) is None:
            status = "already_sent" if db.briefing_sent_today(day, kind) else "in_progress"
            return {"status": status, "kind": kind, "day": day.isoformat()}
    except Exception as exc:
        soft_fail("briefing.deliver.idempotency", exc)

    brief = assemble_briefing(kind, now)
    sections = {s.key: {"count": len(s.items), "error": s.error} for s in brief.sections}
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    result = send_telegram_message(brief.text, chat_id or None)

    ok = bool(result)
    try:
        db.record_briefing(day, kind, ok, sections)
    except Exception as exc:
        soft_fail("briefing.deliver.record", exc)
    try:
        from services import metrics

        metrics.record_briefing_sent(kind, ok)
    except Exception as exc:
        soft_fail("briefing.deliver.metrics", exc)
    if not ok:
        return {"status": "failed", "kind": kind, "reason": getattr(result, "reason", "") or "send_failed"}

    session_id = _telegram_session_id(chat_id)
    try:
        from langchain_core.messages import AIMessage

        from services.session_memory import get_session_memory

        get_session_memory(session_id).add(AIMessage(content=brief.text))
    except Exception as exc:
        soft_fail("briefing.deliver.memory", exc)
    if os.getenv("DATABASE_URL"):
        # main._hydrate_memory recarrega a memória do Postgres a cada turno: sem isto
        # a primeira resposta apagaria o briefing do contexto.
        try:
            db.save_message(session_id, "assistant", brief.text)
        except Exception as exc:
            soft_fail("briefing.deliver.persist_message", exc)
    try:
        db.save_tool_snapshot(
            session_id,
            "morning_briefing",
            {
                "kind": kind,
                "day": day.isoformat(),
                # compacto ("n": "kind:id"): format_tool_snapshots corta em 1200 chars
                "refs": {str(it.n): f"{it.ref.get('kind')}:{it.ref.get('id')}" for it in brief.items},
            },
        )
    except Exception as exc:
        soft_fail("briefing.deliver.snapshot", exc)
    return {
        "status": "sent",
        "kind": kind,
        "day": day.isoformat(),
        "items": len(brief.items),
        "sections": sections,
    }


def note_user_reply(now: datetime | None = None, user_text: str = "") -> int:
    """Conta engajamento: mensagem do usuário até 3 h após o envio. Nunca levanta.

    Comandos (``/bom``…) não contam. Janela relativa a ``now()`` do banco (vale
    também atravessando a meia-noite). Retorna quantos briefings foram marcados.
    """
    try:
        if (user_text or "").lstrip().startswith("/"):
            return 0
        kinds = db.mark_briefing_replied_window(hours=int(REPLY_WINDOW.total_seconds() // 3600))
        if kinds:
            from services import metrics

            for kind in kinds:
                metrics.record_briefing_replied(kind)
        return len(kinds)
    except Exception as exc:
        soft_fail("briefing.note_user_reply", exc)
        return 0
