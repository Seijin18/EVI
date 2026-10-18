"""SCN-UX-02/03 — the Telegram sender never leaks model markers and falls back to plain text."""

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import send_result as sr  # noqa: E402
from services import telegram_notify as tn  # noqa: E402


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_400(description):
    body = json.dumps({"ok": False, "error_code": 400, "description": description}).encode()
    return urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(body))


@pytest.fixture
def sent(monkeypatch):
    """Records each POSTed payload; ``outcomes`` (list) scripts the responses."""
    monkeypatch.setattr(sr.time, "sleep", lambda _s: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    payloads, outcomes = [], []

    def fake(req, timeout=None):
        payloads.append(json.loads(req.data))
        out = outcomes.pop(0) if outcomes else _Resp()
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(sr.urllib.request, "urlopen", fake)
    fake.payloads, fake.outcomes = payloads, outcomes
    return fake


def test_marker_never_leaves_for_any_caller(sent, caplog):
    out = tn.send_telegram_message("oi «externo:email» Ana «/externo» tchau")
    assert bool(out) is True
    text = sent.payloads[0]["text"]
    assert "externo" not in text and "«" not in text
    assert text == "oi  Ana  tchau"
    warned = [r.getMessage() for r in caplog.records if "marker_leak" in r.getMessage()]
    assert len(warned) == 1 and "Ana" not in warned[0]  # logged once, without content


def test_clean_text_is_untouched_and_logs_nothing(sent, caplog):
    tn.send_telegram_message("Bom dia 👍 «aspas» normais")
    assert sent.payloads[0]["text"] == "Bom dia 👍 «aspas» normais"
    assert not [r for r in caplog.records if "marker_leak" in r.getMessage()]


def test_marker_only_text_is_treated_as_empty(sent):
    out = tn.send_telegram_message("«externo:x» «/externo»".replace(" ", ""))
    assert out.reason == "empty_text" and sent.payloads == []


def test_html_mode_sets_parse_mode(sent):
    assert tn.send_telegram_message("<b>oi</b>", parse_mode="HTML")
    assert sent.payloads[0]["parse_mode"] == "HTML"
    tn.send_telegram_message("oi")
    assert "parse_mode" not in sent.payloads[1]


def test_html_rejected_resends_plain_text(sent):
    sent.outcomes.append(_http_400("Bad Request: can't parse entities: Unsupported start tag"))
    out = tn.send_telegram_message('<b>Ana</b> · "x &lt;y&gt; &amp; z"', parse_mode="HTML")
    assert bool(out) is True
    first, second = sent.payloads
    assert first["parse_mode"] == "HTML"
    assert "parse_mode" not in second
    assert second["text"] == 'Ana · "x <y> & z"'


def test_other_400_is_not_retried_as_plain(sent):
    sent.outcomes.append(_http_400("Bad Request: chat not found"))
    out = tn.send_telegram_message("<b>oi</b>", parse_mode="HTML")
    assert bool(out) is False and out.reason == sr.HTTP_4XX
    assert len(sent.payloads) == 1


def test_plain_fallback_that_also_fails_reports_the_failure(sent):
    sent.outcomes += [_http_400("can't parse entities"), _http_400("Bad Request: chat not found")]
    out = tn.send_telegram_message("<b>oi</b>", parse_mode="HTML")
    assert bool(out) is False and len(sent.payloads) == 2


def test_html_to_plain_drops_only_known_tags_and_decodes_entities():
    assert tn.html_to_plain("<b>A</b> <i>b</i> <code>c</code> 1 &lt; 2 &amp; &lt;x&gt;") == "A b c 1 < 2 & <x>"


def test_long_html_is_cut_on_a_line_boundary(sent):
    text = "\n".join(f"<b>linha {i}</b> " + "x" * 90 for i in range(60))
    tn.send_telegram_message(text, parse_mode="HTML")
    sent_text = sent.payloads[0]["text"]
    assert len(sent_text) <= tn.MAX_LEN
    assert sent_text.count("<b>") == sent_text.count("</b>")


# --- inline keyboard (SCN-UX-06) ---------------------------------------------------

_KB = {"inline_keyboard": [[{"text": "1 ✅", "callback_data": "b1:20260101:1:ok"}]]}


class _OkResp(_Resp):
    def __init__(self, message_id):
        self._body = json.dumps({"ok": True, "result": {"message_id": message_id}}).encode()

    def read(self):
        return self._body


def test_reply_markup_is_sent_json_encoded_and_message_id_returned(sent):
    sent.outcomes.append(_OkResp(77))
    out = tn.send_telegram_message("oi", reply_markup=_KB)
    assert bool(out) is True and out.message_id == 77
    assert sent.payloads[0]["reply_markup"] == _KB


def test_no_markup_means_no_reply_markup_key_and_no_message_id_is_fine(sent):
    out = tn.send_telegram_message("oi")  # the fake response has no readable body
    assert bool(out) is True and out.message_id is None
    assert "reply_markup" not in sent.payloads[0]


def test_markup_rejected_resends_text_without_it(sent):
    sent.outcomes.append(_http_400("Bad Request: BUTTON_DATA_INVALID"))
    out = tn.send_telegram_message("<b>oi</b>", parse_mode="HTML", reply_markup=_KB)
    assert bool(out) is True
    first, second = sent.payloads
    assert first["reply_markup"] == _KB
    assert "reply_markup" not in second and second["parse_mode"] == "HTML"


def test_html_rejected_keeps_the_keyboard_on_the_plain_resend(sent):
    sent.outcomes.append(_http_400("Bad Request: can't parse entities"))
    out = tn.send_telegram_message("<b>oi</b>", parse_mode="HTML", reply_markup=_KB)
    assert bool(out) is True
    assert sent.payloads[1]["reply_markup"] == _KB and "parse_mode" not in sent.payloads[1]


def test_marker_guard_applies_to_text_not_markup(sent):
    tn.send_telegram_message("a «externo:x»b«/externo»", reply_markup=_KB)
    assert "«" not in sent.payloads[0]["text"] and sent.payloads[0]["reply_markup"] == _KB


def test_answer_callback_and_edit_reply_markup_post_to_the_bot_api(sent):
    assert tn.answer_callback("cq1", "Ok") is True
    assert sent.payloads[-1] == {"callback_query_id": "cq1", "text": "Ok"}
    assert tn.edit_reply_markup(123, 9, _KB) is True
    assert sent.payloads[-1] == {"chat_id": "123", "message_id": 9, "reply_markup": _KB}
    assert tn.edit_reply_markup(123, 9, None) is True
    assert sent.payloads[-1]["reply_markup"] == {"inline_keyboard": []}


def test_answer_callback_failure_is_false_not_raised(sent):
    sent.outcomes.append(_http_400("Bad Request: query is too old"))
    assert tn.answer_callback("cq1", "x") is False
    assert tn.answer_callback("", "x") is False
