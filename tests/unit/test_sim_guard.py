"""SCN-SIM-01: the evi-sim isolation guard aborts on any leak path."""
from pathlib import Path

from testing.sim.guard import check_config

ROOT = Path("/repo")


def _clean() -> dict:
    return {
        "name": "evi-sim",
        "services": {
            "agent-api": {
                "environment": {
                    "TELEGRAM_BOT_TOKEN": "sim-token",
                    "TELEGRAM_API_BASE": "http://fakes:18080",
                    "GEMINI_API_KEY": "key-with-googleapis.com-inside-is-exempt",
                },
                "volumes": [{"type": "volume", "source": "sim-clock", "target": "/sim"}],
            },
            "fakes": {
                "volumes": [{"type": "bind", "source": "/repo/windmill", "target": "/windmill"}],
            },
        },
    }


def test_clean_config_passes():
    assert check_config(_clean(), ROOT) == []


def test_wrong_project_name():
    cfg = _clean()
    cfg["name"] = "evi"
    assert any("project name" in p for p in check_config(cfg, ROOT))


def test_data_and_logs_binds_abort():
    for src in ("/repo/data", "/repo/data/postgres", "/repo/logs"):
        cfg = _clean()
        cfg["services"]["fakes"]["volumes"].append({"type": "bind", "source": src, "target": "/x"})
        problems = check_config(cfg, ROOT)
        assert any(src in p for p in problems), src


def test_forbidden_hosts_abort():
    for url, host in (
        ("https://api.telegram.org/bot1/x", "api.telegram.org"),
        ("https://www.googleapis.com/x", "googleapis.com"),
        ("http://evolution-api:8080", "evolution-api"),
    ):
        cfg = _clean()
        cfg["services"]["agent-api"]["environment"]["SOME_URL"] = url
        problems = check_config(cfg, ROOT)
        assert any("SOME_URL" in p and host in p for p in problems), url


def test_forbidden_host_in_list_style_env():
    cfg = _clean()
    cfg["services"]["agent-api"]["environment"] = ["TELEGRAM_BOT_TOKEN=sim-token", "X=http://evolution-api:8080"]
    assert any("X" in p for p in check_config(cfg, ROOT))


def test_real_telegram_token_aborts():
    cfg = _clean()
    cfg["services"]["agent-api"]["environment"]["TELEGRAM_BOT_TOKEN"] = "123:real"
    problems = check_config(cfg, ROOT)
    assert any("TELEGRAM_BOT_TOKEN" in p for p in problems)
    assert not any("123:real" in p for p in problems)
