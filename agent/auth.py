import hmac
import logging
import os

from fastapi import Header, HTTPException

_TRUTHY = ("1", "true", "yes")
MIN_KEY_LENGTH = 16
_log = logging.getLogger(__name__)


def api_key_expected() -> str:
    return os.getenv("EVI_API_KEY", "").strip()


def api_key_required() -> bool:
    """Enforcement is ON unless EVI_REQUIRE_API_KEY is explicitly set to a falsy value."""
    return os.getenv("EVI_REQUIRE_API_KEY", "true").strip().lower() in _TRUTHY


def require_api_key_configured() -> None:
    """Startup gate: refuse to serve unauthenticated when enforcement is on."""
    key = api_key_expected()
    if not api_key_required():
        _log.warning(
            "EVI_REQUIRE_API_KEY=false: API routes are %s — use only for local-only runs",
            "UNAUTHENTICATED" if not key else "authenticated only because EVI_API_KEY is set",
        )
        return
    if len(key) < MIN_KEY_LENGTH:
        raise RuntimeError(
            f"EVI_API_KEY is empty or shorter than {MIN_KEY_LENGTH} chars — refusing to start "
            "with weak/missing API auth. Set EVI_API_KEY (e.g. `openssl rand -hex 32`) "
            "or opt out explicitly with EVI_REQUIRE_API_KEY=false for local-only use."
        )


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Gate routes. With no key configured it is a no-op only when enforcement is
    explicitly disabled; otherwise it fails closed."""
    expected = api_key_expected()
    if not expected:
        if api_key_required():
            raise HTTPException(status_code=401, detail="Invalid API key")
        return
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
