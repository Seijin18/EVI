"""Single registry for LangGraph tools — avoid drift between main.py and graph.py."""

from tools.calendar_tool import list_calendar_events, list_calendars, schedule_event
from tools.email_tool import delete_emails, delete_emails_by_query, summarize_inbox
from tools.file_organizer import organize_inbox
from tools.note_manager import save_note_manual
from tools.rag_tool import (
    ingest_university_folder,
    ingest_university_pdf,
    query_university_notes,
)
from tools.commitment_tools import (
    confirm_commitments,
    dismiss_commitments,
    list_pending_commitments,
    list_scheduled_today,
)
from tools.task_tool import create_task, list_tasks
from tools.graph_tool import query_conversation_graph
from tools.contact_tool import (
    get_whatsapp_contact_info,
    learn_whatsapp_contact,
    list_whatsapp_contacts,
)
from tools.dev_bridge_tool import propose_dev_task_tool, status_dev_jobs_tool


def get_all_tools():
    return [
        organize_inbox,
        ingest_university_pdf,
        ingest_university_folder,
        query_university_notes,
        schedule_event,
        list_calendar_events,
        list_calendars,
        save_note_manual,
        create_task,
        list_tasks,
        summarize_inbox,
        delete_emails,
        delete_emails_by_query,
        list_pending_commitments,
        list_scheduled_today,
        confirm_commitments,
        dismiss_commitments,
        query_conversation_graph,
        list_whatsapp_contacts,
        get_whatsapp_contact_info,
        learn_whatsapp_contact,
        propose_dev_task_tool,
        status_dev_jobs_tool,
    ]
