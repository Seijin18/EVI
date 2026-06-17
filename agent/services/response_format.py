"""Human-readable formatting for tool and Windmill responses (Telegram/WhatsApp/chat)."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def format_windmill_oauth_error(raw: str, action: str, resource_env: str) -> str | None:
    lower = raw.lower()
    resource = os.getenv(resource_env, "").strip()
    # Prefer resource path mentioned in Windmill error over stale env in message text
    m = re.search(r"Resource\s+(u/[^\s:]+)", raw, re.I)
    if m:
        resource = m.group(1)
    if "insufficient" in lower and ("scope" in lower or "permission" in lower):
        return (
            f"Não foi possível {action}: OAuth Gmail sem permissão suficiente "
            f"(resource «{resource or '?'}»). "
            "No Windmill → Resources → reconecte o Gmail com escopos "
            "gmail.readonly (ler) e gmail.modify (apagar)."
        )
    if "not found" in lower and "resource" in lower:
        return (
            f"Não foi possível {action}: recurso Windmill «{resource or '?'}» não encontrado. "
            "Abra Windmill → Resources, conecte o OAuth (Gmail) e "
            f"atualize {resource_env} no .env; depois recrie o container: "
            "docker compose up -d --force-recreate agent-api"
        )
    if "refreshing token" in lower or "invalid_" in lower:
        return (
            f"Não foi possível {action}: credencial OAuth expirada ({resource or '?'}). "
            "Reconecte o resource no Windmill → Resources."
        )
    return None


def _parse_json_blob(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        text = m.group(0) if m else text
    try:
        blob = json.loads(text)
        return blob if isinstance(blob, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def format_task_result(title: str, raw: str) -> str:
    if "failed" in raw.lower():
        hint = format_windmill_oauth_error(raw, "criar a tarefa", "WINDMILL_GTASKS_RESOURCE")
        return hint or f"Não foi possível criar a tarefa «{title}». {raw[:300]}"

    blob = _parse_json_blob(raw)
    if blob and blob.get("status") == "error":
        detail = str(blob.get("detail", raw))[:200]
        return f"Erro ao criar tarefa «{title}»: {detail}"

    if blob and blob.get("status") == "created":
        due = (blob.get("due_date") or "").strip()
        due_line = f"Prazo: {due}" if due else "Sem prazo definido"
        return f"Tarefa criada: «{title}»\n{due_line}"

    if '"status":"created"' in raw or '"status": "created"' in raw:
        return f"Tarefa criada: «{title}»"

    return f"Tarefa «{title}» — resposta: {raw[:200]}"


def format_inbox_result(raw: str) -> str:
    if "failed" in raw.lower():
        hint = format_windmill_oauth_error(raw, "acessar o Gmail", "WINDMILL_GMAIL_RESOURCE")
        return hint or f"Não foi possível acessar o Gmail. {raw[:350]}"

    blob = _parse_json_blob(raw)
    if blob and blob.get("status") == "error":
        detail = str(blob.get("detail", ""))[:500]
        http = blob.get("http_status")
        hint = format_windmill_oauth_error(detail, "acessar o Gmail", "WINDMILL_GMAIL_RESOURCE")
        if hint:
            return hint
        prefix = f"Erro Gmail (HTTP {http}): " if http else "Erro Gmail: "
        return f"{prefix}{detail[:250]}"

    if blob and blob.get("status") == "ok":
        count = blob.get("count", 0)
        messages = blob.get("messages") or []
        if messages:
            lines = [f"Caixa de entrada ({count} recentes):"]
            for msg in messages:
                mid = msg.get("id", "")
                subj = msg.get("subject", "(sem assunto)")
                sender = msg.get("from", "")
                tag = f"[{mid}] " if mid else ""
                lines.append(f"• {tag}{subj}")
                if sender:
                    lines.append(f"  De: {sender}")
            lines.append("Para apagar: «apagar email <id>» ou use delete_emails.")
            return "\n".join(lines)
        summary = str(blob.get("summary") or "").strip()
        if summary:
            # Legacy Windmill summary: parse "- [id] subject — sender" lines
            parsed_lines = []
            for line in summary.splitlines():
                line = line.strip()
                if line.startswith("- ["):
                    m = re.match(r"^- \[([^\]]+)\]\s*(.+?)(?:\s+—\s+(.+))?$", line)
                    if m:
                        parsed_lines.append(
                            f"• [{m.group(1)}] {m.group(2)}"
                            + (f"\n  De: {m.group(3)}" if m.group(3) else "")
                        )
                    else:
                        parsed_lines.append(f"• {line.lstrip('- ')}")
                elif line.startswith("- "):
                    parsed_lines.append(f"• {line[2:]}")
            if parsed_lines:
                lines = [f"Caixa de entrada ({count} recentes):"] + parsed_lines
                lines.append(
                    "Para apagar: «apagar email <id>», delete_emails_by_query, ou peça ao assistente."
                )
                return "\n".join(lines)
            return summary
        return "Caixa de entrada vazia (nenhuma mensagem recente)."

    if '"summary"' in raw:
        blob = _parse_json_blob(raw.split("Inbox summary:")[-1].strip() if "Inbox summary:" in raw else raw)
        if blob:
            return format_inbox_result(json.dumps(blob))

    return f"Resposta do Gmail: {raw[:400]}"


def format_delete_emails_result(raw: str, *, count: int | None = None) -> str:
    if "failed" in raw.lower():
        hint = format_windmill_oauth_error(raw, "apagar emails", "WINDMILL_GMAIL_RESOURCE")
        return hint or f"Não foi possível apagar os emails. {raw[:300]}"

    blob = _parse_json_blob(raw)
    if blob and blob.get("status") == "ok":
        n = blob.get("deleted", count or 0)
        return f"{n} email(s) movido(s) para a lixeira."

    if blob and blob.get("status") == "error":
        return f"Erro ao apagar: {str(blob.get('detail', raw))[:250]}"

    return raw[:300]


def format_delete_emails_by_query_result(raw: str) -> str:
    if "failed" in raw.lower():
        hint = format_windmill_oauth_error(raw, "apagar emails", "WINDMILL_GMAIL_RESOURCE")
        return hint or f"Não foi possível apagar os emails. {raw[:300]}"

    blob = _parse_json_blob(raw)
    if blob and blob.get("status") == "ok":
        n = blob.get("deleted", 0)
        q = blob.get("q", "")
        q_bit = f" (query: {q})" if q else ""
        return f"{n} email(s) movido(s) para a lixeira{q_bit}."

    if blob and blob.get("status") == "error":
        return f"Erro ao apagar: {str(blob.get('detail', raw))[:250]}"

    return raw[:300]


def format_confirm_results(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ": failed" in line or "failed —" in line:
            lines.append(f"❌ {line}")
        elif "created" in line.lower() or "criado" in line.lower() or "Agendado" in line:
            # strip raw JSON tail from task results
            if "#" in line and ":" in line:
                prefix, _, rest = line.partition(":")
                rest = rest.strip()
                if rest.startswith("Task '") and "{" in rest:
                    title_m = re.search(r"Task '([^']+)' created", rest)
                    title = title_m.group(1) if title_m else "item"
                    lines.append(f"✅ {prefix}: tarefa «{title}» criada")
                elif "Evento '" in rest or "criado no Google Calendar" in rest:
                    lines.append(f"✅ {line}")
                else:
                    lines.append(f"✅ {line}")
            else:
                lines.append(f"✅ {line}")
        else:
            lines.append(line)
    return "\n".join(lines) if lines else raw
