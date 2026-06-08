"""Unit tests for commitment_capture_notify (evi-commitment-capture-notify)."""

import os
import sys
from pathlib import Path
from unittest.mock import call, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.commitment_capture_notify import notify_commitment_captured  # noqa: E402


def test_no_jids_configured_is_noop():
    os.environ.pop("EVI_WHATSAPP_CONTROL_JIDS", None)
    with patch("services.commitment_capture_notify.send_whatsapp_text") as mock_send:
        notify_commitment_captured(1, "Reunião amanhã", "event")
    mock_send.assert_not_called()


def test_sends_to_each_control_jid():
    jids = "5511999990001@c.us,5511999990002@c.us"
    with patch.dict(os.environ, {"EVI_WHATSAPP_CONTROL_JIDS": jids}):
        with patch("services.commitment_capture_notify.send_whatsapp_text") as mock_send:
            mock_send.return_value = True
            notify_commitment_captured(7, "Almoço executivo", "event")

    assert mock_send.call_count == 2
    texts = [c.args[1] for c in mock_send.call_args_list]
    for t in texts:
        assert "#7" in t
        assert "Almoço executivo" in t
        assert "evento" in t


def test_sends_task_label():
    with patch.dict(os.environ, {"EVI_WHATSAPP_CONTROL_JIDS": "5511@c.us"}):
        with patch("services.commitment_capture_notify.send_whatsapp_text") as mock_send:
            mock_send.return_value = True
            notify_commitment_captured(3, "Comprar leite", "task")

    text = mock_send.call_args.args[1]
    assert "tarefa" in text
    assert "#3" in text


def test_send_failure_is_silent():
    with patch.dict(os.environ, {"EVI_WHATSAPP_CONTROL_JIDS": "5511@c.us"}):
        with patch(
            "services.commitment_capture_notify.send_whatsapp_text",
            side_effect=RuntimeError("network"),
        ):
            notify_commitment_captured(5, "Test", "event")


def test_title_truncated_at_80():
    long_title = "A" * 100
    with patch.dict(os.environ, {"EVI_WHATSAPP_CONTROL_JIDS": "5511@c.us"}):
        with patch("services.commitment_capture_notify.send_whatsapp_text") as mock_send:
            mock_send.return_value = True
            notify_commitment_captured(1, long_title, "event")

    text = mock_send.call_args.args[1]
    assert "A" * 80 in text
    assert "A" * 81 not in text


if __name__ == "__main__":
    test_no_jids_configured_is_noop()
    test_sends_to_each_control_jid()
    test_sends_task_label()
    test_send_failure_is_silent()
    test_title_truncated_at_80()
    print("ok")
