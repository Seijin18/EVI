import os

import requests
from langchain_core.tools import tool


@tool
def summarize_inbox(max_messages: int = 10) -> str:
    """
    Request a short inbox summary from n8n (Gmail node). Secrets stay in n8n.
    """
    webhook_url = os.getenv("N8N_EMAIL_WEBHOOK_URL", "http://n8n:5678/webhook/email")
    payload = {"action": "summarize_inbox", "max_messages": max_messages}
    try:
        test_url = webhook_url.replace("webhook", "webhook-test")
        response = requests.post(test_url, json=payload, timeout=30)
        if response.status_code == 404:
            response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json() if response.content else {}
        summary = data.get("summary", response.text)
        return f"Inbox summary: {summary}"
    except Exception as e:
        return f"Failed to summarize inbox. Error: {e}"
