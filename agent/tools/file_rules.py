from pathlib import Path

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


def classify_file(file: Path) -> str:
    name_lower = file.name.lower()
    ext = file.suffix.lower()
    for _category, rules in SORT_RULES.items():
        ext_match = ext in rules["extensions"]
        keyword_match = any(kw in name_lower for kw in rules["keywords"])
        if ext_match and (keyword_match or not rules["keywords"]):
            return rules["dest"]
    return "/watched_folders/unsorted"
