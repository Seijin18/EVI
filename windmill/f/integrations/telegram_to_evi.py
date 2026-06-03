"""Windmill script: receive Telegram update, forward to EVI agent-api."""

import os

import requests


def main(update: dict):
    api_url = os.environ.get("EVI_AGENT_URL", "http://agent-api:8000/webhooks/telegram")
    api_key = os.environ.get("EVI_API_KEY", "")
    headers = {"X-Api-Key": api_key} if api_key else {}
    r = requests.post(api_url, json=update, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()
