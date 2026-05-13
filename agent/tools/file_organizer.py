# /home/marshibs/Projects/EVI/agent/tools/file_organizer.py
from langchain_core.tools import tool
from pathlib import Path
import shutil
import hashlib

SORT_RULES = {
    "university": {
        "extensions": [".pdf", ".pptx", ".docx"],
        "keywords": ["lecture", "notes", "assignment", "exam", "lab"],
        "dest": "/watched_folders/university",
    },
    "code": {
        "extensions": [".py", ".js", ".ts", ".c", ".cpp", ".ipynb"],
        "keywords": ["project", "homework", "solution"],
        "dest": "/watched_folders/code",
    },
    "pdfs_general": {
        "extensions": [".pdf"],
        "keywords": [],
        "dest": "/watched_folders/pdfs",
    },
}


def _classify_file(file: Path) -> str:
    name_lower = file.name.lower()
    ext = file.suffix.lower()

    for category, rules in SORT_RULES.items():
        ext_match = ext in rules["extensions"]
        keyword_match = any(kw in name_lower for kw in rules["keywords"])
        if ext_match and (keyword_match or not rules["keywords"]):
            return rules["dest"]

    return "/watched_folders/unsorted"


@tool
def organize_inbox(confirm: bool = False) -> str:
    """
    Scans /watched_folders/inbox and sorts files into categorized folders.
    Set confirm=True to actually move files (dry-run by default).
    """
    inbox = Path("/watched_folders/inbox")
    results = []

    if not inbox.exists():
        return "Inbox is missing."

    for file in inbox.iterdir():
        if file.is_dir():
            continue

        dest_folder = _classify_file(file)
        action = f"{'MOVE' if confirm else 'PLAN'}: {file.name} → {dest_folder}"
        results.append(action)

        if confirm:
            dest = Path(dest_folder)
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / file.name

            if target.exists():
                h = hashlib.md5(file.read_bytes()).hexdigest()[:6]
                target = dest / f"{file.stem}_{h}{file.suffix}"

            shutil.move(str(file), str(target))

    return "\n".join(results) if results else "Inbox is empty."
