import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.graph_tool import query_conversation_graph  # noqa: E402


def test_graph_disabled_without_neo4j():
    old = os.environ.pop("NEO4J_URI", None)
    try:
        out = query_conversation_graph.invoke({"jid": "", "limit": 5})
        assert "disabled" in out.lower()
    finally:
        if old:
            os.environ["NEO4J_URI"] = old


def test_graph_query_with_mock():
    with patch.dict(os.environ, {"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "x"}):
        with patch("tools.graph_tool.run_cypher", return_value=[{"id": 1, "title": "Call"}]):
            out = query_conversation_graph.invoke({"jid": "5511@s.whatsapp.net", "limit": 5})
    assert "Call" in out


if __name__ == "__main__":
    test_graph_disabled_without_neo4j()
    test_graph_query_with_mock()
    print("ok")
