from typing import List, Optional

from langchain_core.tools import tool

from tools.note_core import write_auto_insight, write_manual_note


@tool
def save_note_manual(
    title: str, content: str, tags: Optional[List[str]] = None, category: str = "general"
) -> str:
    """
    Save a manual study or productivity note as Markdown with YAML frontmatter.
    Files are stored under watched_folders/inbox_ia/.
    """
    return write_manual_note(title, content, tags, category)


def build_auto_insight(messages: List[dict], session_id: str = "default") -> str:
    return write_auto_insight(messages, session_id)
