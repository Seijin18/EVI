"""In-memory stand-in for the scheduled_tasks db helpers (same CAS semantics as the SQL)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest


class FakeSchedDB:
    def __init__(self):
        self.rows: dict[int, dict] = {}
        self._id = 0
        self._lock = threading.Lock()

    def create_scheduled_task(self, title, prompt, next_at, repeat):
        with self._lock:
            self._id += 1
            self.rows[self._id] = {
                "id": self._id, "title": title, "prompt": prompt, "next_at": next_at,
                "repeat": repeat, "active": True,
                "created_at": datetime.now(timezone.utc), "last_run_at": None,
                "last_status": None, "runs_day": None, "runs_today": 0,
            }
            return self._id

    def get_scheduled_task(self, tid):
        r = self.rows.get(tid)
        return dict(r) if r else None

    def list_scheduled_tasks(self, active_only=False):
        rows = [dict(r) for r in self.rows.values() if r["active"] or not active_only]
        return sorted(rows, key=lambda r: (r["next_at"], r["id"]))

    def count_active_scheduled_tasks(self):
        return sum(1 for r in self.rows.values() if r["active"])

    def delete_scheduled_task(self, tid):
        return self.rows.pop(tid, None) is not None

    def set_scheduled_task_active(self, tid, active, next_at=None):
        r = self.rows.get(tid)
        if not r:
            return False
        r["active"] = active
        if next_at is not None:
            r["next_at"] = next_at
        return True

    def due_scheduled_tasks(self, now, limit=20):
        rows = [dict(r) for r in self.rows.values() if r["active"] and r["next_at"] <= now]
        return sorted(rows, key=lambda r: (r["next_at"], r["id"]))[:limit]

    def scheduled_runs_on(self, day):
        return sum(r["runs_today"] for r in self.rows.values() if r["runs_day"] == day)

    def claim_scheduled_task(self, tid, expected_next_at, new_next_at, active, day, count_run=True):
        with self._lock:
            r = self.rows.get(tid)
            if not r or not r["active"] or r["next_at"] != expected_next_at:
                return None
            r["next_at"], r["active"] = new_next_at, active
            if count_run:
                r["runs_today"] = r["runs_today"] + 1 if r["runs_day"] == day else 1
                r["runs_day"] = day
            return dict(r)

    def finish_scheduled_task(self, tid, status, ran_at=None):
        r = self.rows.get(tid)
        if r:
            r["last_status"] = status
            if ran_at is not None:
                r["last_run_at"] = ran_at


@pytest.fixture
def fake_db(monkeypatch):
    import db

    fake = FakeSchedDB()
    monkeypatch.setattr(db, "init_db", lambda: None)
    for name in (
        "create_scheduled_task", "get_scheduled_task", "list_scheduled_tasks",
        "count_active_scheduled_tasks", "delete_scheduled_task",
        "set_scheduled_task_active", "due_scheduled_tasks", "scheduled_runs_on",
        "claim_scheduled_task", "finish_scheduled_task",
    ):
        monkeypatch.setattr(db, name, getattr(fake, name))
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "true")
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    return fake
