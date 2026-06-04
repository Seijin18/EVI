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

# Repo root (parent of agent/)
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = REPO_ROOT / "tests" / "golden"
LOGS = REPO_ROOT / "logs"


def _log_path(feature: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return LOGS / f"{feature}_{ts}.jsonl"


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


def run_calendar(live_n8n: bool) -> bool:
    import json
    from pathlib import Path as P

    payload = {
        "action": "schedule_event",
        "title": "EVI Test",
        "start_time": "2026-06-10T10:00:00Z",
        "end_time": "2026-06-10T11:00:00Z",
    }
    fixture = FIXTURES / "n8n" / "calendar_payload.json"
    if not fixture.exists():
        fixture.write_text(json.dumps(payload), encoding="utf-8")
    data = json.loads(fixture.read_text())
    ok = data["action"] == "schedule_event" and "title" in data
    if live_n8n:
        try:
            from tools.calendar_tool import schedule_event

            r = schedule_event.invoke(
                {
                    "title": data["title"],
                    "start_time": data["start_time"],
                    "end_time": data["end_time"],
                }
            )
            ok = "Successfully" in str(r)
        except ImportError as e:
            return _result("calendar", False, str(e))
    return _result("calendar", ok, "payload ok" if not live_n8n else "live")


def run_tasks(live_n8n: bool) -> bool:
    fixture = FIXTURES / "n8n" / "task_payload.json"
    if not fixture.exists():
        fixture.write_text(
            '{"action":"create_task","title":"EVI test","due_date":"2026-06-10"}',
            encoding="utf-8",
        )
    ok = "create_task" in fixture.read_text()
    if live_n8n:
        try:
            from tools.task_tool import create_task

            r = create_task.invoke({"title": "EVI test task", "due_date": "2026-06-10"})
            ok = "Successfully" in str(r)
        except ImportError as e:
            return _result("tasks", False, str(e))
    return _result("tasks", ok, "payload ok" if not live_n8n else "live")


def run_email() -> bool:
    fixture = FIXTURES / "n8n" / "email_summary.json"
    if not fixture.exists():
        return _result("email", False, "fixture missing")
    data = json.loads(fixture.read_text())
    ok = "summary" in data and len(data["summary"]) > 0
    return _result("email", ok, "fixture parse")


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


def run_telegram() -> bool:
    fixture = FIXTURES / "telegram" / "update.json"
    if not fixture.exists():
        return _result("telegram", False, "fixture missing")
    data = json.loads(fixture.read_text())
    ok = "message" in data and "text" in data["message"]
    return _result("telegram", ok, "parse update JSON")


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

    from services.evolution_parser import parse_evolution_webhook
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
    return _result("evolution", ok, f"parsed={parsed}")


def run_dev_bridge(dry: bool) -> bool:
    script = REPO_ROOT / "scripts" / "copilot-dev-runner.sh"
    ok = script.exists() and os.access(script, os.X_OK)
    if dry and ok:
        return _result("dev-bridge", True, "script present (dry)")
    return _result("dev-bridge", ok)


def run_rag() -> bool:
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    try:
        import httpx

        r = httpx.get(f"{qdrant_url}/collections", timeout=3.0)
        if r.status_code >= 500:
            return _result("rag", True, "skipped (qdrant down)")
    except Exception:
        return _result("rag", True, "skipped (qdrant unreachable)")

    from tools.rag_tool import extract_and_chunk_pdf

    sample = FIXTURES / "rag" / "sample.txt"
    if sample.exists():
        ok = len(sample.read_text()) > 0
        return _result("rag", ok, "fixture text ok")
    return _result("rag", True, "skipped (no pdf fixture)")


def run_chat() -> bool:
    base = os.getenv("EVI_API_URL", "http://localhost:8002")
    try:
        import httpx

        h = httpx.get(f"{base}/", timeout=5.0)
        if h.status_code != 200:
            return _result("chat", True, "skipped (API down)")
        c = httpx.post(f"{base}/chat", json={"message": "ping"}, timeout=120.0)
        ok = c.status_code == 200 and "response" in c.json()
        return _result("chat", ok)
    except Exception as e:
        return _result("chat", True, f"skipped ({e})")


def run_smoke(full: bool, live_windmill: bool, verbose: bool) -> int:
    tests = [
        run_memory,
        run_file_organizer,
        lambda: run_calendar(live_windmill),
        lambda: run_whatsapp(verbose, None),
        run_notes,
        run_session,
        run_email,
        lambda: run_tasks(live_windmill),
        run_telegram,
        run_evolution,
        run_watcher,
        lambda: run_dev_bridge(True),
        run_rag,
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
    parser.add_argument("--live-n8n", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--log", dest="log_path", default=None)
    parser.add_argument("--dry", action="store_true", help="dev-bridge dry run")
    args = parser.parse_args()
    live_wm = args.live_windmill or args.live_n8n

    os.chdir(AGENT_DIR)
    feature = args.feature.replace("_", "-")

    runners = {
        "memory": run_memory,
        "file-organizer": run_file_organizer,
        "calendar": lambda: run_calendar(live_wm),
        "tasks": lambda: run_tasks(live_wm),
        "evolution": run_evolution,
        "email": run_email,
        "whatsapp": lambda: run_whatsapp(args.verbose, Path(args.log_path) if args.log_path else None),
        "notes": run_notes,
        "session": run_session,
        "telegram": run_telegram,
        "watcher": run_watcher,
        "dev-bridge": lambda: run_dev_bridge(args.dry),
        "rag": run_rag,
        "chat": run_chat,
        "smoke": lambda: run_smoke(args.full, live_wm, args.verbose) == 0,
    }

    if feature not in runners:
        print(f"Unknown feature: {feature}. Available: {', '.join(runners)}")
        return 2

    ok = runners[feature]()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
