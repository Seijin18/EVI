"""Unit tests for agent/integrations factory and messaging factory."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


def test_get_integration_default_is_windmill():
    os.environ.pop("EVI_ORCHESTRATOR", None)
    # Reset lru_cache
    from integrations import factory as fac
    fac.get_integration.cache_clear()
    client = fac.get_integration()
    from integrations.windmill import WindmillClient
    assert isinstance(client, WindmillClient)


def test_get_integration_unknown_raises():
    from integrations import factory as fac
    fac.get_integration.cache_clear()
    with patch.dict(os.environ, {"EVI_ORCHESTRATOR": "unknown_backend"}):
        fac.get_integration.cache_clear()
        try:
            fac.get_integration()
            assert False, "should raise"
        except ValueError as e:
            assert "unknown_backend" in str(e)
    fac.get_integration.cache_clear()


def test_get_messaging_default_is_evolution():
    os.environ.pop("EVI_WHATSAPP_PROVIDER", None)
    from messaging import factory as mfac
    mfac.get_messaging.cache_clear()
    client = mfac.get_messaging()
    from messaging.evolution import EvolutionClient
    assert isinstance(client, EvolutionClient)
    mfac.get_messaging.cache_clear()


def test_windmill_client_post_delegates():
    from integrations.windmill import WindmillClient
    wc = WindmillClient()
    with patch("integrations.windmill._windmill_post", return_value='{"status":"created"}') as mock_pw:
        result = wc.post("schedule_event", {"title": "test"}, timeout=30)
    mock_pw.assert_called_once()
    assert "created" in result


def test_evolution_client_format_reply():
    from messaging.evolution import EvolutionClient
    ec = EvolutionClient()
    assert ec.format_reply("Hello").startswith("[EVI]")
    assert ec.is_bot_message("[EVI] test") is True
    assert ec.is_bot_message("normal message") is False


if __name__ == "__main__":
    test_get_integration_default_is_windmill()
    test_get_messaging_default_is_evolution()
    test_windmill_client_post_delegates()
    test_evolution_client_format_reply()
    print("ok")
