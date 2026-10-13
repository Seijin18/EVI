"""SCN-SEC-05 / SCN-AUTH-01 — regression guards for the access surface."""

import sys
from pathlib import Path

import pytest
import yaml

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root / "agent"))

from fastapi.routing import APIRoute  # noqa: E402

import main  # noqa: E402
from auth import require_api_key_configured, verify_api_key  # noqa: E402

PUBLIC_PATHS = {"/", "/health"}


def _has_dep(dependant, call) -> bool:
    return any(
        d.call is call or _has_dep(d, call) for d in dependant.dependencies
    )


def test_every_non_public_route_requires_the_api_key():
    unguarded = [
        f"{sorted(r.methods)} {r.path}"
        for r in main.app.routes
        if isinstance(r, APIRoute)
        and r.path not in PUBLIC_PATHS
        and not _has_dep(r.dependant, verify_api_key)
    ]
    assert unguarded == [], f"routes without verify_api_key: {unguarded}"


def test_public_allowlist_routes_exist():
    paths = {r.path for r in main.app.routes if isinstance(r, APIRoute)}
    assert PUBLIC_PATHS <= paths


class _Loader(yaml.SafeLoader):
    """Compose merge tags (!reset / !override) are irrelevant here; read them as plain data."""


_Loader.add_multi_constructor(
    "!", lambda loader, suffix, node: loader.construct_sequence(node)
    if isinstance(node, yaml.SequenceNode)
    else loader.construct_scalar(node)
)


def _published(compose_file: Path) -> list[tuple[str, str]]:
    data = yaml.load(compose_file.read_text(encoding="utf-8"), Loader=_Loader) or {}
    out = []
    for name, svc in (data.get("services") or {}).items():
        for port in svc.get("ports") or []:
            out.append((name, str(port) if not isinstance(port, dict) else _fmt(port)))
    return out


def _fmt(port: dict) -> str:
    return f"{port.get('host_ip', '')}:{port.get('published', '')}:{port.get('target', '')}"


@pytest.mark.parametrize(
    "name", ["docker-compose.yml", "docker-compose.sim.yml", "docker-compose.smoke.yml"]
)
def test_published_ports_bind_loopback_only(name):
    path = _root / name
    if not path.exists():
        pytest.skip(f"{name} missing")
    bad = [(s, p) for s, p in _published(path) if not p.startswith("127.0.0.1:")]
    assert bad == [], f"{name} publishes on non-loopback: {bad}"
    if name == "docker-compose.yml":
        assert _published(path), "base compose should publish at least one port"


def test_startup_refuses_without_key(monkeypatch):
    monkeypatch.delenv("EVI_REQUIRE_API_KEY", raising=False)
    monkeypatch.setenv("EVI_API_KEY", "")
    with pytest.raises(RuntimeError, match="EVI_API_KEY"):
        require_api_key_configured()


def test_startup_refuses_short_key(monkeypatch):
    monkeypatch.delenv("EVI_REQUIRE_API_KEY", raising=False)
    monkeypatch.setenv("EVI_API_KEY", "short")
    with pytest.raises(RuntimeError):
        require_api_key_configured()


def test_startup_accepts_strong_key(monkeypatch):
    monkeypatch.delenv("EVI_REQUIRE_API_KEY", raising=False)
    monkeypatch.setenv("EVI_API_KEY", "k" * 32)
    require_api_key_configured()


def test_compose_images_are_pinned_not_latest_or_main():
    # SCN-SEC-06: every image carries an explicit version tag, or a digest.
    compose = yaml.safe_load((_root / "docker-compose.yml").read_text())
    images = {n: s["image"] for n, s in compose["services"].items() if s.get("image")}
    assert images, "no images found in docker-compose.yml"
    bad = []
    for name, image in images.items():
        if "@sha256:" in image:
            continue
        tag = image.rsplit("/", 1)[-1].partition(":")[2]
        if tag in ("", "latest", "main", "master"):
            bad.append(f"{name}={image}")
    assert bad == [], f"unpinned images (use a version tag or @sha256 digest): {bad}"
