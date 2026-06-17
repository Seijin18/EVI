"""Unit tests for direct_task title parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services.direct_task import _parse_title  # noqa: E402


def test_task_de_teste_para_mim():
    assert _parse_title("Crie uma task de teste para mim") == "Tarefa de teste"


def test_quoted_title():
    assert _parse_title('criar tarefa "Comprar leite"') == "Comprar leite"


if __name__ == "__main__":
    test_task_de_teste_para_mim()
    test_quoted_title()
    print("ok")
