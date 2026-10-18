"""Briefing diário determinístico (sem LLM): agenda, tarefas, e-mail e WhatsApp.

Cada fonte é coletada de forma isolada (``ThreadPoolExecutor(4)``); a falha de
uma vira ``Section(error=...)`` e as demais seguem. Os itens são numerados de
forma contínua (1..N) entre seções, para que "confirma 4" possa ser resolvido
pelo snapshot ``morning_briefing`` (entrega/snapshot ficam em outra task).

Duas renderizações do mesmo conteúdo: ``Briefing.text`` (= ``text_model``) guarda
o texto de terceiros delimitado por ``wrap_external`` — é o que vai para a memória da
sessão/LLM; ``Briefing.text_user`` é o que o usuário lê no Telegram (HTML do Telegram,
sem marcadores, todo texto dinâmico escapado). Nenhum LLM é construído aqui.
"""

from __future__ import annotations

import html
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from email.utils import parseaddr
from typing import Any, Callable, NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db
from integrations.factory import get_integration
from services.probe import _resource
from services.soft_fail import soft_fail
from services.tool_result import OAUTH, ToolResult, parse_windmill_result
from services.untrusted import plain_external, strip_markers, wrap_external
from services.ux_format import short_age as _short_age
from services.ux_format import short_day as _short_day
from services.ux_format import short_due as _short_due
from services.ux_format import who_label as _who_label
from tools.calendar_time import evi_timezone, now_local

MAX_CHARS = 4000
LIMITS = {"calendar": 8, "tasks": 5, "email": 3, "whatsapp": 5, "names": 3}
MAX_LINES = 25  # orçamento de linhas do texto do usuário (SCN-UX-04)
# Seções que viram linha-resumo primeiro (menor prioridade primeiro); a ordem de exibição não muda.
COLLAPSE_ORDER = ("email", "tasks", "calendar", "names", "whatsapp")
_EMAIL_FETCH = 15
_EMAIL_DROP_LABELS = frozenset({"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES"})
_NOREPLY_RE = re.compile(r"no-?reply", re.IGNORECASE)
_FREE_DAY = "Dia livre: sem eventos, tarefas ou pendências"
_TRUNC = "…[truncado]"
_WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
_FIELD_MAX = 120
_RM_TITLE_MAX = 80  # reminder text taken from an item title (evi-discovery-tips)
_EVENING_FREE = "Amanhã está livre."


@dataclass(frozen=True)
class BriefItem:
    n: int  # número global exibido (1..N, contínuo entre seções)
    text: str  # linha já formatada; campos de terceiros já delimitados
    ref: dict  # {"kind": "commitment", "id": 12} | {"kind": "email", "id": "18f…"} | …
    group: str = ""  # sub-rótulo dentro da seção (WhatsApp com reply-debts); "" = sem grupo
    user: str = ""  # linha para o usuário (HTML do Telegram, escapada); "" = derivar de ``text``


@dataclass(frozen=True)
class Section:
    key: str  # "calendar" | "tasks" | "email" | "whatsapp"
    title: str
    items: list[BriefItem] = field(default_factory=list)
    error: str = ""  # motivo legível quando a fonte falhou
    more: int = 0  # itens omitidos pelo limite da seção ("+N")
    group_more: dict = field(default_factory=dict)  # grupo -> omitidos ("+N" por grupo)
    collapsed: bool = False  # regra de volume: a seção vira uma linha-resumo
    total: int = 0  # itens da seção antes de colapsar (só vale com ``collapsed``)
    reason: str = ""  # motivo de máquina da falha ("oauth", "http_error"…); "" = desconhecido
    in_banner: bool = False  # a falha já está no selo do topo: a seção não repete o motivo

    def count(self) -> int:
        """Todos os itens da seção, visíveis ou não."""
        if self.collapsed:
            return self.total
        return len(self.items) + self.more + sum(self.group_more.values())


@dataclass(frozen=True)
class Briefing:
    text: str  # = text_model: texto de terceiros delimitado (memória da sessão/LLM)
    sections: list[Section]
    items: list[BriefItem]
    text_user: str = ""  # HTML do Telegram, sem marcadores; "" = derivar de ``text``

    @property
    def text_model(self) -> str:
        return self.text


_TITLES = {
    "calendar": "Agenda", "tasks": "Tarefas", "email": "E-mail", "whatsapp": "WhatsApp",
    "names": 'Conversas sem nome (responda "nomeia N <nome>" ou "ignora N")',
}


class Row(NamedTuple):
    """Uma linha coletada: ``text`` marcado (modelo) e ``user`` limpo (HTML do Telegram)."""

    text: str
    ref: dict
    user: str = ""
    group: str = ""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _bold(text: str) -> str:
    return f"<b>{_esc(text)}</b>"


def _clean(text: str | None, max_chars: int = _FIELD_MAX) -> str:
    """Texto de terceiros para o usuário, escapado (nunca vira formatação)."""
    return _esc(plain_external(text, max_chars))


def _user_from_model(text: str, bold_head: bool = False) -> str:
    """Linha do usuário derivada da marcada (fontes que só entregam ``text``)."""
    flat = " ".join(strip_markers(text).split())
    if bold_head and " — " in flat:
        head, _, rest = flat.partition(" — ")
        return f"{_bold(head)} · {_esc(rest)}"
    return _esc(flat)


def _as_row(raw: tuple, key: str) -> Row:
    if isinstance(raw, Row):
        return raw
    group = raw[2] if len(raw) > 2 else ""
    return Row(raw[0], raw[1], _user_from_model(raw[0], bold_head=key == "names"), group)


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
    def __init__(self, message: str = "", reason: str = ""):
        super().__init__(message)
        self.reason = reason


def _call(op: str, payload: dict[str, Any], *, action: str, env: str, timeout: int) -> dict:
    raw = get_integration().post(op, payload, timeout=timeout, wait_result=True)
    out = parse_windmill_result(raw, action=action, resource_env=env)
    if not out.ok and out.reason in ("oauth", "upstream_error", "http_error"):
        # One retry: the OAuth token may be refreshed by Windmill seconds later.
        time.sleep(float(os.getenv("EVI_BRIEFING_RETRY_SEC", "10")))
        raw = get_integration().post(op, payload, timeout=timeout, wait_result=True)
        out = parse_windmill_result(raw, action=action, resource_env=env)
    if not out.ok:
        raise _SourceError(_reason_text(out), out.reason or "")
    return out.data or {}


# ---------------------------------------------------------------- sources


def _parse_iso(value: str, tz: ZoneInfo) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)


def _collect_calendar(day: date) -> list[Row]:
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
        flag = " ⚠ conflito de horário" if i in conflicts else ""
        user = f"{_esc(when)} {_clean(ev.get('summary') or '(sem título)')}{flag}"
        rows.append(Row(f"{when} {name}{flag}", {"kind": "event", "id": ev.get("id") or ""}, user))
    return rows


def _collect_tasks(day: date, overdue: bool) -> list[Row]:
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
        user = _clean(t.get("title") or "(sem título)") + (f" · venceu {due_d.strftime('%d/%m')}" if tag else "")
        ref = {"kind": "task", "id": t.get("id") or ""}
        if due_d == day:  # due that day: the evening preview offers a reminder for it
            ref["rm_title"] = plain_external(t.get("title") or "(sem título)", _RM_TITLE_MAX)
        rows.append((Row(f"{title}{tag}", ref, user), due_d))
    rows.sort(key=lambda r: r[1])
    return [row for row, _ in rows]


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


def _sender_name(raw: str) -> str:
    name, addr = parseaddr(raw or "")
    return (name or addr or "").strip()


def _collect_email() -> list[Row]:
    payload = {"max_messages": _EMAIL_FETCH, "gmail": _resource("gmail")}
    blob = _call(
        "summarize_inbox", payload, action="acessar o Gmail",
        env="WINDMILL_GMAIL_RESOURCE", timeout=180,
    )
    rows = []
    for m in select_emails(list(blob.get("messages") or [])):
        subj = wrap_external(m.get("subject") or "(sem assunto)", "email", _FIELD_MAX)
        sender = wrap_external(m.get("from") or "", "email", _FIELD_MAX)
        who = _clean(_sender_name(str(m.get("from") or "")), 40)
        what = _clean(m.get("subject") or "(sem assunto)", 70)
        user = f"<b>{who}</b> · {what}" if who else what
        rows.append(Row(f"{subj} — {sender}", {"kind": "email", "id": m.get("id") or ""}, user))
    return rows


GROUP_DEBTS = "Esperando sua resposta"
GROUP_PROMISES = "Suas promessas"
GROUP_COMMITMENTS = "Combinados"
GROUP_LIMIT = 3


def _commitment_date(c: dict) -> date | None:
    when = c.get("event_date") or c.get("due_date") or ""
    if when:
        try:
            return date.fromisoformat(str(when)[:10])
        except ValueError:
            return None
    return None


def _debt_age(hours: float) -> str:
    if hours < 48:
        return f"há {max(1, int(hours))} h"
    return f"há {int(hours // 24)} d"


def _collect_whatsapp(today: date | None = None) -> list[Row]:
    from services.whatsapp_processor import reply_debts_enabled

    today = today or now_local().date()
    grouped = reply_debts_enabled()
    rows: list[Row] = []
    debts: list[Row] = []
    promises: list[Row] = []
    for c in db.list_pending_commitments(limit=50):
        text = wrap_external(c.get("title") or c.get("raw_text") or "", "whatsapp", _FIELD_MAX)
        who = c.get("source_label") or c.get("source_chat") or ""
        when_d = _commitment_date(c)
        line = text
        if who:
            line += f" — {wrap_external(who, 'whatsapp', 60)}"
        if when_d:
            line += f" ({when_d.strftime('%d/%m')})"
        ref = {"kind": "commitment", "id": c.get("id")}
        if when_d == today + timedelta(days=1) and c.get("type") != "event":  # events are already scheduled
            ref["rm_title"] = plain_external(c.get("title") or c.get("raw_text") or "", _RM_TITLE_MAX)
        is_promise = c.get("type") == "promise"
        who_user = _who_label(who)
        parts = []
        if who_user:
            parts.append(_bold(plain_external(who_user, 40)))
        parts.append(_clean(c.get("title") or c.get("raw_text") or "", 60))
        if when_d:
            parts.append(_short_due(when_d, today) if is_promise else _short_day(when_d, today))
        user = " · ".join(p for p in parts if p)
        if not grouped:
            rows.append(Row(line, ref, user))
        elif is_promise:
            promises.append(Row(line, ref, user, GROUP_PROMISES))
        else:
            rows.append(Row(line, ref, user, GROUP_COMMITMENTS))
    if not grouped:
        return rows
    from services.reply_debts import list_debts

    for d in list_debts():
        line = (
            f"{wrap_external(d.get('name') or d['jid'], 'whatsapp', 60)} — "
            f"{_debt_age(d['age_h'])}: {wrap_external(d.get('preview') or '', 'whatsapp', _FIELD_MAX)}"
        )
        who_user = _who_label(d.get("name") or d["jid"]) or "contato sem nome"
        preview = plain_external(d.get("preview") or "", 60)
        user = f"{_bold(plain_external(who_user, 40))} · {_short_age(d['age_h'])}"
        if preview:
            user += f' · "{_esc(preview)}"'
        debts.append(Row(line, {"kind": "reply_debt", "id": d["jid"]}, user, GROUP_DEBTS))
    return debts + promises + rows


def _collect_names(now: datetime) -> list[tuple[str, dict]]:
    from services.contact_names import prompt_rows

    return prompt_rows(now)


# ---------------------------------------------------------------- assembly


def _run_source(key: str, fn: Callable[[], list]) -> Section:
    title = _TITLES[key]
    try:
        rows = [_as_row(r, key) for r in fn()]
    except _SourceError as exc:
        return Section(key, title, error=str(exc), reason=getattr(exc, "reason", ""))
    except Exception as exc:  # isolada: nunca derruba as outras fontes
        soft_fail(f"briefing.{key}", exc)
        return Section(key, title, error=f"falha inesperada ({str(exc)[:100]})")
    if rows and rows[0].group:  # grupos rotulados: teto e "+N" por grupo
        items: list[BriefItem] = []
        group_more: dict = {}
        counts: dict = {}
        for row in rows:
            counts[row.group] = counts.get(row.group, 0) + 1
            if counts[row.group] <= GROUP_LIMIT:
                items.append(BriefItem(0, row.text, row.ref, row.group, row.user))
        for group, total in counts.items():
            if total > GROUP_LIMIT:
                group_more[group] = total - GROUP_LIMIT
        return Section(key, title, items=items, group_more=group_more)
    limit = _email_max() if key == "email" else LIMITS[key]
    items = [BriefItem(0, r.text, r.ref, "", r.user) for r in rows[:limit]]
    return Section(key, title, items=items, more=max(0, len(rows) - limit))


def _header_parts(day: date, kind: str) -> tuple[str, str]:
    stamp = f"{_WEEKDAYS[day.weekday()]}, {day.strftime('%d/%m')}"
    if kind == "evening":
        return "Boa noite!", f"Amanhã: {stamp}"
    return "Bom dia!", stamp


def _header(now: datetime, day: date, kind: str) -> str:
    greeting, rest = _header_parts(day, kind)
    return f"{greeting} {rest}"


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    cut = text[: MAX_CHARS - len(_TRUNC)]
    cut = cut[: cut.rfind("\n")] if "\n" in cut else cut
    return cut.rstrip() + "\n" + _TRUNC


# Rótulos do texto do usuário. ``_NOUNS``: (singular, plural, pedido que lista tudo) — o
# pedido é uma frase que o agente já entende (tools de listar), não um comando novo.
_PLAIN_TITLES = {"calendar": "Agenda", "tasks": "Tarefas", "email": "E-mail",
                 "whatsapp": "WhatsApp", "names": "Conversas sem nome"}
_USER_TITLES = {"calendar": "📅 Agenda", "tasks": "✅ Tarefas", "email": "✉️ E-mail",
                "whatsapp": "💬 WhatsApp", "names": "🏷 Conversas sem nome"}
_GROUP_TITLES = {GROUP_DEBTS: "💬 Esperando sua resposta", GROUP_PROMISES: "🤝 Suas promessas",
                 GROUP_COMMITMENTS: "📌 Combinados"}
_NOUNS = {
    "calendar": ("evento", "eventos", "minha agenda"),
    "tasks": ("tarefa", "tarefas", "minhas tarefas"),
    "email": ("e-mail", "e-mails", "resumo dos e-mails"),
    "whatsapp": ("pendência do WhatsApp", "pendências do WhatsApp", "pendências do WhatsApp"),
    "names": ("conversa sem nome", "conversas sem nome", "conversas sem nome"),
    GROUP_DEBTS: ("conversa", "conversas", "quem está esperando minha resposta"),
    GROUP_PROMISES: ("promessa", "promessas", "minhas promessas"),
    GROUP_COMMITMENTS: ("combinado", "combinados", "meus compromissos"),
}


def _more_text(n: int, key: str) -> str:
    sing, plur, ask = _NOUNS[key]
    return f'+{n} {sing if n == 1 else plur} — peça "{ask}"'


def _summary_text(sec: Section) -> str:
    """Linha-resumo de uma seção colapsada pela regra de volume."""
    sing, plur, ask = _NOUNS[sec.key]
    n = sec.count()
    return f'{n} {sing if n == 1 else plur} — peça "{ask}"'


def _item_user_line(it: BriefItem) -> str:
    return f"{it.n}. {it.user or _user_from_model(it.text)}"


def _user_section_lines(sec: Section) -> list[str]:
    """Linhas do usuário (HTML do Telegram) de uma seção; [] se vazia."""
    if sec.error and sec.in_banner:
        return [f"⚠ {_esc(_PLAIN_TITLES[sec.key])} indisponível ({_SEE_BANNER})"]
    if sec.error:
        return [f"⚠ {_esc(_PLAIN_TITLES[sec.key])} indisponível — {_esc(strip_markers(sec.error))}"]
    if sec.collapsed:
        emoji = _USER_TITLES[sec.key].split(" ", 1)[0]
        return [f"{emoji} {_esc(_summary_text(sec))}"]
    if not sec.items:
        return []
    grouped = any(it.group for it in sec.items)
    lines = [] if grouped else [_bold(_USER_TITLES[sec.key])]
    cur = None
    for i, it in enumerate(sec.items):
        if it.group and it.group != cur:
            if cur is not None:
                lines.append("")
            cur = it.group
            lines.append(_bold(_GROUP_TITLES.get(cur, cur)))
        lines.append(_item_user_line(it))
        nxt = sec.items[i + 1].group if i + 1 < len(sec.items) else None
        if it.group and nxt != it.group and sec.group_more.get(it.group):
            lines.append(_esc(_more_text(sec.group_more[it.group], it.group)))
    if sec.more:
        lines.append(_esc(_more_text(sec.more, sec.key)))
    return lines


def volume_lines(sections: list[Section]) -> int:
    """Linhas não vazias do texto do usuário (cabeçalho + seções + rodapé)."""
    body = sum(1 for s in sections for ln in _user_section_lines(s) if ln)
    has_items = any(s.items for s in sections)
    return 1 + body + (1 if has_items else 0)


def fit_volume(sections: list[Section], budget: int = MAX_LINES) -> list[Section]:
    """Regra de volume (SCN-UX-04): acima de ~``budget`` linhas, seções de menor prioridade
    viram uma linha-resumo com o pedido que as lista. Pura; mantém ordem e itens das demais."""
    out = list(sections)
    for key in COLLAPSE_ORDER:
        if volume_lines(out) <= budget:
            break
        for i, sec in enumerate(out):
            if sec.key == key and sec.items and not sec.error and not sec.collapsed:
                out[i] = replace(sec, items=[], more=0, group_more={}, collapsed=True, total=sec.count())
    return out


def _footer(items: list[BriefItem], kind: str = "morning") -> str:
    """Comandos de resposta válidos para os tipos de item mostrados (um número de exemplo cada)."""
    first: dict = {}
    for it in items:
        first.setdefault(it.ref.get("kind"), it.n)
    parts: list[str] = []
    if "commitment" in first:
        parts += [f"confirma {first['commitment']}", f"dispensa {first['commitment']}"]
    if "reply_debt" in first:
        parts.append(f"respondido {first['reply_debt']}")
    if "name_prompt" in first:
        parts += [f"nomeia {first['name_prompt']} Nome", f"ignora {first['name_prompt']}"]
    remind = remindable_titles(items, kind)
    if remind:
        parts.append(f"lembra {min(remind)}")
    return f"<i>Responda: {_esc(' · '.join(parts))}</i>" if parts else ""


def _render_model(header: str, sections: list[Section], free_day: str, banner: list[str] = (), tip: str = "") -> str:
    """Texto para a sessão/LLM: terceiros delimitados por ``wrap_external``."""
    lines = [header, *banner]
    if free_day:
        lines.append(free_day)
    for sec in sections:
        if sec.error and sec.in_banner:
            lines.append(f"⚠ {sec.title} indisponível ({_SEE_BANNER})")
        elif sec.error:
            lines.append(f"⚠ {sec.title} indisponível — {sec.error}")
        elif sec.collapsed:
            lines.append(f"\n{sec.title}")
            lines.append(_summary_text(sec))
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
    if tip:
        lines += ["", tip]
    return _truncate("\n".join(lines))


def _render_user(day: date, kind: str, sections: list[Section], items: list[BriefItem],
                 free_day: str, banner: list[str] = (), tip: str = "") -> str:
    """Texto para o usuário: HTML do Telegram, sem marcadores, dinâmico escapado."""
    greeting, rest = _header_parts(day, kind)
    lines = [f"{_bold(greeting)} {_esc(rest)}", *(_esc(ln) for ln in banner)]
    if free_day:
        lines.append(_esc(free_day))
    prev_short = False  # avisos e resumos de uma linha ficam colados, sem linha em branco
    for sec in sections:
        sec_lines = _user_section_lines(sec)
        short = bool(sec.error or sec.collapsed)
        if sec_lines and not (short and prev_short) and not sec.error:
            lines.append("")
        if sec_lines:
            prev_short = short
        lines.extend(sec_lines)
    footer = _footer(items, kind)
    if footer:
        lines += ["", footer]
    if tip:
        lines += ["", _esc(tip)]
    return _truncate("\n".join(lines))


# ---------------------------------------------------------------- selo de fontes fora

_SEE_BANNER = "ver aviso acima"
_SOURCE_KEYS = {"calendar": "calendar", "tasks": "tasks", "email": "gmail", "whatsapp": "whatsapp"}
_GOOGLE = (("calendar", "agenda"), ("tasks", "tarefas"), ("gmail", "e-mail"))
_SOURCE_LABELS = {"calendar": "Agenda", "tasks": "Tarefas", "gmail": "E-mail", "telegram": "Telegram",
                  "whatsapp": "WhatsApp"}
_SHORT_REASONS = {
    "not_configured": "não configurado",
    "http_error": "erro de comunicação",
    "upstream_error": "sem resposta",
    "unparseable": "resposta ilegível",
}


def _record_sources(sections: list[Section]) -> None:
    """Grava o resultado de cada fonte em ``source_status`` (e o estado da sessão WhatsApp)."""
    wa_failed = False
    for sec in sections:
        key = _SOURCE_KEYS.get(sec.key)
        if not key:
            continue
        if key == "whatsapp":  # os dados guardados podem vir com a sessão fechada: vale o estado
            wa_failed = bool(sec.error)
            continue
        db.record_source(key, not sec.error, (sec.reason or "error") if sec.error else None)
    from services.health import whatsapp_connection_state

    state = whatsapp_connection_state() if os.getenv("EVOLUTION_API_KEY", "").strip() else None
    if state == "open":
        db.record_source("whatsapp", True)
    elif state is not None:
        db.record_source("whatsapp", False, "disconnected")
    elif wa_failed:
        db.record_source("whatsapp", False, "error")


def _since(row: dict) -> str:
    ts = row.get("down_since")
    if not isinstance(ts, datetime):
        return ""
    return f" desde {ts.astimezone(_tz()).strftime('%d/%m')}"


def _banner_lines(down: list[dict]) -> list[str]:
    """Uma linha por fonte fora (Google agrupado); só texto nosso, sem conteúdo de terceiros."""
    google = [r for r in down if r["source"] in dict(_GOOGLE) and r.get("reason") == "oauth"]
    lines: list[str] = []
    google_done = False
    for r in down:
        if r in google:
            if google_done:
                continue
            google_done = True
            names = ", ".join(n for k, n in _GOOGLE if any(g["source"] == k for g in google))
            lines.append(f"⚠️ Google ({names}): acesso expirado{_since(google[0])} — "
                         "reconecte no Windmill (Resources)")
        elif r["source"] == "whatsapp":
            lines.append(f"📵 WhatsApp desconectado{_since(r)} — o EVI não está lendo suas conversas; "
                         "gere o QR no manager da Evolution")
        else:
            label = _SOURCE_LABELS.get(r["source"], r["source"])
            why = _SHORT_REASONS.get(r.get("reason") or "", "indisponível")
            lines.append(f"⚠️ {label} fora{_since(r)} — {why}")
    return lines


def _source_health(sections: list[Section]) -> tuple[list[str], list[Section]]:
    """Registra as fontes e devolve (linhas do selo, seções marcadas como cobertas pelo selo).
    Nunca propaga: sem DB/Evolution o briefing sai sem selo."""
    from services.health import source_alerts_enabled

    if not source_alerts_enabled():
        return [], sections
    try:
        _record_sources(sections)
        down = db.list_sources_down()
    except Exception as exc:
        soft_fail("briefing.source_health", exc)
        return [], sections
    banner = _banner_lines(down)
    down_keys = {r["source"] for r in down}
    covered = [replace(s, in_banner=True) if s.error and _SOURCE_KEYS.get(s.key) in down_keys else s
               for s in sections]
    return banner, covered


def assemble_briefing(kind: str = "morning", now: datetime | None = None) -> Briefing:
    """Monta o briefing sem LLM. ``kind="evening"`` é a prévia de amanhã."""
    now = now or now_local()
    evening = kind == "evening"
    day = now.date() + timedelta(days=1) if evening else now.date()
    sources: list[tuple[str, Callable[[], list]]] = [
        ("calendar", lambda: _collect_calendar(day)),
        ("tasks", lambda: _collect_tasks(day, overdue=not evening)),
        ("email", _collect_email),
        ("whatsapp", lambda: _collect_whatsapp(now.date())),
    ]
    if kind == "morning" and now.weekday() == 0:  # weekly "Conversas sem nome" (SCN-NAME-05)
        sources.append(("names", lambda: _collect_names(now)))
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures = [pool.submit(_run_source, key, fn) for key, fn in sources]
        raw_sections = [f.result() for f in futures]

    banner, raw_sections = _source_health(raw_sections)
    is_free = not any(s.items for s in raw_sections) and not any(s.error for s in raw_sections)
    free_day = (_EVENING_FREE if evening else _FREE_DAY) if is_free else ""
    fitted = fit_volume(raw_sections, MAX_LINES - len(banner))  # o selo conta primeiro e não colapsa  # antes de numerar: só o que aparece recebe número
    n = 0
    sections: list[Section] = []
    for sec in fitted:
        numbered = []
        for it in sec.items:
            n += 1
            numbered.append(replace(it, n=n))
        sections.append(replace(sec, items=numbered))
    items = [it for sec in sections for it in sec.items]

    tip = ""
    if kind == "morning" and volume_lines(sections) + len(banner) < MAX_LINES:
        # the tip is the first line to go: it only fits when the budget has a spare line
        from services.discovery_tips import tip_for

        tip = tip_for(now.date(), now) or ""
    text_model = _render_model(_header(now, day, kind), sections, free_day, banner, tip)
    text_user = _render_user(day, kind, sections, items, free_day, banner, tip)
    return Briefing(text_model, sections, items, text_user)


REPLY_WINDOW = timedelta(hours=3)
_KINDS = ("morning", "evening")


def _telegram_session_id(chat_id: str) -> str:
    # Mesmo formato de services/telegram_handler.py (`f"telegram-{chat_id}"`).
    return f"telegram-{chat_id}"


NO_BRIEFING_TODAY = "não há briefing de hoje para resolver os números"


def today_snapshot(session_id: str | None, kind: str | None = None) -> dict | None:
    """Payload of the latest ``morning_briefing`` snapshot of the session when it is
    from today (local day), else None. The latest snapshot decides, so an old one never
    answers for a newer briefing that failed to store. With ``kind`` only snapshots of
    that briefing kind (morning/evening) are considered."""
    if not session_id:
        return None
    try:
        today = now_local().date()
        tz = now_local().tzinfo
        for row in db.load_tool_snapshots(session_id, limit=50):
            if row.get("tool_name") != "morning_briefing":
                continue
            payload = row.get("payload") or {}
            if kind is not None and payload.get("kind") != kind:
                continue
            payload_day = str(payload.get("day") or "")
            if payload_day:  # the briefing's own local day (created_at is the DB clock)
                same_day = payload_day == today.isoformat()
            else:
                created = datetime.fromisoformat(str(row.get("created_at")))
                if created.tzinfo is not None and tz is not None:
                    created = created.astimezone(tz)
                same_day = created.date() == today
            return payload if same_day else None
    except Exception as exc:
        soft_fail("briefing.resolve_items", exc)
    return None


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
    payload = today_snapshot(session_id)
    refs: dict | None = None if payload is None else (payload.get("refs") or {})
    if refs is None:
        return [], [NO_BRIEFING_TODAY] if nums else []
    label = {"commitment": "um compromisso", "reply_debt": "uma conversa esperando resposta", "name_prompt": "uma conversa sem nome"}.get(kind, f"do tipo {kind}")
    ids: list = []
    errors: list[str] = []
    for n in nums:
        ref = refs.get(str(n))
        if ref is None:
            last = max((int(k) for k in refs if str(k).isdigit()), default=0)
            span = f" (o briefing vai de 1 a {last})" if last else ""
            errors.append(f"item {n} não existe no briefing{span}")
            continue
        ref_kind, _, ref_id = str(ref).partition(":")
        if kind in ("reply_debt", "name_prompt"):
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


# --- botões inline (evi-briefing-buttons) -----------------------------------------

BUTTON_KINDS = ("reply_debt", "commitment", "name_prompt")
MAX_BUTTON_ROWS = 10
KIND_CODES = {"morning": "m", "evening": "e"}
CODE_KINDS = {v: k for k, v in KIND_CODES.items()}
CALLBACK_RE = re.compile(r"^b1:(\d{8}):([me]):(\d{1,3}):(ok|no|up|dn|rm)$")


def buttons_enabled() -> bool:
    return os.getenv("EVI_BRIEFING_BUTTONS", "true").strip().lower() != "false"


def callback_data(day: str, kind: str, n: int, action: str) -> str:
    """``b1:<yyyymmdd>:<m|e>:<n>:<a>`` — only the day, the briefing kind, the item number
    and the action."""
    return f"b1:{day.replace('-', '')}:{KIND_CODES[kind]}:{n}:{action}"


def parse_callback_data(data: object) -> tuple[str, str, int, str] | None:
    """``(yyyymmdd, kind, n, action)`` or None for anything that is not exactly our format."""
    m = CALLBACK_RE.match(data) if isinstance(data, str) else None
    return (m.group(1), CODE_KINDS[m.group(2)], int(m.group(3)), m.group(4)) if m else None


def actionable_kinds(items: list[BriefItem]) -> dict[int, str]:
    """Item number -> ref kind for the items that get buttons (first ``MAX_BUTTON_ROWS``)."""
    out = {it.n: it.ref.get("kind") for it in items if it.ref.get("kind") in BUTTON_KINDS}
    return dict(sorted(out.items())[:MAX_BUTTON_ROWS])


def actionable_from_refs(refs: dict) -> dict[int, str]:
    """Same as ``actionable_kinds`` but from the snapshot's ``{"n": "kind:id"}`` refs."""
    out = {
        int(n): str(ref).partition(":")[0]
        for n, ref in (refs or {}).items()
        if str(n).isdigit() and str(ref).partition(":")[0] in BUTTON_KINDS
    }
    return dict(sorted(out.items())[:MAX_BUTTON_ROWS])


def remindable_titles(items: list[BriefItem], kind: str) -> dict[int, str]:
    """Evening preview only: item number -> title for the items due tomorrow (the ones that
    offer "🔔 lembrar amanhã 9h"). Titles are plain text, at most ``_RM_TITLE_MAX`` chars."""
    if kind != "evening":
        return {}
    out = {it.n: str(it.ref["rm_title"]) for it in items if it.ref.get("rm_title")}
    return dict(sorted(out.items())[:MAX_BUTTON_ROWS])


def build_keyboard(
    day: str, kind: str, actionable: dict[int, str], done: object = (), feedback: str | None = None,
    remind: object = (), reminded: object = (),
) -> dict:
    """Inline keyboard: one row per item with something left to do (✅/✖ for actionable
    kinds, 🔔 for ``remind`` items not yet in ``reminded``), then 👍/👎 (the chosen one
    marked ✓ — it stays tappable, the last tap wins)."""
    handled = {int(n) for n in done}
    set_reminders = {int(n) for n in remind} - {int(n) for n in reminded}
    rows: list[list[dict]] = []
    for n in sorted(set(actionable) | set_reminders):
        item_kind = actionable.get(n)
        row: list[dict] = []
        if item_kind and n not in handled:
            if item_kind == "name_prompt":
                row.append({"text": f"{n} ✖ ignorar", "callback_data": callback_data(day, kind, n, "no")})
            else:
                row.append({"text": f"{n} ✅", "callback_data": callback_data(day, kind, n, "ok")})
                row.append({"text": f"{n} ✖", "callback_data": callback_data(day, kind, n, "no")})
        if n in set_reminders:
            row.append({"text": f"{n} 🔔", "callback_data": callback_data(day, kind, n, "rm")})
        if row:
            rows.append(row)
    rows.append([
        {"text": "👍 ✓" if feedback == "up" else "👍", "callback_data": callback_data(day, kind, 0, "up")},
        {"text": "👎 ✓" if feedback == "down" else "👎", "callback_data": callback_data(day, kind, 0, "dn")},
    ])
    return {"inline_keyboard": rows}


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
    sections = {
        s.key: {"count": s.total if s.collapsed else len(s.items), "error": s.error}
        for s in brief.sections
    }
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    # O usuário recebe o texto limpo (HTML); a memória/LLM guarda a versão marcada.
    actionable = actionable_kinds(brief.items)
    remind = remindable_titles(brief.items, kind)
    markup = (
        {"reply_markup": build_keyboard(day.isoformat(), kind, actionable, remind=remind)}
        if buttons_enabled() else {}
    )
    if brief.text_user:
        result = send_telegram_message(brief.text_user, chat_id or None, parse_mode="HTML", **markup)
    else:
        result = send_telegram_message(strip_markers(brief.text), chat_id or None, **markup)

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

        get_session_memory(session_id).add(AIMessage(content=brief.text_model))
    except Exception as exc:
        soft_fail("briefing.deliver.memory", exc)
    if os.getenv("DATABASE_URL"):
        # main._hydrate_memory recarrega a memória do Postgres a cada turno: sem isto
        # a primeira resposta apagaria o briefing do contexto.
        try:
            db.save_message(session_id, "assistant", brief.text_model)
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
                "message_id": getattr(result, "message_id", None),
                # item -> title (delimited: the snapshot is shown to the model) for "🔔 / lembra N"
                **({"rm": {str(n): wrap_external(t, "briefing", _RM_TITLE_MAX) for n, t in remind.items()}}
                   if remind else {}),
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
