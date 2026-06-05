"""Unit tests for commitment priority (SCN inbox)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services.commitment_priority import classify_priority


def test_urgent():
    assert classify_priority("preciso urgente hoje") == "urgent"


def test_university():
    assert classify_priority("prova de faculdade sexta") == "university"


def test_work():
    assert classify_priority("reunião com cliente amanhã") == "work"


def test_normal():
    assert classify_priority("jantar domingo") == "normal"


if __name__ == "__main__":
    test_urgent()
    test_university()
    test_work()
    test_normal()
    print("All commitment_priority tests passed")
