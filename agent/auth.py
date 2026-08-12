import os

from fastapi import Header, HTTPException

_TRUTHY = ("1", "true", "yes")


def api_key_expected() -> str:
    return os.getenv("EVI_API_KEY", "").strip()


def api_key_required() -> bool:
    """When true, starting without EVI_API_KEY is a hard error."""
    return os.getenv("EVI_REQUIRE_API_KEY", "false").strip().lower() in _TRUTHY


def require_api_key_configured() -> None:
    """Startup gate: refuse to serve unauthenticated when enforcement is on."""
    if api_key_required() and not api_key_expected():
        raise RuntimeError(
            "EVI_REQUIRE_API_KEY=true but EVI_API_KEY is empty — refusing to start "
            "with unauthenticated routes. Set EVI_API_KEY (e.g. `openssl rand -hex 32`) "
            "or set EVI_REQUIRE_API_KEY=false for local-only use."
        )


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Gate mutating routes. No-op while EVI_API_KEY is unset (local default)."""
    expected = api_key_expected()
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
