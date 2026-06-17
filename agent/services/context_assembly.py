"""Assemble project context before LangGraph invoke (OpenClaw phase 3)."""

from __future__ import annotations

from services.session_context import extract_jid_from_session, format_tool_snapshots
from services.skill_loader import build_skills_block
from services.workspace import bootstrap_names, read_bootstrap_file, read_daily_memory


def _contact_profile_block(jid: str | None) -> str:
    if not jid:
        return ""
    try:
        from services.contact_filesystem import contact_dir, memory_enabled

        if not memory_enabled():
            return ""
        profile = contact_dir(jid) / "profile.md"
        if not profile.is_file():
            return ""
        text = profile.read_text(encoding="utf-8").strip()
        if not text:
            return ""
        return f"CONTACT PROFILE ({jid}):\n{text[:2000]}"
    except Exception:
        return ""


def build_context(
    session_id: str,
    user_message: str,
    *,
    jid: str | None = None,
) -> str:
    """Return text block injected into the agent system prompt."""
    jid = jid or extract_jid_from_session(session_id)
    blocks: list[str] = []

    bootstrap_parts: list[str] = []
    for name in bootstrap_names():
        if name == "HEARTBEAT.md":
            continue
        content = read_bootstrap_file(name)
        if content:
            bootstrap_parts.append(f"### {name}\n{content}")
    if bootstrap_parts:
        blocks.append("PROJECT CONTEXT:\n" + "\n\n".join(bootstrap_parts))

    snapshots = format_tool_snapshots(session_id)
    if snapshots:
        blocks.append(snapshots)

    daily = read_daily_memory(days_back=1)
    if daily:
        blocks.append(f"RECENT MEMORY LOGS:\n{daily}")

    profile = _contact_profile_block(jid)
    if profile:
        blocks.append(profile)

    skills = build_skills_block(user_message)
    if skills:
        blocks.append(skills)

    return "\n\n".join(blocks)
