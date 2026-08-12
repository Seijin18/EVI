import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

from services.evolution_filter import filter_for_processing
from services.message_sources import IncomingMessage

GROUP_JID = "120363012345678901@g.us"
OTHER_GROUP = "120363099999999999@g.us"


def _recent_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _group_msg(jid: str = GROUP_JID, msg_id: str = "g1") -> IncomingMessage:
    return IncomingMessage(
        id=msg_id,
        sender=jid,
        text="Reunião amanhã às 10h",
        ts=_recent_ts(),
        is_group=True,
    )


def _env(**overrides: str):
    base = {
        "EVI_WHATSAPP_SKIP_GROUPS": "true",
        "EVI_WHATSAPP_DEDUPE_IDS": "false",
    }
    base.update(overrides)
    return patch.dict(os.environ, base, clear=False)


def test_skips_groups_by_default(tmp_path):
    env = {"EVI_WHATSAPP_SKIP_GROUPS": "true", "EVI_WHATSAPP_DEDUPE_IDS": "false"}
    with patch.dict(os.environ, env, clear=True):
        kept, stats, dropped = filter_for_processing([_group_msg()], log_dir=tmp_path)

    assert kept == []
    assert stats["skipped_group"] == 1
    assert dropped[0]["reason"] == "group"
    assert dropped[0]["message_ts"]


def test_whitelisted_group_passes(tmp_path):
    with _env(EVI_WHATSAPP_GROUP_WHITELIST=GROUP_JID):
        kept, stats, dropped = filter_for_processing([_group_msg()], log_dir=tmp_path)

    assert len(kept) == 1
    assert dropped == []
    assert kept[0].sender == GROUP_JID
    assert stats["skipped_group"] == 0


def test_non_whitelisted_group_still_skipped(tmp_path):
    with _env(EVI_WHATSAPP_GROUP_WHITELIST=GROUP_JID):
        kept, stats, dropped = filter_for_processing([_group_msg(jid=OTHER_GROUP)], log_dir=tmp_path)

    assert kept == []
    assert stats["skipped_group"] == 1
    assert dropped[0]["reason"] == "group"


def test_skips_missing_timestamp(tmp_path):
    msg = IncomingMessage(
        id="no-ts-1",
        sender="5511999999999@s.whatsapp.net",
        text="Reunião amanhã às 10h",
        ts="",
        is_group=False,
    )
    with patch.dict(
        os.environ,
        {"EVI_WHATSAPP_REQUIRE_TS": "true", "EVI_WHATSAPP_DEDUPE_IDS": "false"},
        clear=True,
    ):
        kept, stats, dropped = filter_for_processing([msg], log_dir=tmp_path)
    assert kept == []
    assert stats["skipped_no_ts"] == 1
    assert dropped[0]["reason"] == "no_ts"


if __name__ == "__main__":
    from pathlib import Path

    td = Path("/tmp/evi-test-evolution-filter")
    td.mkdir(parents=True, exist_ok=True)
    test_skips_groups_by_default(td)
    test_whitelisted_group_passes(td)
    test_non_whitelisted_group_still_skipped(td)
    print("All evolution_filter unit tests passed")


def test_seen_ids_evicts_oldest_not_arbitrary(tmp_path, monkeypatch):
    """SCN-WA-17 — trimming an unordered set could drop a just-seen id."""
    from services import evolution_filter as ef

    monkeypatch.setattr(ef, "_MAX_SEEN_IDS", 5)
    path = tmp_path / "seen.json"

    seen = ef.SeenIds()
    for i in range(5):
        seen.add(f"old-{i}")
    seen.add("newest")
    ef._save_seen_ids(path, seen)

    stored = json.loads(path.read_text())
    assert len(stored) == 5
    assert "newest" in stored, "the most recent id must survive a trim"
    assert "old-0" not in stored, "the oldest id is the one to drop"
    assert stored == ["old-1", "old-2", "old-3", "old-4", "newest"]


def test_seen_ids_round_trips_existing_json(tmp_path):
    """On-disk format is unchanged, so existing files keep loading."""
    from services import evolution_filter as ef

    path = tmp_path / "seen.json"
    path.write_text(json.dumps(["a", "b", "c"]), encoding="utf-8")
    seen = ef._load_seen_ids(path)
    assert "b" in seen and len(seen) == 3
    assert seen.newest(2) == ["b", "c"]


def test_readding_an_id_refreshes_its_position(tmp_path):
    from services import evolution_filter as ef

    seen = ef.SeenIds(["a", "b", "c"])
    seen.add("a")
    assert seen.newest(3) == ["b", "c", "a"]
    assert len(seen) == 3, "re-adding must not duplicate"


def test_claim_message_id_still_dedupes(tmp_path, monkeypatch):
    from services import evolution_filter as ef

    monkeypatch.setenv("EVI_WHATSAPP_DEDUPE_IDS", "true")
    assert ef.claim_message_id("msg-1", log_dir=tmp_path) is True
    assert ef.claim_message_id("msg-1", log_dir=tmp_path) is False
    assert ef.claim_message_id("msg-2", log_dir=tmp_path) is True
