"""Unit tests for list_tasks tool and formatter."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.response_format import format_list_tasks_result  # noqa: E402


def test_format_list_tasks_ok():
    raw = json.dumps(
        {
            "status": "ok",
            "tasks": [
                {"title": "definir requisitos plataforma", "due": "sem prazo"},
            ],
        }
    )
    out = format_list_tasks_result(raw)
    assert "definir requisitos plataforma" in out
    assert "Tarefas abertas" in out


def test_format_list_tasks_empty():
    out = format_list_tasks_result(json.dumps({"status": "ok", "tasks": []}))
    assert "Nenhuma tarefa" in out


def test_list_tasks_invoke_mock():
    try:
        from tools.task_tool import list_tasks
    except ImportError:
        return  # langchain not on host; CI/container runs full suite

    payload = json.dumps(
        {
            "status": "ok",
            "tasks": [{"title": "Test", "due": "2026-06-20"}],
            "count": 1,
        }
    )
    with patch("integrations.factory.get_integration") as get_int:
        get_int.return_value.post.return_value = payload
        out = list_tasks.invoke({"max_results": 10})
    assert "Test" in str(out)


if __name__ == "__main__":
    test_format_list_tasks_ok()
    test_format_list_tasks_empty()
    test_list_tasks_invoke_mock()
    print("ok")
