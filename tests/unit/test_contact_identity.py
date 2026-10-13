"""SCN-MEM-21 — one person, two JIDs (@lid / @s.whatsapp.net), one identity."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

import db  # noqa: E402
from services import contact_identity, whatsapp_activity  # noqa: E402
from services.contact_filesystem import contact_dir, list_contact_dirs  # noqa: E402
from services.message_sources import IncomingMessage  # noqa: E402
from services.message_timeline import record_whatsapp_message  # noqa: E402

LID = "99887766554433@lid"
PHONE = "5511948260209@s.whatsapp.net"


@pytest.fixture
def aliases(monkeypatch, tmp_path):
    """In-memory wa_jid_alias behind the real db function names."""
    store: dict[str, str] = {}
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/fake")
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "get_jid_alias", lambda lid: store.get(lid))
    monkeypatch.setattr(db, "upsert_jid_alias", lambda lid, p: store.__setitem__(lid, p))
    monkeypatch.setattr(db, "merge_conversation_state", lambda src, dst: False)
    monkeypatch.setattr(
        db, "list_jid_aliases", lambda: [{"lid": k, "phone_jid": v} for k, v in store.items()]
    )
    contact_identity.reset_cache_for_tests()
    yield store
    contact_identity.reset_cache_for_tests()


def _msg(jid, mid, text="oi", ts="2026-10-01T10:00:00+00:00", from_me=False):
    return IncomingMessage(id=mid, sender=jid, text=text, ts=ts, from_me=from_me, label="Fulana")


def test_canonical_known_unknown_and_non_lid(aliases):
    aliases[LID] = PHONE
    assert contact_identity.canonical_jid(LID) == PHONE
    assert contact_identity.canonical_jid("1@lid") == "1@lid"
    assert contact_identity.canonical_jid(PHONE) == PHONE
    assert contact_identity.canonical_jid("1@g.us") == "1@g.us"


def test_canonical_db_failure_returns_jid(aliases, monkeypatch):
    def boom(_):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "get_jid_alias", boom)
    assert contact_identity.canonical_jid(LID) == LID


def test_canonical_without_database_is_identity(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    contact_identity.reset_cache_for_tests()
    assert contact_identity.canonical_jid(LID) == LID


def test_alias_recorded_from_message_payload(aliases):
    raw = {"key": {"id": "A1", "remoteJid": LID, "remoteJidAlt": PHONE, "fromMe": False}}
    assert contact_identity.record_alias_from_message(raw)
    assert aliases == {LID: PHONE}
    # wrapped webhook payload
    aliases.clear()
    contact_identity.reset_cache_for_tests()
    assert contact_identity.record_alias_from_message({"data": raw})
    assert aliases == {LID: PHONE}


def test_alias_ignored_when_shapes_are_wrong(aliases):
    for key in (
        {"remoteJid": PHONE, "remoteJidAlt": LID},
        {"remoteJid": LID, "remoteJidAlt": "123@g.us"},
        {"remoteJid": LID},
    ):
        assert not contact_identity.record_alias_from_message({"key": key})
    assert aliases == {}


def test_parser_records_alias_from_remote_jid_alt(aliases):
    from services.evolution_parser import parse_evolution_message_list

    data = [
        {
            "key": {"id": "B1", "remoteJid": LID, "remoteJidAlt": PHONE, "fromMe": False},
            "message": {"conversation": "oi"},
            "messageTimestamp": 1790000000,
        }
    ]
    msgs = parse_evolution_message_list(data, remote_jid=LID)
    assert len(msgs) == 1 and aliases == {LID: PHONE}


def test_scn_mem_21_timelines_land_in_one_directory(aliases, tmp_path):
    aliases[LID] = PHONE
    assert record_whatsapp_message(_msg(LID, "m1", "do lid"))
    assert record_whatsapp_message(_msg(PHONE, "m2", "do telefone", from_me=True))
    dirs = [p.name for p in list_contact_dirs()]
    assert dirs == [PHONE]
    lines = (contact_dir(PHONE) / "timeline.jsonl").read_text().splitlines()
    assert {json.loads(x)["source_id"] for x in lines} == {"m1", "m2"}
    assert contact_dir(LID) == contact_dir(PHONE)


def test_unknown_lid_keeps_its_own_directory(aliases):
    record_whatsapp_message(_msg(LID, "m1"))
    assert [p.name for p in list_contact_dirs()] == [LID]


def test_scn_mem_21_summary_shows_one_conversation(aliases):
    aliases[LID] = PHONE
    rows = [
        {"ts": "2026-10-01T10:00:00", "chat_jid": LID, "chat_label": "Fulana", "chat_phone": "",
         "from_me": False, "text": "oi", "preview": "oi"},
        {"ts": "2026-10-01T11:00:00", "chat_jid": PHONE, "chat_label": "Fulana",
         "chat_phone": "+55 11 94826-0209", "from_me": True, "text": "e aí", "preview": "e aí"},
    ]
    lines = whatsapp_activity.conversation_lines(rows)
    assert sum(1 for line in lines if line.startswith("💬")) == 1
    assert sum(1 for line in lines if line.startswith("  •")) == 2


def test_reply_debts_track_under_canonical_jid(aliases, monkeypatch):
    from services import reply_debts

    aliases[LID] = PHONE
    seen = []

    class Fake:
        def __getattr__(self, name):
            return lambda *a, **k: None

    fake = Fake()
    fake.init_db = lambda: None
    fake.record_inbound = lambda jid, ts, preview, mid: seen.append(jid)
    fake.get_jid_alias = db.get_jid_alias
    monkeypatch.setitem(sys.modules, "db", fake)
    assert reply_debts.track_conversation([_msg(LID, "m1")]) == 1
    assert seen == [PHONE]


# --- migration ---------------------------------------------------------------


def _write_dir(root, jid, rows, profile):
    d = root / "contacts" / jid
    (d / "summaries").mkdir(parents=True)
    (d / "timeline.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (d / "profile.md").write_text(profile, encoding="utf-8")
    return d


def _snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() if p.is_file() else None
        for p in sorted(root.rglob("*"))
    }


@pytest.fixture
def two_dirs(aliases, tmp_path):
    aliases[LID] = PHONE
    lid = _write_dir(
        tmp_path, LID,
        [
            {"ts": "2026-10-01T12:00:00+00:00", "source_id": "a", "text_preview": "lid-a"},
            {"ts": "2026-10-01T09:00:00+00:00", "source_id": "dup", "text_preview": "same"},
        ],
        "# LID PROFILE SECRET-FACT\n",
    )
    (lid / "summaries" / "2026-10-01.md").write_text("resumo lid", encoding="utf-8")
    phone = _write_dir(
        tmp_path, PHONE,
        [
            {"ts": "2026-10-01T10:00:00+00:00", "source_id": "b", "text_preview": "phone-b"},
            {"ts": "2026-10-01T09:00:00+00:00", "source_id": "dup", "text_preview": "same"},
        ],
        "# PHONE PROFILE\n",
    )
    return lid, phone


def test_migration_dry_run_changes_nothing(aliases, tmp_path, two_dirs):
    before = _snapshot(tmp_path)
    counts = contact_identity.migrate_lid_dirs(apply=False)
    assert counts["lid_dirs"] == 1 and counts["mergeable"] == 1 and counts["merged"] == 0
    assert _snapshot(tmp_path) == before


def test_migration_apply_merges_dedupes_orders_and_renames(aliases, tmp_path, two_dirs, monkeypatch):
    monkeypatch.setattr(db, "get_state", lambda jid: None)
    monkeypatch.setattr(db, "merge_conversation_state", lambda a, b: False)
    lid, phone = two_dirs
    counts = contact_identity.migrate_lid_dirs(apply=True)
    assert counts["merged"] == 1 and counts["timeline_added"] == 1
    rows = [json.loads(x) for x in (phone / "timeline.jsonl").read_text().splitlines()]
    assert [r["source_id"] for r in rows] == ["dup", "b", "a"]  # unique, ordered by ts
    # renamed, not deleted
    assert not lid.exists()
    renamed = [p for p in (tmp_path / "contacts").iterdir() if ".merged-" in p.name]
    assert len(renamed) == 1 and (renamed[0] / "timeline.jsonl").is_file()
    assert [p.name for p in list_contact_dirs()] == [PHONE]
    # the lid profile never replaces the phone's; it is kept in history.md
    assert (phone / "profile.md").read_text() == "# PHONE PROFILE\n"
    assert "SECRET-FACT" in (phone / "history.md").read_text()
    assert "## Perfil anterior (@lid)" in (phone / "history.md").read_text()
    assert (phone / "summaries" / "2026-10-01.md").read_text() == "resumo lid"


def test_migration_without_alias_leaves_lid_dir(aliases, tmp_path):
    _write_dir(tmp_path, LID, [], "# p\n")
    counts = contact_identity.migrate_lid_dirs(apply=True)
    assert counts["lid_dirs"] == 1 and counts["merged"] == 0
    assert (tmp_path / "contacts" / LID).is_dir()


@pytest.mark.ephemeral_db
def test_db_alias_roundtrip_and_state_merge():
    db.reset_db_init_for_tests()
    db.init_db()
    db.upsert_jid_alias(LID, PHONE)
    assert db.get_jid_alias(LID) == PHONE
    assert db.get_jid_alias("zzz@lid") is None
    assert any(a["lid"] == LID for a in db.list_jid_aliases())
    t0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    db.record_inbound(LID, t0 + timedelta(hours=2), "novo", "m2")
    db.record_inbound(PHONE, t0, "velho", "m1")
    db.record_outbound(PHONE, t0 + timedelta(hours=1))
    assert db.merge_conversation_state(LID, PHONE)
    assert db.get_state(LID) is None
    st = db.get_state(PHONE)
    assert st["last_in_preview"] == "novo" and st["last_in_at"] == t0 + timedelta(hours=2)
    assert st["last_out_at"] == t0 + timedelta(hours=1)


# --- stale @lid state (inbound before the alias was known) -------------------


@pytest.fixture
def real_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db.DATABASE_URL)
    db.reset_db_init_for_tests()
    db.init_db()
    contact_identity.reset_cache_for_tests()
    yield
    contact_identity.reset_cache_for_tests()


def _debt_jids(now):
    from services import reply_debts

    return [d["jid"] for d in reply_debts.list_debts(now=now, min_hours=1)]


@pytest.mark.ephemeral_db
def test_stale_lid_inbound_then_reply_under_phone_leaves_no_debt(real_db):
    t0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    now = t0 + timedelta(hours=6)
    db.record_inbound(LID, t0, "oi", "m1")  # alias unknown at the time
    assert _debt_jids(now) == [LID]
    assert contact_identity.record_alias(LID, PHONE)  # folds the stale row
    assert db.get_state(LID) is None
    assert _debt_jids(now) == [PHONE]  # counted once, under the phone jid
    db.record_outbound(PHONE, t0 + timedelta(hours=1))  # user answers under the phone jid
    assert _debt_jids(now) == []


@pytest.mark.ephemeral_db
def test_acknowledge_phone_clears_debt_created_by_lid_inbound(real_db, monkeypatch):
    t0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    now = t0 + timedelta(hours=6)
    db.record_inbound(LID, t0, "oi", "m1")
    db.upsert_jid_alias(LID, PHONE)  # alias written elsewhere; no fold yet
    contact_identity.reset_cache_for_tests()
    assert _debt_jids(now) == [PHONE]  # list_debts folds lazily
    db.acknowledge(PHONE, t0 + timedelta(hours=2))
    assert _debt_jids(now) == []


@pytest.mark.ephemeral_db
def test_merge_state_keeps_concurrent_newer_values():
    db.reset_db_init_for_tests()
    db.init_db()
    t0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    db.record_inbound(PHONE, t0 + timedelta(hours=3), "novo", "m9")
    db.record_inbound(LID, t0, "velho", "m1")
    assert db.merge_conversation_state(LID, PHONE)
    st = db.get_state(PHONE)
    assert st["last_in_preview"] == "novo" and st["last_in_id"] == "m9"
    assert not db.merge_conversation_state(LID, PHONE)


@pytest.mark.ephemeral_db
def test_alias_remap_is_logged_with_last_four_digits_only(real_db, monkeypatch):
    import services.soft_fail as sf

    seen = []
    monkeypatch.setattr(sf, "soft_fail", lambda where, exc: seen.append(str(exc)))
    db.upsert_jid_alias(LID, PHONE)
    assert seen == []
    db.upsert_jid_alias(LID, "5511999990000@s.whatsapp.net")
    assert len(seen) == 1 and "0000" in seen[0] and "5511999990000" not in seen[0]
    assert db.get_jid_alias(LID) == "5511999990000@s.whatsapp.net"


def test_discovery_alt_requires_matching_remote_jid():
    from services.evolution_discovery import _alt_phone_jid

    recs = [
        {"key": {"remoteJid": "other@lid", "remoteJidAlt": "5511111111111@s.whatsapp.net"}},
        {"key": {"remoteJid": LID, "remoteJidAlt": PHONE}},
    ]
    assert _alt_phone_jid(recs, LID) == PHONE
    assert _alt_phone_jid(recs[:1], LID) == ""


def test_failed_alias_lookup_is_cached(aliases, monkeypatch):
    calls = []

    def boom(_):
        calls.append(1)
        raise RuntimeError("down")

    monkeypatch.setattr(db, "get_jid_alias", boom)
    for _ in range(3):
        assert contact_identity.canonical_jid(LID) == LID
    assert len(calls) == 1


def test_migration_is_idempotent_for_history_and_backs_up_timeline(aliases, tmp_path, two_dirs, monkeypatch):
    monkeypatch.setattr(db, "merge_conversation_state", lambda a, b: False)
    lid, phone = two_dirs
    contact_identity._merge_dir(lid, phone, PHONE, "T1")
    contact_identity._merge_dir(lid, phone, PHONE, "T2")
    assert (phone / "history.md").read_text().count("## Perfil anterior (@lid)") == 1
    assert (phone / "timeline.jsonl.pre-merge-T1").is_file()
    assert not list(phone.glob("timeline.jsonl.tmp-*"))
