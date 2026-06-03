from pathlib import Path

import importlib.util
from pathlib import Path as _P

_spec = importlib.util.spec_from_file_location(
    "file_rules",
    _P(__file__).resolve().parents[2] / "agent" / "tools" / "file_rules.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_classify_file = _mod.classify_file


def test_classify_university_pdf():
    assert _classify_file(Path("lecture_notes.pdf")) == "/watched_folders/university"


def test_classify_code():
    assert _classify_file(Path("homework.py")) == "/watched_folders/code"


def test_classify_unsorted():
    assert _classify_file(Path("random.xyz")) == "/watched_folders/unsorted"


if __name__ == "__main__":
    test_classify_university_pdf()
    test_classify_code()
    test_classify_unsorted()
    print("All file_organizer unit tests passed")
