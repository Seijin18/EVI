"""Guard for DB-mutating tests.

Tests marked `@pytest.mark.ephemeral_db` insert/update/delete rows (and some run the
signals/prune jobs). They run only against a throwaway Postgres: set both
DATABASE_URL and EVI_TEST_EPHEMERAL_DB=1 (CI does). A developer whose DATABASE_URL
points at the dev database never has them touch it. Rows inserted through
db.insert_turn / db.insert_probe during such a test are deleted afterwards.
"""

import os

import pytest


def _enabled() -> bool:
    return bool(os.getenv("DATABASE_URL")) and os.getenv("EVI_TEST_EPHEMERAL_DB") == "1"


def pytest_collection_modifyitems(config, items):
    if _enabled():
        return
    skip = pytest.mark.skip(
        reason="DB-mutating test: needs DATABASE_URL and EVI_TEST_EPHEMERAL_DB=1 (ephemeral Postgres only)"
    )
    for item in items:
        if "ephemeral_db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _cleanup_inserted_rows(request):
    if "ephemeral_db" not in request.keywords or not _enabled():
        yield
        return
    import db

    turn_ids: list = []
    probe_ids: list = []
    real_turn, real_probe = db.insert_turn, db.insert_probe

    def tracked_turn(*a, **k):
        tid = real_turn(*a, **k)
        turn_ids.append(tid)
        return tid

    def tracked_probe(*a, **k):
        pid = real_probe(*a, **k)
        probe_ids.append(pid)
        return pid

    db.insert_turn, db.insert_probe = tracked_turn, tracked_probe
    try:
        yield
    finally:
        db.insert_turn, db.insert_probe = real_turn, real_probe
        try:
            with db._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM turn_log WHERE id = ANY(%s)", (turn_ids,))
                    cur.execute("DELETE FROM probe_log WHERE id = ANY(%s)", (probe_ids,))
                conn.commit()
        except Exception:
            pass
