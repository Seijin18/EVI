"""SCN-TASK-06/07: complete_tasks resolves targets in code and completes them."""

import json

import pytest

from tools import task_tool

TASKS = [
    {"id": "aaaaaaaa11", "title": "Avaliar PowerPoint do mestrado", "due": "sem prazo"},
    {"id": "bbbbbbbb22", "title": "Implementar análise de tempo", "due": "sem prazo"},
    {"id": "cccccccc33", "title": "Implementar lembretes", "due": "sem prazo"},
]


class FakeIntegration:
    def __init__(self, fail=()):
        self.completed, self.fail = [], set(fail)

    def post(self, op, payload, **_k):
        if op == "list_tasks":
            return json.dumps({"status": "ok", "count": len(TASKS), "tasks": TASKS})
        if payload["task_id"] in self.fail:
            return json.dumps({"status": "error", "http_status": 500, "detail": "x"})
        self.completed.append(payload["task_id"])
        return json.dumps({"status": "completed", "task_id": payload["task_id"]})


@pytest.fixture
def integ(monkeypatch):
    fake = FakeIntegration()
    monkeypatch.setattr(task_tool, "get_integration", lambda: fake)
    return fake


def test_all_open_except(integ):
    out = task_tool.complete_tasks_result([], True, ["mestrado"])
    assert out.ok and integ.completed == ["bbbbbbbb22", "cccccccc33"]
    assert out.data["kept"] == ["Avaliar PowerPoint do mestrado"]


def test_match_accent_insensitive_and_short_id(integ):
    out = task_tool.complete_tasks_result(["ANALISE de tempo", "[aaaaaaaa]"], False, [])
    assert out.ok and integ.completed == ["aaaaaaaa11", "bbbbbbbb22"]


def test_nothing_without_target(integ):
    out = task_tool.complete_tasks_result([], False, [])
    assert not out.ok and integ.completed == []


def test_unmatched_reported(integ):
    out = task_tool.complete_tasks_result(["inexistente"], False, [])
    assert integ.completed == [] and out.data["unmatched"] == ["inexistente"]


def test_partial_failure_is_reported(monkeypatch):
    fake = FakeIntegration(fail={"cccccccc33"})
    monkeypatch.setattr(task_tool, "get_integration", lambda: fake)
    out = task_tool.complete_tasks_result([], True, ["mestrado"])
    assert not out.ok and out.data["failed"] == ["Implementar lembretes"]
    assert out.data["completed"] == ["Implementar análise de tempo"]


def test_list_tasks_shows_short_id():
    from services.response_format import format_list_tasks_result

    assert "[aaaaaaaa]" in format_list_tasks_result(
        json.dumps({"status": "ok", "tasks": TASKS})
    )
