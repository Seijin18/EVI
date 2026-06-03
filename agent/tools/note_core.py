import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

def notes_dir() -> Path:
    return Path(os.getenv("EVI_NOTES_DIR", "/watched_folders/inbox_ia"))


def ensure_notes_dir() -> Path:
    dest = notes_dir()
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def slug(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title.lower())
    return safe[:48] or "note"


def write_manual_note(
    title: str, content: str, tags: Optional[List[str]] = None, category: str = "general"
) -> str:
    tags = tags or []
    dest = ensure_notes_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = dest / f"{ts}_{slug(title)}.md"
    tag_line = ", ".join(tags)
    path.write_text(
        f"""---
title: "{title}"
date: {datetime.now().isoformat()}
tags: [{tag_line}]
category: {category}
---

# {title}

{content}
""",
        encoding="utf-8",
    )
    return str(path)


def write_auto_insight(messages: List[dict], session_id: str = "default") -> str:
    dest = ensure_notes_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = dest / f"{ts}_auto_insight_{session_id}.md"
    bullets = []
    for m in messages[-6:]:
        role = m.get("role", "user")
        text = (m.get("content") or "")[:200]
        if text.strip():
            bullets.append(f"- **{role}**: {text}")
    if not bullets:
        bullets.append("- (empty session)")
    path.write_text(
        f"""---
title: "Auto insight"
date: {datetime.now().isoformat()}
tags: [auto-insight]
category: productivity
session_id: {session_id}
---

# Session insight

## Key points
{chr(10).join(bullets)}
""",
        encoding="utf-8",
    )
    return str(path)
