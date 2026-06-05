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
        kept, stats = filter_for_processing([_group_msg()], log_dir=tmp_path)

    assert kept == []
    assert stats["skipped_group"] == 1


def test_whitelisted_group_passes(tmp_path):
    with _env(EVI_WHATSAPP_GROUP_WHITELIST=GROUP_JID):
        kept, stats = filter_for_processing([_group_msg()], log_dir=tmp_path)

    assert len(kept) == 1
    assert kept[0].sender == GROUP_JID
    assert stats["skipped_group"] == 0


def test_non_whitelisted_group_still_skipped(tmp_path):
    with _env(EVI_WHATSAPP_GROUP_WHITELIST=GROUP_JID):
        kept, stats = filter_for_processing([_group_msg(jid=OTHER_GROUP)], log_dir=tmp_path)

    assert kept == []
    assert stats["skipped_group"] == 1


if __name__ == "__main__":
    from pathlib import Path

    td = Path("/tmp/evi-test-evolution-filter")
    td.mkdir(parents=True, exist_ok=True)
    test_skips_groups_by_default(td)
    test_whitelisted_group_passes(td)
    test_non_whitelisted_group_still_skipped(td)
    print("All evolution_filter unit tests passed")
