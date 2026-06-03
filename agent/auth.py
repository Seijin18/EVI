import os

from fastapi import Header, HTTPException


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional API key for remote webhooks (Telegram, etc.)."""
    expected = os.getenv("EVI_API_KEY", "")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
