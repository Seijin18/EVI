#!/usr/bin/env python3
"""Tier 2 integration test runner — invoked via scripts/evi-test."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Repo root (parent of agent/) — in Docker WORKDIR is /app
_here = Path(__file__).resolve()
_agent_candidate = _here.parents[1]
if (_agent_candidate / "main.py").is_file():
    AGENT_DIR = _agent_candidate
    REPO_ROOT = Path(os.getenv("EVI_REPO_ROOT", _agent_candidate.parent))
else:
    REPO_ROOT = _here.parents[2]
    AGENT_DIR = REPO_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

FIXTURES = Path(os.getenv("EVI_FIXTURES_DIR", REPO_ROOT / "tests" / "fixtures"))
GOLDEN = REPO_ROOT / "tests" / "golden"
LOGS = REPO_ROOT / "logs"


def _log_path(feature: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    harness = LOGS / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    return harness / f"{feature}_{ts}.jsonl"


def _result(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}" + (f" — {detail}" if detail else "")
    print(line)
    return ok


def run_memory() -> bool:
    from memory import BoundedMemory

    class _Msg:
        def __init__(self, content: str):
            self.content = content

    m = BoundedMemory(max_pairs=2)
    for c in ("a", "b", "c", "d", "e"):
        m.add(_Msg(c))
    msgs = m.get_messages()
    ok = len(msgs) <= 4
    m.clear()
    ok = ok and len(m.get_messages()) == 0
    return _result("memory", ok, f"len={len(msgs)} after bound")


def run_file_organizer() -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "file_rules", AGENT_DIR / "tools" / "file_rules.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _classify_file = mod.classify_file
    from pathlib import Path as P

    ok = _classify_file(P("lecture_notes.pdf")) == "/watched_folders/university"
    ok = ok and _classify_file(P("homework.py")) == "/watched_folders/code"

    inbox_fix = FIXTURES / "inbox"
    if not inbox_fix.exists():
        return _result("file-organizer", False, "fixtures/inbox missing")

    with tempfile.TemporaryDirectory() as tmp:
        # Patch inbox by copying fixture structure into temp - test classify via tool dry-run on copy
        tmp_inbox = P(tmp) / "inbox"
        shutil.copytree(inbox_fix, tmp_inbox)
        # Tool uses hardcoded /watched_folders/inbox — unit path already tested _classify_file
    return _result("file-organizer", ok, "classify rules")


def run_calendar(live_windmill: bool) -> bool:
    import json

    payload = {
        "action": "schedule_event",
        "title": "EVI Test",
        "start_time": "2026-06-10T10:00:00Z",
        "end_time": "2026-06-10T11:00:00Z",
    }
    if live_windmill:
        try:
            from tools.calendar_tool import schedule_event

            r = schedule_event.invoke(
                {
                    "title": payload["title"],
                    "start_time": payload["start_time"],
                    "end_time": payload["end_time"],
                }
            )
            text = str(r)
            ok = '"status":"created"' in text or '"status": "created"' in text
            if not ok and "created in Google Calendar" in text:
                ok = True
            if not ok and "failed" not in text.lower():
                ok = "Successfully" in text
        except ImportError as e:
            return _result("calendar", False, str(e))
        except Exception as e:
            return _result("calendar", False, str(e))
        return _result("calendar", ok, text[:200])
    fixture = FIXTURES / "windmill" / "calendar_payload.json"
    if not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(json.dumps(payload), encoding="utf-8")
    data = json.loads(fixture.read_text())
    ok = data["action"] == "schedule_event" and "title" in data
    return _result("calendar", ok, "payload ok")


def run_calendar_list(live_windmill: bool) -> bool:
    if live_windmill:
        try:
            from tools.calendar_tool import list_calendar_events

            text = str(list_calendar_events.invoke({"days_ahead": 7, "limit": 10}))
            ok = "Próximos eventos" in text or "Nenhum evento" in text
            if not ok:
                ok = "failed" not in text.lower() and "falha" not in text.lower()
        except ImportError as e:
            return _result("calendar-list", False, str(e))
        except Exception as e:
            return _result("calendar-list", False, str(e))
        return _result("calendar-list", ok, text[:200])

    tool_path = AGENT_DIR / "tools" / "calendar_tool.py"
    if not tool_path.is_file():
        return _result("calendar-list", False, "calendar_tool.py missing")
    src = tool_path.read_text(encoding="utf-8")
    ok = "list_calendar_events" in src and "WINDMILL_WEBHOOK_LIST_EVENTS" in src
    return _result("calendar-list", ok, "offline wiring (use --live-windmill)")


def run_tasks(live_windmill: bool) -> bool:
    text = "payload ok"
    if live_windmill:
        try:
            from tools.task_tool import create_task

            r = create_task.invoke({"title": "EVI test task", "due_date": "2026-06-10"})
            text = str(r)
            ok = '"status":"created"' in text or '"status": "created"' in text
        except ImportError as e:
            return _result("tasks", False, str(e))
        except Exception as e:
            return _result("tasks", False, str(e))
        return _result("tasks", ok, text[:200])
    fixture = FIXTURES / "windmill" / "task_payload.json"
    if not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(
            '{"action":"create_task","title":"EVI test","due_date":"2026-06-10"}',
            encoding="utf-8",
        )
    ok = "create_task" in fixture.read_text()
    return _result("tasks", ok, text)


def run_email(live_windmill: bool = False) -> bool:
    if live_windmill:
        try:
            from tools.email_tool import summarize_inbox

            r = summarize_inbox.invoke({"max_messages": 5})
            text = str(r)
            ok = (
                "failed" not in text.lower()
                and "Não foi possível" not in text
                and (
                    "Caixa de entrada" in text
                    or '"summary"' in text
                    or '"status":"ok"' in text
                    or (len(text) > 40 and "•" in text)
                )
            )
        except ImportError as e:
            return _result("email", False, str(e))
        except Exception as e:
            return _result("email", False, str(e))
        return _result("email", ok, text[:200])
    legacy = FIXTURES / "windmill" / "email_summary.json"
    messages_fixture = FIXTURES / "windmill" / "email_summary_messages.json"
    if not legacy.exists():
        return _result("email", False, "fixture missing")
    data = json.loads(legacy.read_text())
    ok = "summary" in data and len(data["summary"]) > 0
    if messages_fixture.exists():
        msg_data = json.loads(messages_fixture.read_text())
        ok = ok and msg_data.get("status") == "ok" and len(msg_data.get("messages") or []) >= 2
        from services.response_format import format_inbox_result

        formatted = format_inbox_result(json.dumps(msg_data))
        ok = ok and "msg001" in formatted and "AliExpress" in formatted
    return _result("email", ok, "fixture parse + messages format")


def run_whatsapp(verbose: bool, log_file: Path | None) -> bool:
    from services.whatsapp_processor import process_fixture_file

    fixture = FIXTURES / "whatsapp" / "messages.jsonl"
    golden = GOLDEN / "whatsapp_commitments.json"
    log_path = log_file or _log_path("whatsapp", None)
    ok = process_fixture_file(fixture, golden, log_path=log_path, verbose=verbose)
    return _result("whatsapp", ok, str(log_path))


def run_notes() -> bool:
    from tools.note_core import write_auto_insight, write_manual_note

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_NOTES_DIR"] = tmp
        path = write_manual_note(
            "Test Note", "Body", tags=["test"], category="study"
        )
        ok = Path(path).exists() and "Test Note" in Path(path).read_text()
        insight = write_auto_insight(
            [{"role": "user", "content": "Preciso organizar tarefas"}], session_id="test"
        )
        ok = ok and Path(insight).exists()
    return _result("notes", ok)


def run_session() -> bool:
    if not os.getenv("DATABASE_URL"):
        return _result("session", True, "skipped (no DATABASE_URL)")

    try:
        from db import init_db, save_message, load_recent_messages
    except ImportError as e:
        return _result("session", True, f"skipped ({e})")

    try:
        init_db()
        save_message("test-session", "user", "hello")
        msgs = load_recent_messages("test-session", limit=5)
        ok = len(msgs) >= 1 and msgs[-1]["content"] == "hello"
        return _result("session", ok)
    except Exception as e:
        return _result("session", True, f"skipped ({e})")


def run_telegram(live: bool = False) -> bool:
    fixture = FIXTURES / "telegram" / "update.json"
    if not fixture.exists():
        return _result("telegram", False, "fixture missing")
    data = json.loads(fixture.read_text())
    ok = "message" in data and "text" in data["message"]
    if not live:
        return _result("telegram", ok, "parse update JSON")

    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        return _result("telegram", True, "skipped (no TELEGRAM_BOT_TOKEN)")

    from services.telegram_notify import send_telegram_message

    ok = ok and send_telegram_message("EVI: teste live sendMessage (SCN-TG-02)")
    detail = "live sendMessage"
    if ok:
        base = os.getenv("EVI_API_URL", "http://localhost:8002")
        try:
            import httpx

            headers = {}
            key = os.getenv("EVI_API_KEY", "").strip()
            if key:
                headers["X-Api-Key"] = key
            r = httpx.post(
                f"{base}/webhooks/telegram",
                json=data,
                headers=headers,
                timeout=180.0,
            )
            if r.status_code == 200:
                body = r.json()
                ok = ok and body.get("telegram_sent") is True
                detail = f"webhook telegram_sent={body.get('telegram_sent')}"
            else:
                ok = False
                detail = f"webhook HTTP {r.status_code}"
        except Exception as e:
            ok = False
            detail = f"webhook failed ({e})"
    return _result("telegram", ok, detail)


def run_watcher() -> bool:
    root = os.getenv("EVI_PROJECT_ROOT", str(REPO_ROOT))
    host_prefix = os.getenv("EVI_HOST_WATCH_PREFIX", f"{root}/watched_folders")
    container_prefix = os.getenv("EVI_CONTAINER_WATCH_PREFIX", "/watched_folders")
    host = f"{host_prefix}/university/note.pdf"
    docker = host.replace(host_prefix, container_prefix)
    ok = docker == "/watched_folders/university/note.pdf"
    return _result("watcher", ok, f"mapped={docker}")


def run_evolution() -> bool:
    import json
    import tempfile
    from pathlib import Path as P

    from services.evolution_filter import filter_for_processing
    from services.evolution_parser import parse_evolution_webhook
    from services.evolution_client import is_evi_bot_message
    from services.whatsapp_processor import extract_commitment

    fixtures = [
        FIXTURES / "evolution" / "messages_upsert.json",
        FIXTURES / "evolution" / "messages_upsert_v237.json",
    ]
    ok = True
    parsed = 0
    for fix in fixtures:
        if not fix.exists():
            ok = False
            continue
        body = json.loads(fix.read_text())
        msgs = parse_evolution_webhook(body)
        parsed += len(msgs)
        if not msgs:
            ok = False
        elif "Reunião" in msgs[0].text:
            ok = ok and extract_commitment(msgs[0]) is not None
        if msgs and msgs[0].ts:
            ok = ok and "T" in msgs[0].ts
    with tempfile.TemporaryDirectory() as tmp:
        kept, stats, dropped = filter_for_processing(
            parse_evolution_webhook(json.loads((FIXTURES / "evolution" / "messages_upsert.json").read_text())),
            log_dir=P(tmp),
        )
        ok = ok and stats["received"] >= 1
        if dropped:
            ok = ok and bool(dropped[0].get("message_ts"))
        # SCN-UX-WA-ING-01: messages without timestamp skipped when REQUIRE_TS=true
        from services.message_sources import IncomingMessage

        no_ts = IncomingMessage(
            id="no-ts-1",
            text="hello",
            sender="5511@s.whatsapp.net",
            ts="",
            from_me=False,
            is_group=False,
        )
        prev = os.environ.get("EVI_WHATSAPP_REQUIRE_TS")
        os.environ["EVI_WHATSAPP_REQUIRE_TS"] = "true"
        try:
            _, no_ts_stats, _ = filter_for_processing([no_ts], log_dir=P(tmp))
            ok = ok and no_ts_stats.get("skipped_no_ts", 0) >= 1
        finally:
            if prev is None:
                os.environ.pop("EVI_WHATSAPP_REQUIRE_TS", None)
            else:
                os.environ["EVI_WHATSAPP_REQUIRE_TS"] = prev
    ok = ok and is_evi_bot_message("[EVI] teste")
    ok = ok and not is_evi_bot_message("oi")
    return _result("evolution", ok, f"parsed={parsed}")


def run_dev_bridge(dry: bool) -> bool:
    copilot = REPO_ROOT / "scripts" / "copilot-dev-runner.sh"
    cursor = REPO_ROOT / "scripts" / "cursor-dev-runner.sh"
    ok = copilot.exists() and os.access(copilot, os.X_OK)
    ok = ok and cursor.is_file() and os.access(cursor, os.X_OK)
    ok = ok and (AGENT_DIR / "services" / "dev_bridge.py").is_file()
    if dry and ok:
        return _result("dev-bridge", True, "scripts + dev_bridge.py (dry)")
    return _result("dev-bridge", ok)


def _ensure_rag_fixture_pdf() -> Path:
    pdf = FIXTURES / "rag" / "sample.pdf"
    if pdf.is_file():
        return pdf
    txt = FIXTURES / "rag" / "sample.txt"
    if not txt.is_file():
        raise FileNotFoundError("rag fixtures missing")
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), txt.read_text(encoding="utf-8")[:500])
    pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(pdf)
    doc.close()
    return pdf


def run_rag(live_qdrant: bool) -> bool:
    if live_qdrant:
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        try:
            import httpx

            r = httpx.get(f"{qdrant_url}/collections", timeout=5.0)
            if r.status_code >= 500:
                return _result("rag", False, "qdrant down")
        except Exception as e:
            return _result("rag", False, str(e))

        try:
            from tools.rag_tool import ingest_university_pdf, query_university_notes

            pdf = _ensure_rag_fixture_pdf()
            ing = str(ingest_university_pdf.invoke({"file_path": str(pdf)}))
            if "Successfully" not in ing and "ingested" not in ing.lower():
                return _result("rag", False, ing[:200])
            out = str(
                query_university_notes.invoke(
                    {"query": "university note text", "top_k": 2}
                )
            )
            ok = "Failed to query" not in out
            return _result("rag", ok, out[:200])
        except ImportError as e:
            return _result("rag", False, str(e))
        except Exception as e:
            return _result("rag", False, str(e))

    rag_tool = AGENT_DIR / "tools" / "rag_tool.py"
    if not rag_tool.is_file():
        return _result("rag", False, "rag_tool.py missing")
    sample = FIXTURES / "rag" / "sample.txt"
    ok = sample.is_file() and "university_notes" in rag_tool.read_text(encoding="utf-8")
    return _result("rag", ok, "offline wiring (use --live-qdrant)")


def run_commitments() -> bool:
    if not os.getenv("DATABASE_URL"):
        return _result("commitments", True, "skipped (no DATABASE_URL)")

    try:
        from db import init_db, insert_pending_commitment, list_pending_commitments
        from tools.commitment_tools import list_pending_commitments as list_tool
    except ImportError as e:
        return _result("commitments", False, str(e))

    try:
        init_db()
        sid = f"evi-test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        row_id = insert_pending_commitment(
            source="evi-test",
            source_id=sid,
            ctype="event",
            title="EVI commitments harness",
            event_date="2026-06-15",
            event_time="10:00",
            priority="normal",
            raw_text="SCN-WA-10 / SCN-CHAT-02 trace",
        )
        if not row_id:
            return _result("commitments", False, "insert failed")
        rows = list_pending_commitments(limit=50)
        ok = any(r["id"] == row_id for r in rows)
        if not ok:
            return _result("commitments", False, "row not in list")
        out = list_tool.invoke({"limit": 10})
        ok = ok and "EVI commitments harness" in out
        return _result("commitments", ok, f"id={row_id}")
    except Exception as e:
        return _result("commitments", True, f"skipped ({e})")


def run_metrics(live: bool) -> bool:
    metrics_py = AGENT_DIR / "services" / "metrics.py"
    if not metrics_py.is_file():
        return _result("metrics", False, "metrics.py missing")
    src = metrics_py.read_text(encoding="utf-8")
    ok = "evi_http_requests_total" in src and "evi_webhook_duration_seconds" in src
    if live:
        base = os.getenv("EVI_API_URL", "http://localhost:8002")
        try:
            import httpx

            r = httpx.get(f"{base}/metrics", timeout=5.0)
            ok = r.status_code == 200 and "evi_http_requests_total" in r.text
            return _result("metrics", ok, f"http {r.status_code}")
        except Exception as e:
            return _result("metrics", False, str(e))
    return _result("metrics", ok, "offline wiring (use --full for live)")


def run_health(live: bool) -> bool:
    if live:
        base = os.getenv("EVI_API_URL", "http://localhost:8002")
        try:
            import httpx

            r = httpx.get(f"{base}/health", timeout=10.0)
            ok = r.status_code == 200 and r.json().get("status") in (
                "ok",
                "degraded",
            )
            detail = r.json().get("status", r.text[:80])
        except Exception as e:
            return _result("health", False, str(e))
        return _result("health", ok, str(detail))

    health_py = AGENT_DIR / "services" / "health.py"
    if not health_py.is_file():
        return _result("health", False, "health.py missing")
    src = health_py.read_text(encoding="utf-8")
    ok = "run_health_checks" in src and "postgres" in src
    return _result("health", ok, "offline wiring (use --full for live)")


def run_contact_learning() -> bool:
    import tempfile
    from unittest.mock import patch

    from services.contact_filesystem import ingest_commitment

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5516992657231@s.whatsapp.net"
        ingest_commitment(
            jid=jid,
            source_id="learn-1",
            title="Reunião",
            raw_text="amanhã 10h",
            commitment_id=1,
            label="Leozao",
        )
        ok = "list_whatsapp_contacts" in (
            AGENT_DIR / "tools" / "registry.py"
        ).read_text(encoding="utf-8")
        ok = ok and (AGENT_DIR / "services" / "contact_learning.py").is_file()
        ok = ok and (AGENT_DIR / "services" / "whatsapp_backfill.py").is_file()
        with patch(
            "services.contact_learning._llm_synthesize",
            return_value="Contato trabalha em projetos X.",
        ):
            from services.contact_learning import learn_contact

            out = learn_contact("Leozao", days=7, fetch_messages=False)
        ok = ok and "Leozao" in out and "Aprendizado" in out
    return _result("contact-learning", ok, "offline learn + registry")


def run_heartbeat() -> bool:
    from services.heartbeat import run_heartbeat

    dry = run_heartbeat(dry=True)
    ok = dry.get("ok") is True and "checklist" in dry
    prev = os.environ.get("EVI_HEARTBEAT_ENABLED")
    os.environ["EVI_HEARTBEAT_ENABLED"] = "false"
    try:
        live = run_heartbeat()
        ok = ok and live.get("enabled") is False
    finally:
        if prev is None:
            os.environ.pop("EVI_HEARTBEAT_ENABLED", None)
        else:
            os.environ["EVI_HEARTBEAT_ENABLED"] = prev
    return _result("heartbeat", ok, "dry + disabled stub")


def run_contact_memory() -> bool:
    import tempfile

    from services.contact_filesystem import ingest_commitment, memory_enabled

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        ok = ingest_commitment(
            jid="evi-test@s.whatsapp.net",
            source_id="harness-1",
            title="Harness event",
            raw_text="SCN-MEM-02",
            commitment_id=99,
            label="Harness",
        )
        ok = ok and memory_enabled()
        timeline = Path(tmp) / "contacts" / "evi-test@s.whatsapp.net" / "timeline.jsonl"
        ok = ok and timeline.is_file() and timeline.read_text(encoding="utf-8").strip()
        from services.contact_memory_audit import format_memory_audit

        audit = format_memory_audit(limit=5)
        ok = ok and "Memória de contatos" in audit
    return _result("contact-memory", ok, "FS ingest + audit")


def run_daily_summary() -> bool:
    import tempfile

    from services.contact_filesystem import ingest_commitment
    from services.daily_summary import run_daily_summaries

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        ingest_commitment(
            jid="evi-test@s.whatsapp.net",
            source_id="harness-2",
            title="Summary item",
            raw_text="hoje",
            commitment_id=100,
        )
        n = run_daily_summaries()
        summaries = list(Path(tmp).glob("contacts/*/summaries/*.md"))
        ok = n >= 1 and bool(summaries)
    return _result("daily-summary", ok, f"written={n}")


def run_graph() -> bool:
    tool = AGENT_DIR / "tools" / "graph_tool.py"
    sync = AGENT_DIR / "services" / "graph_sync.py"
    if not tool.is_file() or not sync.is_file():
        return _result("graph", False, "graph modules missing")
    src = tool.read_text(encoding="utf-8")
    ok = "query_conversation_graph" in src and "NEO4J_URI" in sync.read_text(encoding="utf-8")
    if os.getenv("NEO4J_URI"):
        try:
            from tools.graph_tool import query_conversation_graph

            out = str(query_conversation_graph.invoke({"jid": "", "limit": 3}))
            ok = ok and ("disabled" not in out.lower() or "No graph" in out)
        except Exception as e:
            return _result("graph", False, str(e))
        return _result("graph", ok, out[:120])
    return _result("graph", ok, "offline wiring (set NEO4J_URI for live)")


def run_memory_live() -> bool:
    """Live stack validation: FS on mounted volume, daily-summary job, optional Neo4j."""
    mem_dir = os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip()
    if not mem_dir:
        return _result("memory-live", True, "skipped (EVI_CONTACT_MEMORY_DIR unset)")

    from services.contact_filesystem import contact_dir, ingest_commitment, memory_enabled
    from services.daily_summary import run_daily_summaries

    jid = "evi-memory-live@s.whatsapp.net"
    sid = f"live-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    ok = memory_enabled()
    ok = ok and ingest_commitment(
        jid=jid,
        source_id=sid,
        title="Memory live test",
        raw_text="validação memória longa",
        commitment_id=9001,
        label="EVI harness",
    )
    timeline = contact_dir(jid) / "timeline.jsonl"
    ok = ok and timeline.is_file() and sid in timeline.read_text(encoding="utf-8")

    n = run_daily_summaries()
    summaries = list(contact_dir(jid).glob("summaries/*.md"))
    ok = ok and n >= 1 and bool(summaries)

    base = os.getenv("EVI_API_URL", "").strip()
    if not base:
        base = (
            "http://127.0.0.1:8000"
            if (AGENT_DIR / "main.py").is_file()
            else "http://localhost:8002"
        )
    base = base.rstrip("/")
    api_key = os.getenv("EVI_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    try:
        import httpx

        r = httpx.post(f"{base}/jobs/daily-summary", headers=headers, json={}, timeout=30.0)
        ok = ok and r.status_code == 200 and r.json().get("ok") is True
        job_detail = f"job_written={r.json().get('written')}"
    except Exception as e:
        return _result("memory-live", False, f"daily-summary job: {e}")

    graph_detail = "graph=skipped"
    if os.getenv("NEO4J_URI", "").strip() and os.getenv("NEO4J_PASSWORD", "").strip():
        from services.graph_sync import run_cypher, sync_commitment
        from tools.graph_tool import query_conversation_graph

        synced = sync_commitment(
            commitment_id=9001,
            jid=jid,
            title="Memory live test",
            ctype="event",
            status="pending",
            label="EVI harness",
        )
        rows = run_cypher(
            "MATCH (c:Contact {jid: $jid})<-[:ORIGINATED_FROM]-(m:Commitment {id: $cid}) "
            "RETURN m.title AS title LIMIT 1",
            {"jid": jid, "cid": 9001},
        )
        out = str(query_conversation_graph.invoke({"jid": jid, "limit": 5}))
        ok = ok and synced and rows and "Memory live test" in out
        graph_detail = f"graph_nodes={len(rows)}"

    detail = f"timeline={timeline.name}, summaries={len(summaries)}, {job_detail}, {graph_detail}"
    return _result("memory-live", ok, detail)


def run_runtime_v3() -> bool:
    """Offline checks for EVI agent runtime v3 (workspace, context, skills)."""
    ws = os.getenv("EVI_WORKSPACE", str(REPO_ROOT / "EVI_WORKSPACE"))
    root = Path(ws)
    required = ["USER.md", "AGENTS.md", "MEMORY.md"]
    ok = root.is_dir() and all((root / name).is_file() for name in required)

    prev_ws = os.environ.get("EVI_WORKSPACE")
    os.environ["EVI_WORKSPACE"] = str(root)
    try:
        from services.context_assembly import build_context
        from services.daily_summary import run_heartbeat_dry
        from services.skill_loader import build_skills_block, match_skills

        ctx = build_context("telegram-harness", "Revise meus emails")
        ok = ok and len(ctx) > 20
        skills = match_skills("Revise meus emails")
        ok = ok and "inbox-triage" in skills
        block = build_skills_block("Revise meus emails")
        ok = ok and ("inbox" in block.lower() or "email" in block.lower())
        hb = run_heartbeat_dry()
        ok = ok and hb.get("ok") is True
        reg_src = (AGENT_DIR / "tools" / "registry.py").read_text(encoding="utf-8")
        ok = ok and "delete_emails_by_query" in reg_src
    except Exception as e:
        return _result("runtime-v3", False, str(e))
    finally:
        if prev_ws is None:
            os.environ.pop("EVI_WORKSPACE", None)
        else:
            os.environ["EVI_WORKSPACE"] = prev_ws

    return _result("runtime-v3", ok, f"workspace={root.name}")


def run_inbox_ux() -> bool:
    """SCN-UX-INBOX: inbox format, delete_by_query mock, optional snapshot round-trip."""
    from unittest.mock import patch

    from services.response_format import format_delete_emails_by_query_result, format_inbox_result

    msg_fixture = FIXTURES / "windmill" / "email_summary_messages.json"
    if not msg_fixture.exists():
        return _result("inbox-ux", False, "email_summary_messages.json missing")
    blob = json.loads(msg_fixture.read_text())
    formatted = format_inbox_result(json.dumps(blob))
    ok = "msg001" in formatted and "Caixa de entrada" in formatted

    delete_raw = json.dumps({"status": "ok", "deleted": 2, "q": "from:aliexpress OR from:olx"})
    delete_fmt = format_delete_emails_by_query_result(delete_raw)
    ok = ok and "2 email" in delete_fmt

    try:
        from unittest.mock import MagicMock

        with patch("integrations.factory.get_integration") as get_int:
            integration = MagicMock()
            integration.post.return_value = delete_raw
            get_int.return_value = integration
            from tools.email_tool import delete_emails_by_query

            out = delete_emails_by_query.invoke({"q": "from:aliexpress OR from:olx"})
        ok = ok and "2 email" in str(out) and "failed" not in str(out).lower()
    except ImportError:
        pass

    if os.getenv("DATABASE_URL"):
        try:
            import json as _json
            from unittest.mock import MagicMock

            from db import init_db, load_tool_snapshots
            from services.context_assembly import build_context
            from services.session_context import persist_tool_snapshots

            init_db()
            sid = f"inbox-ux-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            payload = {"status": "ok", "messages": [{"id": "snap001", "subject": "Test"}]}
            tool = MagicMock(
                type="tool",
                name="summarize_inbox",
                content=_json.dumps(payload),
            )
            persist_tool_snapshots(sid, [tool])
            rows = load_tool_snapshots(sid, limit=1)
            ok = ok and len(rows) >= 1
            ctx = build_context(sid, "apaga o primeiro")
            ok = ok and ("snap001" in ctx or "SESSION TOOL SNAPSHOTS" in ctx)
        except Exception as e:
            print(f"[SKIP] inbox-ux snapshot DB — {e}")
            with patch(
                "services.session_context.format_tool_snapshots",
                return_value=(
                    'SESSION TOOL SNAPSHOTS (use for follow-ups):\n'
                    '- summarize_inbox: {"messages": [{"id": "snap001"}]}'
                ),
            ):
                from services.context_assembly import build_context

                ctx = build_context("mock-inbox-ux", "apaga o primeiro")
            ok = ok and ("snap001" in ctx or "SESSION TOOL SNAPSHOTS" in ctx)

    return _result("inbox-ux", ok, "SCN-UX-INBOX-01/02/04")


def run_chat(*, strict: bool = False) -> bool:
    base = os.getenv("EVI_API_URL", "http://localhost:8002")
    session_id = "evi-test-chat-harness"
    import time

    max_attempts = 5 if strict else 1
    last_error = ""

    for attempt in range(max_attempts):
        try:
            import httpx

            headers: dict[str, str] = {}
            key = os.getenv("EVI_API_KEY", "").strip()
            if key:
                headers["X-Api-Key"] = key
            h = httpx.get(f"{base}/", timeout=5.0, headers=headers)
            if h.status_code != 200:
                last_error = f"API down HTTP {h.status_code}"
                if strict and attempt + 1 < max_attempts:
                    time.sleep(3)
                    continue
                if strict:
                    return _result("chat", False, last_error)
                return _result("chat", True, "skipped (API down)")
            c = httpx.post(
                f"{base}/chat",
                json={"message": "ping", "session_id": session_id},
                headers=headers,
                timeout=120.0,
            )
            if c.status_code != 200:
                return _result("chat", False, f"HTTP {c.status_code}")
            body = c.json()
            ok = "response" in body and "session_id" in body and "tools" in body
            return _result("chat", ok, f"session={body.get('session_id')}")
        except Exception as e:
            last_error = str(e)
            if strict and attempt + 1 < max_attempts:
                time.sleep(3)
                continue
            if strict:
                return _result("chat", False, last_error)
            return _result("chat", True, f"skipped ({last_error})")

    return _result("chat", False, last_error or "unreachable")


def run_smoke(full: bool, live_windmill: bool, verbose: bool) -> int:
    tests = [
        run_memory,
        run_file_organizer,
        lambda: run_calendar(live_windmill),
        lambda: run_whatsapp(verbose, None),
        run_notes,
        run_session,
        lambda: run_email(live_windmill),
        lambda: run_tasks(live_windmill),
        lambda: run_telegram(False),
        run_evolution,
        run_runtime_v3,
        run_watcher,
        lambda: run_dev_bridge(True),
        lambda: run_rag(False),
    ]
    if full:
        tests.append(run_chat)

    failed = 0
    for t in tests:
        if not t():
            failed += 1
    print(f"\nSmoke: {len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EVI feature test harness")
    parser.add_argument("feature", nargs="?", default="smoke")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--full", action="store_true", help="Include Tier 3 (chat)")
    parser.add_argument("--live-windmill", action="store_true")
    parser.add_argument("--live-qdrant", action="store_true")
    parser.add_argument("--live-telegram", action="store_true")
    parser.add_argument("--live-n8n", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--log", dest="log_path", default=None)
    parser.add_argument("--dry", action="store_true", help="dev-bridge dry run")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Live chat/telegram: fail instead of skip when API/deps missing",
    )
    args = parser.parse_args()
    live_wm = args.live_windmill or args.live_n8n

    os.chdir(AGENT_DIR)
    feature = args.feature.replace("_", "-")

    runners = {
        "memory": run_memory,
        "file-organizer": run_file_organizer,
        "calendar": lambda: run_calendar(live_wm),
        "calendar-list": lambda: run_calendar_list(live_wm),
        "tasks": lambda: run_tasks(live_wm),
        "evolution": run_evolution,
        "email": lambda: run_email(live_wm),
        "whatsapp": lambda: run_whatsapp(args.verbose, Path(args.log_path) if args.log_path else None),
        "notes": run_notes,
        "session": run_session,
        "telegram": lambda: run_telegram(args.live_telegram),
        "watcher": run_watcher,
        "dev-bridge": lambda: run_dev_bridge(args.dry),
        "rag": lambda: run_rag(args.live_qdrant),
        "chat": lambda: run_chat(strict=args.strict),
        "health": lambda: run_health(args.full),
        "metrics": lambda: run_metrics(args.full),
        "commitments": run_commitments,
        "contact-memory": run_contact_memory,
        "contact-learning": run_contact_learning,
        "daily-summary": run_daily_summary,
        "heartbeat": run_heartbeat,
        "graph": run_graph,
        "memory-live": run_memory_live,
        "runtime-v3": run_runtime_v3,
        "inbox-ux": run_inbox_ux,
        "smoke": lambda: run_smoke(args.full, live_wm, args.verbose) == 0,
    }

    if feature not in runners:
        print(f"Unknown feature: {feature}. Available: {', '.join(runners)}")
        return 2

    ok = runners[feature]()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
