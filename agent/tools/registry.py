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
from tools.reply_debt_tools import dismiss_reply_debt, list_reply_debts
from tools.commitment_tools import (
    confirm_commitments,
    dismiss_commitments,
    list_pending_commitments,
    list_scheduled_today,
)
from tools.reminder_tools import (
    cancel_reminder,
    complete_reminder,
    create_reminder,
    list_reminders,
    snooze_reminder,
)
from tools.scheduled_task_tools import (
    cancel_scheduled_task,
    create_scheduled_task,
    list_scheduled_tasks,
    pause_scheduled_task,
    resume_scheduled_task,
)
from tools.task_tool import complete_tasks, create_task, list_tasks
from tools.graph_tool import query_conversation_graph
from tools.contact_tool import (
    get_whatsapp_contact_info,
    learn_whatsapp_contact,
    list_recent_whatsapp_messages,
    list_whatsapp_contacts,
    set_whatsapp_contact_name,
    summarize_whatsapp_messages,
)


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
        complete_tasks,
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
        set_whatsapp_contact_name,
        list_recent_whatsapp_messages,
        summarize_whatsapp_messages,
        create_reminder,
        list_reminders,
        cancel_reminder,
        snooze_reminder,
        complete_reminder,
        list_reply_debts,
        dismiss_reply_debt,
        create_scheduled_task,
        list_scheduled_tasks,
        cancel_scheduled_task,
        pause_scheduled_task,
        resume_scheduled_task,
    ]
