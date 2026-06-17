import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.contact_filesystem import (  # noqa: E402
    collect_known_contacts,
    ingest_commitment,
    phone_to_jid,
    search_contacts,
)
from tools.contact_tool import (  # noqa: E402
    get_whatsapp_contact_info,
    list_whatsapp_contacts,
)


def test_phone_to_jid():
    assert phone_to_jid("+55 16 99265-7231") == "5516992657231@s.whatsapp.net"


def test_search_by_name_and_phone():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5516992657231@s.whatsapp.net"
        ingest_commitment(
            jid=jid,
            source_id="w1",
            title="Reunião",
            raw_text="amanhã",
            commitment_id=1,
            label="Leozao",
        )
        by_name = search_contacts("Leozao")
        assert len(by_name) == 1
        assert by_name[0]["label"] == "Leozao"
        by_phone = search_contacts("99265-7231")
        assert len(by_phone) == 1
        assert by_phone[0]["jid"] == jid


def test_list_and_get_tools():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5516992657231@s.whatsapp.net"
        ingest_commitment(
            jid=jid,
            source_id="w2",
            title="Call",
            raw_text="teste",
            commitment_id=2,
            label="Leozao",
        )
        listed = list_whatsapp_contacts.invoke({"limit": 10})
        assert "Leozao" in listed
        assert "@s.whatsapp.net" not in listed
        detail = get_whatsapp_contact_info.invoke({"name_or_phone": "Leozao"})
        assert "Leozao" in detail
        assert "Call" in detail or "Reunião" in detail or "Atividade" in detail


def test_collect_merges_postgres():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        fake_rows = [
            {
                "source_chat": "5511888777666@s.whatsapp.net",
                "source_label": "Maria",
                "commitment_count": 3,
            }
        ]
        with patch("db.init_db"), patch(
            "db.list_whatsapp_contact_sources", return_value=fake_rows
        ):
            contacts = collect_known_contacts()
        labels = {c["label"] for c in contacts}
        assert "Maria" in labels


def test_learn_contact_with_mock_llm():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5516992657231@s.whatsapp.net"
        ingest_commitment(
            jid=jid,
            source_id="w3",
            title="Projeto X",
            raw_text="deadline sexta",
            commitment_id=3,
            label="Leozao",
        )
        with patch("llm.build_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "Leozao trabalha no projeto X."
            from services.contact_learning import learn_contact  # noqa: E402

            out = learn_contact("Leozao", days=30)
        assert "Leozao" in out
        assert "Perfil atualizado" in out
        profile = (Path(tmp) / "contacts" / jid / "profile.md").read_text(encoding="utf-8")
        assert "Síntese" in profile
        assert "projeto X" in profile.lower()


if __name__ == "__main__":
    test_phone_to_jid()
    test_search_by_name_and_phone()
    test_list_and_get_tools()
    test_collect_merges_postgres()
    test_learn_contact_with_mock_llm()
    print("ok")
