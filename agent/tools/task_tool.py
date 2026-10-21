import os
import unicodedata

from langchain_core.tools import tool
from services.write_guard import guarded_write

from integrations.factory import get_integration
from services.response_format import (
    _parse_json_blob,
    format_list_tasks_result,
    format_task_result,
)
from services.tool_result import ToolResult, parse_windmill_result


def _gtasks_resource() -> str:
    gtasks = os.getenv("WINDMILL_GTASKS_RESOURCE", "gtasks").strip()
    if gtasks.startswith("$var:"):
        gtasks = gtasks[5:]
    if gtasks and not gtasks.startswith("$res:"):
        gtasks = f"$res:{gtasks}"
    return gtasks


def create_task_result(
    title: str, due_date: str = "", notes: str = ""
) -> ToolResult:
    """Structured form of `create_task` — `confirm_commitments` gates a DB write on it."""
    payload = {
        "title": title,
        "due_date": due_date,
        "notes": notes,
        "gtasks": _gtasks_resource(),
    }
    raw = get_integration().post("create_task", payload, timeout=180, wait_result=True)
    out = parse_windmill_result(
        raw,
        action=f"criar a tarefa «{title}»",
        resource_env="WINDMILL_GTASKS_RESOURCE",
        tool="create_task",
    )
    if not out.ok:
        return out
    # Prose unchanged: format_task_result still renders the success wording the
    # tests and the model already expect.
    return ToolResult.success(format_task_result(title, raw), data=out.data)


@tool
@guarded_write
def create_task(title: str, due_date: str = "", notes: str = "") -> str:
    """
    Create a Google Task via the configured orchestration backend.
    """
    return str(create_task_result(title, due_date, notes))


@tool
def list_tasks(max_results: int = 25, show_completed: bool = False) -> str:
    """
    List open Google Tasks from the default task list.

    Args:
        max_results: Maximum tasks to return (default 25).
        show_completed: Include completed tasks (default false).
    """
    payload = {
        "gtasks": _gtasks_resource(),
        "max_results": max_results,
        "show_completed": show_completed,
    }
    result = get_integration().post("list_tasks", payload, timeout=120, wait_result=True)
    return format_list_tasks_result(result)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def _hits(task: dict, terms: list[str]) -> bool:
    title, tid = _norm(task.get("title", "")), (task.get("id") or "").casefold()
    for term in terms:
        t = _norm(term).strip("[]")
        if t and (t in title or (len(t) >= 6 and tid.startswith(t))):
            return True
    return False


def complete_tasks_result(
    match: list[str], all_open: bool, except_match: list[str]
) -> ToolResult:
    """Resolve targets in code from the open tasks, then complete each one."""
    match = [m for m in (match or []) if m and m.strip()]
    except_match = [m for m in (except_match or []) if m and m.strip()]
    if not match and not all_open:
        return ToolResult.failure(
            "Nada foi concluído: diga quais tarefas finalizar (parte do título) "
            "ou peça para finalizar todas as abertas.",
            reason="invalid_request",
        )
    gtasks = _gtasks_resource()
    integ = get_integration()
    raw = integ.post(
        "list_tasks", {"gtasks": gtasks, "max_results": 100, "show_completed": False},
        timeout=120, wait_result=True,
    )
    listed = parse_windmill_result(
        raw, action="listar tarefas", resource_env="WINDMILL_GTASKS_RESOURCE",
        tool="complete_tasks",
    )
    if not listed.ok:
        return listed
    blob = _parse_json_blob(raw) or {}
    open_tasks = [t for t in blob.get("tasks") or [] if t.get("id")]

    targets = [t for t in open_tasks if all_open or _hits(t, match)]
    kept = [t for t in targets if _hits(t, except_match)]
    targets = [t for t in targets if t not in kept]
    unmatched = [m for m in match if not any(_hits(t, [m]) for t in open_tasks)]

    done: list[str] = []
    failed: list[str] = []
    for t in targets:
        out = parse_windmill_result(
            integ.post(
                "complete_task", {"task_id": t["id"], "gtasks": gtasks},
                timeout=120, wait_result=True,
            ),
            action=f"concluir a tarefa «{t.get('title', '')}»",
            resource_env="WINDMILL_GTASKS_RESOURCE", tool="complete_tasks",
        )
        (done if out.ok else failed).append(t.get("title") or "(sem título)")

    data = {
        "completed": done, "failed": failed,
        "kept": [t.get("title") for t in kept], "unmatched": unmatched,
    }
    lines = [f"Tarefas concluídas ({len(done)}):" if done else "Nenhuma tarefa foi concluída."]
    lines += [f"• {title}" for title in done]
    if kept:
        lines.append(f"Mantidas abertas ({len(kept)}): " + "; ".join(data["kept"]))
    if failed:
        lines.append("Falharam: " + "; ".join(failed))
    if unmatched:
        lines.append("Sem correspondência: " + "; ".join(unmatched))
    if failed:
        return ToolResult.failure("\n".join(lines), data=data)
    return ToolResult.success("\n".join(lines), data=data)


@tool
@guarded_write
def complete_tasks(
    match: list[str] | None = None,
    all_open: bool = False,
    except_match: list[str] | None = None,
) -> str:
    """
    Mark open Google Tasks as completed. Only on an explicit user request.

    Args:
        match: Parts of task titles (or the short [id] shown by list_tasks) to finish.
        all_open: Finish every open task (use with except_match to spare some).
        except_match: Parts of titles that must stay open.
    """
    return str(complete_tasks_result(match or [], all_open, except_match or []))
