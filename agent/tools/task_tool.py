import os

import requests
from langchain_core.tools import tool


@tool
def create_task(title: str, due_date: str = "", notes: str = "") -> str:
    """
    Create a Google Task via n8n webhook.

    Args:
        title: Task title.
        due_date: Due date YYYY-MM-DD (optional).
        notes: Extra notes (optional).
    """
    webhook_url = os.getenv("N8N_TASKS_WEBHOOK_URL", "http://n8n:5678/webhook/tasks")
    payload = {
        "action": "create_task",
        "title": title,
        "due_date": due_date,
        "notes": notes,
    }
    try:
        test_url = webhook_url.replace("webhook", "webhook-test")
        response = requests.post(test_url, json=payload, timeout=10)
        if response.status_code == 404:
            response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return f"Successfully passed task '{title}' to n8n."
    except Exception as e:
        return f"Failed to create task. Error: {e}"
