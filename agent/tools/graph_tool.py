"""Query Neo4j conversation graph (Etapa 5b, optional)."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from services.graph_sync import graph_enabled, run_cypher


@tool
def query_conversation_graph(
    jid: str = "",
    limit: int = 10,
) -> str:
    """
    Query the EVI knowledge graph for contacts and commitments (Neo4j only).
    Requires NEO4J_URI. Prefer get_whatsapp_contact_info / list_whatsapp_contacts for names.
    Filter by WhatsApp/Telegram JID when provided.
    """
    if not graph_enabled():
        return "Graph memory disabled (set NEO4J_URI and NEO4J_PASSWORD)."
    if jid:
        rows = run_cypher(
            """
            MATCH (c:Contact {jid: $jid})<-[:ORIGINATED_FROM]-(m:Commitment)
            RETURN m.id AS id, m.title AS title, m.type AS type, m.status AS status
            ORDER BY m.created_at DESC
            LIMIT $limit
            """,
            {"jid": jid, "limit": limit},
        )
    else:
        rows = run_cypher(
            """
            MATCH (c:Contact)<-[:ORIGINATED_FROM]-(m:Commitment)
            RETURN c.jid AS jid, m.id AS id, m.title AS title, m.status AS status
            ORDER BY m.created_at DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )
    if not rows:
        return "No graph results."
    return json.dumps(rows, ensure_ascii=False, indent=2)
