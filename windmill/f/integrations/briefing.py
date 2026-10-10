"""Windmill cron: trigger the EVI morning briefing via agent-api.

Schedule: daily 07:00 local (kind=morning); optional 21:00 (kind=evening).
The job collects four sources in parallel (Gmail can take up to 180 s).
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


def main(kind: str = "morning", force: bool = False) -> dict:
    base = os.environ.get("EVI_API_URL", "http://agent-api:8000").rstrip("/")
    api_key = os.environ.get("EVI_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    query = urllib.parse.urlencode({"kind": kind, "force": "true" if force else "false"})
    req = urllib.request.Request(
        f"{base}/jobs/briefing?{query}",
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
