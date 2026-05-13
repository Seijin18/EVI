from langchain_core.tools import tool
import requests
import os


@tool
def schedule_event(
    title: str, start_time: str, end_time: str, description: str = ""
) -> str:
    """
    Schedules an event in the user's Google Calendar via n8n webhook.

    Args:
        title (str): Title of the event.
        start_time (str): Start time in ISO 8601 format (e.g. '2026-05-12T14:00:00Z').
        end_time (str): End time in ISO 8601 format (e.g. '2026-05-12T15:00:00Z').
        description (str, optional): Description of the event.
    """
    # Grab the URL from .env, default to the local docker network name
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/calendar")

    payload = {
        "action": "schedule_event",
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
    }

    try:
        # To help capture it in the n8n UI right now, we first try the test webhook
        webhook_test_url = webhook_url.replace("webhook", "webhook-test")
        response = requests.post(webhook_test_url, json=payload, timeout=10)

        # If test URL is not active (404), fallback to the production webhook URL
        if response.status_code == 404:
            response = requests.post(webhook_url, json=payload, timeout=10)

        response.raise_for_status()
        return f"Successfully passed the event '{title}' to n8n to be scheduled!"
    except Exception as e:
        return f"Failed to schedule event. Error: {str(e)}"
