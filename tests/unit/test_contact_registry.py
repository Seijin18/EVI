import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.contact_registry import (  # noqa: E402
    assign_contact_name,
    format_contact_names,
    search_db_contacts,
)
from services.contact_filesystem import search_contacts  # noqa: E402


def test_assign_and_search_by_display_name():
    jid = "5511959875299@s.whatsapp.net"
    store: dict = {}

    def fake_upsert(j, **kwargs):
        row = store.get(j, {"jid": j, "aliases": []})
        for key, val in kwargs.items():
            if val is None:
                continue
            if key == "aliases" and val:
                seen = {a.casefold() for a in row.get("aliases", [])}
                for alias in val:
                    if alias.casefold() not in seen:
                        row.setdefault("aliases", []).append(alias)
                        seen.add(alias.casefold())
            else:
                row[key] = val
        store[j] = row

    def fake_get(j):
        return store.get(j)

    def fake_list(limit=500):
        return list(store.values())

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        with patch("db.init_db"), patch("db.upsert_whatsapp_contact", side_effect=fake_upsert), patch(
            "db.get_whatsapp_contact", side_effect=fake_get
        ), patch("db.list_whatsapp_contacts_db", side_effect=fake_list):
            assign_contact_name(
                jid,
                display_name="Pedro Unna",
                aliases=["Pedro"],
                whatsapp_label="PNFagundes",
            )
            hits = search_db_contacts("Pedro Unna")
            assert len(hits) == 1
            assert hits[0]["jid"] == jid
            assert hits[0]["label"] == "Pedro Unna"

            by_alias = search_db_contacts("pedro")
            assert len(by_alias) == 1

            by_whatsapp = search_db_contacts("PNFagundes")
            assert len(by_whatsapp) == 1


def test_format_contact_names():
    row = {
        "display_name": "Pedro Unna",
        "whatsapp_label": "PNFagundes",
    }
    assert "Pedro Unna" in format_contact_names(row)
    assert "PNFagundes" in format_contact_names(row)


def test_set_whatsapp_contact_name_tool():
    from tools.contact_tool import set_whatsapp_contact_name  # noqa: E402

    jid = "5511959875299@s.whatsapp.net"
    store: dict = {}

    def fake_upsert(j, **kwargs):
        row = store.get(j, {"jid": j, "aliases": []})
        for key, val in kwargs.items():
            if val is None:
                continue
            if key == "aliases" and val:
                row.setdefault("aliases", []).extend(val)
            else:
                row[key] = val
        store[j] = row

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        from services.contact_filesystem import ingest_commitment  # noqa: E402

        ingest_commitment(
            jid=jid,
            source_id="w-alias",
            title="Vôlei",
            raw_text="test",
            commitment_id=1,
            label="PNFagundes",
        )
        with patch("db.init_db"), patch("db.upsert_whatsapp_contact", side_effect=fake_upsert), patch(
            "db.get_whatsapp_contact", side_effect=lambda j: store.get(j)
        ), patch("db.list_whatsapp_contacts_db", side_effect=lambda limit=500: list(store.values())):
            out = set_whatsapp_contact_name.invoke(
                {
                    "name_or_phone": "PNFagundes",
                    "display_name": "Pedro Unna",
                    "also_known_as": "Pedro",
                }
            )
            assert "Pedro Unna" in out
            assert "salvo no banco" in out.lower() or "Contato salvo" in out

            found = search_contacts("Pedro Unna")
            assert len(found) >= 1
            assert found[0]["jid"] == jid


if __name__ == "__main__":
    test_assign_and_search_by_display_name()
    test_format_contact_names()
    test_set_whatsapp_contact_name_tool()
    print("ok")
