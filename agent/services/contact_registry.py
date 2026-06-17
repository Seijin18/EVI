"""Postgres-backed WhatsApp contact registry with display names and aliases."""

from __future__ import annotations

import re
from typing import Any

from services.contact_filesystem import phone_to_jid, update_contact_label


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_aliases(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if str(a).strip()]
    return []


def effective_label(row: dict[str, Any] | None, fallback: str = "") -> str:
    if not row:
        return fallback
    display = (row.get("display_name") or "").strip()
    if display:
        return display
    whatsapp = (row.get("whatsapp_label") or "").strip()
    if whatsapp:
        return whatsapp
    return fallback


def searchable_names(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("display_name", "whatsapp_label"):
        val = (row.get(key) or "").strip()
        if val and val not in names:
            names.append(val)
    for alias in _normalize_aliases(row.get("aliases")):
        if alias not in names:
            names.append(alias)
    jid = row.get("jid") or ""
    if jid and jid not in names:
        names.append(jid)
    return names


def touch_contact(jid: str, *, whatsapp_label: str = "", phone: str = "") -> None:
    """Ensure contact exists in DB; set whatsapp_label only when still unknown."""
    if not jid:
        return
    from db import get_whatsapp_contact, init_db, upsert_whatsapp_contact

    init_db()
    existing = get_whatsapp_contact(jid)
    wl = (whatsapp_label or "").strip()
    ph = (phone or "").strip()

    if existing:
        if existing.get("whatsapp_label"):
            wl = ""
        elif wl and (existing.get("display_name") or "").strip().casefold() == wl.casefold():
            wl = ""
        if not wl and not ph:
            return

    upsert_whatsapp_contact(
        jid,
        whatsapp_label=wl or None,
        phone=ph or None,
    )


def sync_evolution_contacts(*, limit: int | None = None) -> int:
    """Upsert Evolution address book into Postgres (whatsapp_label only)."""
    from db import init_db, upsert_whatsapp_contact
    from services.evolution_discovery import fetch_evolution_contacts

    init_db()
    count = 0
    for c in fetch_evolution_contacts(limit=limit):
        jid = c.get("jid") or ""
        if not jid:
            continue
        label = (c.get("label") or "").strip()
        digits = _digits_only(jid.split("@", 1)[0])
        upsert_whatsapp_contact(
            jid,
            whatsapp_label=label or None,
            phone=digits or None,
        )
        count += 1
    return count


def assign_contact_name(
    jid: str,
    *,
    display_name: str,
    aliases: list[str] | None = None,
    whatsapp_label: str = "",
) -> dict[str, Any]:
    """Set preferred display name and optional aliases for a JID."""
    from db import get_whatsapp_contact, init_db, upsert_whatsapp_contact

    init_db()
    display_name = (display_name or "").strip()
    if not display_name:
        raise ValueError("display_name is required")

    clean_aliases = [a.strip() for a in (aliases or []) if (a or "").strip()]
    wa_label = (whatsapp_label or "").strip()
    upsert_whatsapp_contact(
        jid,
        display_name=display_name,
        aliases=clean_aliases or None,
        whatsapp_label=wa_label or None,
    )
    try:
        update_contact_label(jid, display_name)
    except Exception:
        pass
    if wa_label:
        upsert_whatsapp_contact(jid, whatsapp_label=wa_label)
    return get_whatsapp_contact(jid) or {"jid": jid, "display_name": display_name}


def db_contacts_map() -> dict[str, dict[str, Any]]:
    from db import init_db, list_whatsapp_contacts_db

    init_db()
    return {row["jid"]: row for row in list_whatsapp_contacts_db()}


def merge_db_fields(contact: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return contact
    out = dict(contact)
    out["display_name"] = (row.get("display_name") or "").strip()
    out["whatsapp_label"] = (row.get("whatsapp_label") or "").strip()
    out["aliases"] = _normalize_aliases(row.get("aliases"))
    out["phone"] = (row.get("phone") or "").strip()
    label = effective_label(row, contact.get("label") or contact.get("jid") or "")
    out["label"] = label
    out["in_db"] = True
    return out


def _name_score(label: str, query: str) -> int:
    from services.evolution_discovery import name_query_matches

    if not label or not query:
        return 0
    if label.casefold() == query.casefold():
        return 100
    if name_query_matches(label, query):
        return 85
    return 0


def search_db_contacts(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Search Postgres contacts by display name, alias, whatsapp label or phone."""
    q = (query or "").strip()
    if not q:
        return []
    digits = _digits_only(q)
    jid_guess = phone_to_jid(q) if digits else ""

    scored: list[tuple[int, dict[str, Any]]] = []
    for row in db_contacts_map().values():
        jid = row.get("jid") or ""
        best = 0
        for name in searchable_names(row):
            best = max(best, _name_score(name, q))
        if jid_guess and jid == jid_guess:
            best = max(best, 90)
        elif digits:
            jid_digits = _digits_only(jid.split("@", 1)[0])
            phone_digits = _digits_only(row.get("phone") or "")
            if digits in jid_digits or digits in phone_digits:
                best = max(best, 70)
        if best:
            contact = merge_db_fields({"jid": jid}, row)
            scored.append((best, contact))

    scored.sort(key=lambda x: (-x[0], (x[1].get("label") or "").casefold()))
    return [c for _, c in scored[:limit]]


def format_contact_names(row: dict[str, Any] | None, fallback: str = "") -> str:
    if not row:
        return fallback
    display = (row.get("display_name") or "").strip()
    whatsapp = (row.get("whatsapp_label") or "").strip()
    if display and whatsapp and display.casefold() != whatsapp.casefold():
        return f"{display} (WhatsApp: {whatsapp})"
    return effective_label(row, fallback)
