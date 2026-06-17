"""Unit tests for services/response_format.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services.response_format import (  # noqa: E402
    format_inbox_result,
    format_task_result,
)


def test_format_task_created():
    raw = '{"status":"created","title":"Teste","task_id":"abc","due_date":""}'
    out = format_task_result("Teste", raw)
    assert "Tarefa criada" in out
    assert "Teste" in out
    assert "{" not in out


def test_format_inbox_with_messages():
    raw = (
        '{"status":"ok","count":1,"messages":['
        '{"id":"msg1","subject":"Olá","from":"a@b.com"}]}'
    )
    out = format_inbox_result(raw)
    assert "Caixa de entrada" in out
    assert "Olá" in out
    assert "msg1" in out
    assert "a@b.com" in out


def test_format_inbox_resource_error():
    raw = "Windmill failed: Resource u/foo/gmail not found"
    out = format_inbox_result(raw)
    assert "recurso Windmill" in out or "Gmail" in out


if __name__ == "__main__":
    test_format_task_created()
    test_format_inbox_with_messages()
    test_format_inbox_resource_error()
    print("ok")
