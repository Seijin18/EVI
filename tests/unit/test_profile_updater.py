"""Unit tests for services/profile_updater.py."""

import sys
import tempfile
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.profile_updater import extract_profile_facts, merge_profile  # noqa: E402


def test_extract_name():
    facts = extract_profile_facts("Meu nome é Carlos Silva")
    assert facts.get("name") == "Carlos Silva"


def test_extract_company():
    facts = extract_profile_facts("Trabalho na Empresa Acme e preciso de ajuda.")
    assert "company" in facts
    assert "Acme" in facts["company"] or "Empresa Acme" in facts["company"]


def test_extract_role():
    facts = extract_profile_facts("Sou engenheiro de software na área de dados")
    assert "role" in facts
    assert "engenheiro" in facts["role"].lower()


def test_extract_empty():
    assert extract_profile_facts("Bom dia, como você está?") == {}


def test_merge_profile_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        import os
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        result = merge_profile("5511@c.us", {"name": "Ana"})
        assert result is True
        path = Path(tmp) / "5511@c.us" / "profile.md"
        assert path.is_file()
        content = path.read_text()
        assert "Ana" in content
        del os.environ["EVI_CONTACT_MEMORY_DIR"]


def test_merge_profile_updates_existing():
    with tempfile.TemporaryDirectory() as tmp:
        import os
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        merge_profile("jid1", {"name": "João"})
        merge_profile("jid1", {"name": "João Silva", "company": "ACME"})
        path = Path(tmp) / "jid1" / "profile.md"
        content = path.read_text()
        assert "João Silva" in content
        assert "ACME" in content
        del os.environ["EVI_CONTACT_MEMORY_DIR"]


def test_merge_profile_no_dir():
    import os
    os.environ.pop("EVI_CONTACT_MEMORY_DIR", None)
    result = merge_profile("jid2", {"name": "Test"})
    assert result is False


def test_merge_profile_no_new_facts():
    with tempfile.TemporaryDirectory() as tmp:
        import os
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        merge_profile("jid3", {"name": "Maria"})
        result = merge_profile("jid3", {"name": "Maria"})
        assert result is False
        del os.environ["EVI_CONTACT_MEMORY_DIR"]


if __name__ == "__main__":
    test_extract_name()
    test_extract_company()
    test_extract_role()
    test_extract_empty()
    test_merge_profile_creates_file()
    test_merge_profile_updates_existing()
    test_merge_profile_no_dir()
    test_merge_profile_no_new_facts()
    print("ok")
