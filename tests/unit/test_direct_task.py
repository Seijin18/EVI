import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.direct_task import _parse_title, wants_task  # noqa: E402


def test_wants_task():
    assert wants_task("Você pode criar uma task de teste?")
    assert wants_task("criar tarefa comprar leite")
    assert not wants_task("listar compromissos")


def test_parse_title():
    assert "teste" in _parse_title("criar uma task de teste?").lower()


if __name__ == "__main__":
    test_wants_task()
    test_parse_title()
    print("ok")
