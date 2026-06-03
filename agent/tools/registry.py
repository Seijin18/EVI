"""Single registry for LangGraph tools — avoid drift between main.py and graph.py."""

from tools.calendar_tool import schedule_event
from tools.email_tool import summarize_inbox
from tools.file_organizer import organize_inbox
from tools.note_manager import save_note_manual
from tools.rag_tool import ingest_university_pdf, query_university_notes
from tools.task_tool import create_task


def get_all_tools():
    return [
        organize_inbox,
        ingest_university_pdf,
        query_university_notes,
        schedule_event,
        save_note_manual,
        create_task,
        summarize_inbox,
    ]
