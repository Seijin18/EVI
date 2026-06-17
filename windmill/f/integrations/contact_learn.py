"""Windmill cron: re-synthesize active WhatsApp contacts (no Evolution backfill)."""

import json
import os
import urllib.error
import urllib.request


def main() -> dict:
    base = os.environ.get("EVI_API_URL", "http://agent-api:8000").rstrip("/")
    api_key = os.environ.get("EVI_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    req = urllib.request.Request(
        f"{base}/jobs/contact-learn",
        data=b"{}",
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        return {"status": "error", "http": e.code, "detail": detail}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:400]}
    return {"status": "ok", **body}
