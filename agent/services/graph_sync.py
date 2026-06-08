"""Neo4j knowledge graph sync (Etapa 5b, optional)."""

from __future__ import annotations

import os
from typing import Any


def graph_enabled() -> bool:
    return bool(os.getenv("NEO4J_URI", "").strip())


def _driver():
    if not graph_enabled():
        return None
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return None
    uri = os.getenv("NEO4J_URI", "").strip()
    user = os.getenv("NEO4J_USER", "neo4j").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()
    if not password:
        return None
    return GraphDatabase.driver(uri, auth=(user, password))


def sync_commitment(
    *,
    commitment_id: int,
    jid: str,
    title: str,
    ctype: str,
    status: str = "pending",
    label: str = "",
) -> bool:
    """Upsert Contact + Commitment nodes and ORIGINATED_FROM edge."""
    driver = _driver()
    if not driver or not jid:
        return False
    cypher = """
    MERGE (c:Contact {jid: $jid})
      ON CREATE SET c.label = $label, c.created_at = datetime()
      ON MATCH SET c.label = coalesce($label, c.label)
    MERGE (m:Commitment {id: $cid})
      ON CREATE SET m.title = $title, m.type = $ctype, m.status = $status,
                    m.created_at = datetime()
      ON MATCH SET m.title = $title, m.type = $ctype, m.status = $status
    MERGE (m)-[:ORIGINATED_FROM]->(c)
    """
    try:
        with driver.session() as session:
            session.run(
                cypher,
                jid=jid,
                label=label or jid,
                cid=commitment_id,
                title=title,
                ctype=ctype,
                status=status,
            )
        return True
    except Exception:
        return False
    finally:
        driver.close()


def run_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    driver = _driver()
    if not driver:
        return []
    try:
        with driver.session() as session:
            result = session.run(query, **(params or {}))
            return [r.data() for r in result]
    except Exception:
        return []
    finally:
        driver.close()
