"""Unit tests for Telegram handler (SCN-TG-01/02)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.telegram_handler import process_telegram_update  # noqa: E402

@pytest.fixture(autouse=True)
def _owner_chat(monkeypatch):
    """The allowlist fails closed without TELEGRAM_CHAT_ID (F16); fixtures use these ids."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "933619568")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1,7")


_DIRECT_OFF = patch.dict(os.environ, {"EVI_DIRECT_HANDLERS": "false"}, clear=False)
_DIRECT_ON = patch.dict(os.environ, {"EVI_DIRECT_HANDLERS": "true"}, clear=False)


def test_skips_non_text():
    out = process_telegram_update({"message": {"chat": {"id": 1}}}, lambda m, s: {})
    assert out["skipped"] == "no text"


def test_processes_text_and_sends():
    update = {
        "message": {
            "text": "olá",
            "chat": {"id": 933619568, "type": "private"},
        }
    }

    def fake_chat(msg, session_id):
        assert msg == "olá"
        assert session_id == "telegram-933619568"
        return {"response": "Oi!", "tools": []}

    with _DIRECT_OFF:
        with (
            patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
            patch("services.telegram_handler._persist_turn") as persist,
            patch("services.telegram_handler.log_telegram_turn") as audit,
        ):
            out = process_telegram_update(update, fake_chat)
    assert out["telegram_sent"] is True
    assert out["response"] == "Oi!"
    assert out.get("llm") is True
    send.assert_called_once()
    persist.assert_called_once_with("telegram-933619568", "olá", "Oi!")
    audit.assert_called_once()


def test_llm_first_inbox_when_direct_handlers_off():
    update = {
        "message": {
            "text": "Revise meus emails",
            "chat": {"id": 933619568, "type": "private"},
        }
    }
    invoked = []

    def fake_chat(msg, session_id):
        invoked.append((msg, session_id))
        return {
            "response": "3 emails recentes.",
            "tools": [{"kind": "call", "tool": "summarize_inbox"}],
        }

    with _DIRECT_OFF:
        with patch("services.telegram_handler.try_direct_email") as mock_email:
            with patch("services.telegram_handler.try_direct_review") as mock_review:
                with (
                    patch("services.telegram_handler.send_telegram_message", return_value=True),
                    patch("services.telegram_handler._persist_turn"),
                    patch("services.telegram_handler.log_telegram_turn"),
                ):
                    out = process_telegram_update(update, fake_chat)
    mock_email.assert_not_called()
    mock_review.assert_not_called()
    assert invoked == [("Revise meus emails", "telegram-933619568")]
    assert out.get("llm") is True
    assert out["response"] == "3 emails recentes."


def test_direct_email_when_handlers_enabled():
    update = {
        "message": {
            "text": "Revise meus emails",
            "chat": {"id": 933619568, "type": "private"},
        }
    }

    with _DIRECT_ON:
        with patch("services.telegram_handler.try_direct_review", return_value=None):
            with patch("services.telegram_handler.try_direct_schedule", return_value=None):
                with patch("services.telegram_handler.try_direct_task", return_value=None):
                    with patch(
                        "services.telegram_handler.try_direct_email",
                        return_value="Inbox summary",
                    ) as mock_email:
                        with (
                            patch("services.telegram_handler.send_telegram_message", return_value=True),
                            patch("services.telegram_handler._persist_turn"),
                            patch("services.telegram_handler.log_telegram_turn"),
                        ):
                            out = process_telegram_update(update, lambda m, s: {})
    mock_email.assert_called_once()
    assert out.get("email_direct") is True


def test_processes_gemini_content_blocks():
    update = {
        "message": {
            "text": "oi",
            "chat": {"id": 933619568, "type": "private"},
        }
    }
    gemini_response = [
        {"type": "text", "text": "Olá! Como posso ajudar?", "extras": {"signature": "x"}},
    ]

    def fake_chat(msg, session_id):
        return {"response": gemini_response}

    with _DIRECT_OFF, patch.dict(os.environ, {"EVI_LLM_PROVIDER": "gemini"}):
        with (
            patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
            patch("services.telegram_handler._persist_turn"),
            patch("services.telegram_handler.log_telegram_turn"),
        ):
            out = process_telegram_update(update, fake_chat)
    assert out["telegram_sent"] is True
    assert out["response"] == "Olá! Como posso ajudar?"
    send.assert_called_once_with("Olá! Como posso ajudar?", chat_id=933619568)


if __name__ == "__main__":
    test_skips_non_text()
    test_processes_text_and_sends()
    test_llm_first_inbox_when_direct_handlers_off()
    test_direct_email_when_handlers_enabled()
    test_processes_gemini_content_blocks()
    print("ok")


# --- voice (evi-voice-input SCN-VOICE-01/03) ---------------------------------

import pytest  # noqa: E402

from services import transcribe as _tr  # noqa: E402

_VOICE = {"message": {"chat": {"id": 7}, "voice": {"file_id": "F1", "duration": 5, "file_size": 1000}}}


@pytest.fixture
def voice_env(monkeypatch):
    monkeypatch.setenv("EVI_VOICE_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET:TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "7")
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    with (
        patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
        patch("services.telegram_handler._persist_turn"),
        patch("services.telegram_handler.log_telegram_turn"),
    ):
        yield send


def test_voice_disabled_replies_without_download(voice_env, monkeypatch):
    monkeypatch.setenv("EVI_VOICE_ENABLED", "false")
    with patch("services.telegram_poller.download_file") as dl:
        out = process_telegram_update(_VOICE, lambda m, s, **k: {})
    dl.assert_not_called()
    voice_env.assert_called_once()
    assert voice_env.call_args.args[0] == _tr.MSG_DISABLED
    assert out["telegram_sent"] is True


def test_voice_too_long_no_download_no_transcribe(voice_env, monkeypatch):
    monkeypatch.setenv("EVI_VOICE_MAX_SECONDS", "300")
    update = {"message": {"chat": {"id": 7}, "voice": {"file_id": "F", "duration": 600}}}
    with (
        patch("services.telegram_poller.download_file") as dl,
        patch("services.transcribe.transcribe") as tx,
    ):
        process_telegram_update(update, lambda m, s, **k: {})
    dl.assert_not_called()
    tx.assert_not_called()
    assert "passa de" in voice_env.call_args.args[0]


def test_voice_ok_invokes_chat_with_voice_kind_and_echo(voice_env):
    seen = {}

    def chat(msg, sid, input_kind="text"):
        seen.update(msg=msg, sid=sid, kind=input_kind)
        return {"response": "Feito.", "tools": []}

    with (
        patch("services.telegram_poller.get_file_path", return_value="voice/a.oga"),
        patch("services.telegram_poller.download_file", return_value=b"OGG"),
        patch(
            "services.transcribe.transcribe",
            return_value=_tr.TranscriptionResult(True, "marca dentista"),
        ) as tx,
    ):
        out = process_telegram_update(_VOICE, chat)
    assert seen == {"msg": "marca dentista", "sid": "telegram-7", "kind": "voice"}
    assert tx.call_args.args[1] == "audio/ogg"
    sent = voice_env.call_args.args[0]
    assert sent.startswith("🎙️ Entendi: marca dentista\n\n")
    assert sent.endswith("Feito.")
    assert out["response"] == sent


def test_voice_echo_truncated_to_200(voice_env):
    with (
        patch("services.telegram_poller.get_file_path", return_value="p"),
        patch("services.telegram_poller.download_file", return_value=b"x"),
        patch("services.transcribe.transcribe", return_value=_tr.TranscriptionResult(True, "a" * 500)),
    ):
        process_telegram_update(_VOICE, lambda m, s, input_kind="text": {"response": "ok"})
    first = voice_env.call_args.args[0].split("\n\n")[0]
    assert len(first) <= len("🎙️ Entendi: ") + 201


def test_voice_download_failure_visible_and_token_not_leaked(voice_env, caplog):
    with patch(
        "services.telegram_poller.get_file_path",
        side_effect=RuntimeError("getFile failed: boom <token>"),
    ):
        out = process_telegram_update(_VOICE, lambda m, s, **k: {})
    assert voice_env.call_args.args[0] == _tr.MSG_FAILED
    assert "SECRET:TOKEN" not in str(out) and "SECRET:TOKEN" not in caplog.text


def test_voice_transcription_failure_uses_user_message(voice_env):
    with (
        patch("services.telegram_poller.get_file_path", return_value="p"),
        patch("services.telegram_poller.download_file", return_value=b"x"),
        patch(
            "services.transcribe.transcribe",
            return_value=_tr.TranscriptionResult(False, "", _tr.REASON_EMPTY),
        ),
    ):
        process_telegram_update(_VOICE, lambda m, s, **k: {})
    assert voice_env.call_args.args[0] == _tr.MSG_EMPTY


def test_voice_audio_uses_own_mime_and_other_chat_skipped(voice_env, monkeypatch):
    update = {"message": {"chat": {"id": 7}, "audio": {"file_id": "A", "mime_type": "audio/mpeg"}}}
    with (
        patch("services.telegram_poller.get_file_path", return_value="p"),
        patch("services.telegram_poller.download_file", return_value=b"x"),
        patch("services.transcribe.transcribe", return_value=_tr.TranscriptionResult(True, "oi")) as tx,
    ):
        process_telegram_update(update, lambda m, s, input_kind="text": {"response": "ok"})
        assert tx.call_args.args[1] == "audio/mpeg"
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        out = process_telegram_update(update, lambda m, s, input_kind="text": {})
    assert out["skipped"] == "chat not allowed"


# --- SCN-INJ-00: only the owner's chat reaches the agent ---------------------


def _text(chat_id, text="olá"):
    return {"message": {"text": text, "chat": {"id": chat_id}}}


def _run_guard(update, env, monkeypatch):
    import services.telegram_handler as th

    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    calls = []

    def chat(m, s, **k):
        calls.append(m)
        return {"response": "ok"}

    with (
        _DIRECT_OFF,
        patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
        patch("services.telegram_handler._persist_turn"),
        patch("services.telegram_handler.log_telegram_turn"),
    ):
        out = th.process_telegram_update(update, chat)
    return out, calls, send


def test_stranger_text_ignored(monkeypatch):
    out, calls, send = _run_guard(_text(666), {"TELEGRAM_CHAT_ID": "111"}, monkeypatch)
    assert out == {"ok": True, "skipped": "chat not allowed"}
    assert calls == []
    send.assert_not_called()


def test_stranger_command_ignored(monkeypatch):
    out, calls, send = _run_guard(_text(666, "/ajuda"), {"TELEGRAM_CHAT_ID": "111"}, monkeypatch)
    assert out["skipped"] == "chat not allowed"
    assert calls == []
    send.assert_not_called()


def test_owner_chat_allowed(monkeypatch):
    out, calls, send = _run_guard(_text(111), {"TELEGRAM_CHAT_ID": " 111 "}, monkeypatch)
    assert calls == ["olá"]
    send.assert_called_once()


def test_extra_allowed_chat_id(monkeypatch):
    env = {"TELEGRAM_CHAT_ID": "111", "TELEGRAM_ALLOWED_CHAT_IDS": "222, 333"}
    out, calls, _ = _run_guard(_text(333), env, monkeypatch)
    assert calls == ["olá"]
    out, calls, _ = _run_guard(_text(444), env, monkeypatch)
    assert out["skipped"] == "chat not allowed" and calls == []


def test_unset_owner_fails_closed_and_warns_once(monkeypatch, caplog):
    import services.telegram_handler as th

    monkeypatch.setattr(th, "_warned_open", False)
    with caplog.at_level("WARNING", logger="services.telegram_handler"):
        out, calls, send = _run_guard(_text(5), {}, monkeypatch)
        _run_guard(_text(6), {}, monkeypatch)
    assert calls == [] and out["skipped"] == "chat not allowed"
    send.assert_not_called()
    warns = [r for r in caplog.records if "TELEGRAM_CHAT_ID not set" in r.getMessage()]
    assert len(warns) == 1


def test_disallowed_log_has_chat_id_not_text(monkeypatch, caplog):
    with caplog.at_level("INFO", logger="services.telegram_handler"):
        _run_guard(_text(666, "segredo-xyz"), {"TELEGRAM_CHAT_ID": "111"}, monkeypatch)
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "666" in joined and "segredo-xyz" not in joined


def test_chat_none_does_not_crash():
    with _DIRECT_OFF:
        with (
            patch("services.telegram_handler.send_telegram_message", return_value=True),
            patch("services.telegram_handler._persist_turn"),
            patch("services.telegram_handler.log_telegram_turn"),
        ):
            process_telegram_update(
                {"message": {"text": "oi", "chat": None}},
                lambda m, s: {"response": "ok", "tools": []},
            )


def test_forwarded_message_is_flagged_to_invoke_chat():
    seen = {}

    def fake_chat(msg, session_id, forwarded=False):
        seen["forwarded"] = forwarded
        return {"response": "ok", "tools": []}

    update = {
        "message": {"text": "sim", "chat": {"id": 1}, "forward_origin": {"type": "user"}}
    }
    with _DIRECT_OFF:
        with (
            patch("services.telegram_handler.send_telegram_message", return_value=True),
            patch("services.telegram_handler._persist_turn"),
            patch("services.telegram_handler.log_telegram_turn"),
        ):
            process_telegram_update(update, fake_chat)
    assert seen["forwarded"] is True


def test_scn_ux_02_direct_list_sends_clean_text_and_persists_marked(monkeypatch):
    """The user gets no «externo» marker; the session memory keeps the delimited text."""
    from services.untrusted import has_marker

    rows = [{"id": 31, "title": "Mandar a modelagem", "type": "promise",
             "source_label": "Eliana", "event_date": "2026-10-16"}]
    update = {"message": {"text": "listar compromissos pendentes",
                          "chat": {"id": 933619568, "type": "private"}}}
    sent, persisted = [], []
    monkeypatch.setattr("tools.commitment_tools.pending_rows", lambda limit=20: rows)
    with _DIRECT_ON:
        with (
            patch("services.telegram_handler.send_telegram_message",
                  side_effect=lambda text, chat_id=None, **kw: sent.append(text) or True),
            patch("services.telegram_handler._persist_turn",
                  side_effect=lambda sid, user, assistant: persisted.append(assistant)),
            patch("services.telegram_handler.log_telegram_turn"),
        ):
            out = process_telegram_update(update, lambda m, s: {})
    assert out.get("review_direct") is True
    assert sent and not has_marker(sent[0]) and "Eliana · Mandar a modelagem" in sent[0]
    assert persisted and has_marker(persisted[0])


# --- briefing buttons (SCN-UX-07/08/09) -----------------------------------------------

import json  # noqa: E402
from datetime import datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

TODAY = datetime(2026, 10, 12, 7, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
OWNER = 933619568


@pytest.fixture
def buttons(monkeypatch):
    import db
    from services import briefing, telegram_notify as tn, turn_log

    st = SimpleNamespace(
        snaps=[{"tool_name": "morning_briefing", "created_at": "2026-10-12T10:00:00+00:00", "payload": {
            "kind": "morning", "day": "2026-10-12", "message_id": 77,
            "refs": {"1": "reply_debt:5511@s.whatsapp.net", "2": "commitment:12", "3": "name_prompt:9@lid"},
        }}],
        acked=[], commitments={12: "event"}, status={}, ignored=[], feedback=None, replied=[],
        answers=[], edits=[], turns=[], confirmed=[], promises=[],
    )
    monkeypatch.setattr(briefing, "now_local", lambda: TODAY)
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "load_tool_snapshots", lambda sid, limit=5: list(st.snaps))
    monkeypatch.setattr(db, "save_tool_snapshot",
                        lambda sid, name, payload: st.snaps.insert(0, {"tool_name": name, "payload": payload}))
    monkeypatch.setattr(db, "get_briefing", lambda day, kind: {"feedback": st.feedback})
    monkeypatch.setattr(db, "set_briefing_feedback", lambda day, kind, v: setattr(st, "feedback", v) or True)
    monkeypatch.setattr(db, "mark_briefing_replied", lambda day, kind: st.replied.append((str(day), kind)) or True)
    monkeypatch.setattr(db, "acknowledge", lambda jid, ts: st.acked.append(jid))
    monkeypatch.setattr(db, "set_name_prompt_ignored", lambda jid, until: st.ignored.append(jid))
    monkeypatch.setattr(db, "list_pending_commitments", lambda limit=50, **kw: [
        {"id": i, "type": t} for i, t in st.commitments.items() if i not in st.status])
    monkeypatch.setattr(db, "update_commitment_status",
                        lambda i, status, confirmed_via=None: st.status.setdefault(i, status) == status
                        if i not in st.status else False)
    monkeypatch.setattr(db, "finish_pending_promise",
                        lambda i, s, via: st.status.setdefault(i, s) and st.promises.append(i) or True)
    monkeypatch.setattr("tools.reply_debt_tools._debt_names", lambda jids: ["Ana" for _ in jids])
    import tools.commitment_tools as ct

    def _confirm(ids, via):
        st.confirmed.append((list(ids), via))
        for i in ids:
            st.status[i] = "scheduled"
        return ["ok"]

    monkeypatch.setattr(ct, "confirm_commitment_ids", _confirm)
    monkeypatch.setattr(tn, "answer_callback", lambda qid, text="": st.answers.append(text) or True)
    monkeypatch.setattr(tn, "edit_reply_markup", lambda c, m, kb: st.edits.append((c, m, kb)) or True)
    monkeypatch.setattr(turn_log, "record_turn", lambda collector, **kw: st.turns.append((collector, kw)))
    import llm

    monkeypatch.setattr(llm, "build_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM")))
    return st


def _tap(data, chat=OWNER, sender=OWNER, message_id=77):
    return {"update_id": 1, "callback_query": {
        "id": "cq1", "from": {"id": sender}, "data": data,
        "message": {"message_id": message_id, "chat": {"id": chat, "type": "private"}}}}


def _go(update):
    def no_chat(*a, **k):
        raise AssertionError("button taps never reach the LLM")

    return process_telegram_update(update, no_chat)


def _rows(edit):
    return [[b["text"] for b in row] for row in edit[2]["inline_keyboard"]]


def test_scn_ux_07_tap_ok_on_debt_acknowledges_and_edits_markup(buttons):
    out = _go(_tap("b1:20261012:m:1:ok"))
    assert out["callback"] == "done"
    assert buttons.acked == ["5511@s.whatsapp.net"]
    assert buttons.answers == ["Ok, marcado como respondido."]
    assert buttons.replied == [("2026-10-12", "morning")]
    assert _rows(buttons.edits[-1]) == [["2 ✅", "2 ✖"], ["3 ✖ ignorar"], ["👍", "👎"]]  # item 1 gone
    assert buttons.edits[-1][:2] == (OWNER, 77)
    collector, kw = buttons.turns[-1]
    assert collector.input_kind == "button" and "5511" not in kw["user_text"]


def test_scn_ux_08_old_day_changes_nothing_and_says_old(buttons):
    out = _go(_tap("b1:20261011:m:1:ok"))
    assert out["callback"] == "stale" and buttons.answers == ["Esse briefing é antigo — use o de hoje."]
    assert not buttons.acked and not buttons.edits and not buttons.replied


def test_scn_ux_08_other_message_than_the_current_briefing_is_old(buttons):
    _go(_tap("b1:20261012:m:1:ok", message_id=70))
    assert not buttons.acked and buttons.answers == ["Esse briefing é antigo — use o de hoje."]


def test_scn_ux_08_foreign_chat_or_sender_changes_nothing(buttons):
    for update in (_tap("b1:20261012:m:1:ok", chat=555), _tap("b1:20261012:m:1:ok", sender=555)):
        assert _go(update)["skipped"] == "chat not allowed"
    assert not buttons.acked and not buttons.answers and not buttons.edits and not buttons.replied


@pytest.mark.parametrize("data", [None, "", "x", "b1:20261012:m:1:rm", "b1:20261012:m:99:ok", "b1:20261012:m:2:ok ",
                                  "b1:20261012:m:3:ok"])  # 3 = name prompt: only ✖ exists
def test_malformed_or_impossible_data_answers_error_and_changes_nothing(buttons, data):
    out = _go(_tap(data))
    assert out["callback"] == "invalid" and "Não consegui" in buttons.answers[0]
    assert not buttons.acked and not buttons.status and not buttons.ignored and not buttons.replied


def test_second_tap_on_same_item_is_idempotent(buttons):
    _go(_tap("b1:20261012:m:1:ok"))
    out = _go(_tap("b1:20261012:m:1:ok"))
    assert out["callback"] == "already" and buttons.answers[-1] == "Já estava feito."
    assert buttons.acked == ["5511@s.whatsapp.net"]  # no second action


def test_commitment_ok_confirms_with_button_provenance_and_no_dismisses(buttons):
    _go(_tap("b1:20261012:m:2:ok"))
    assert buttons.confirmed == [([12], "telegram_button")]
    assert buttons.answers == ["Ok, confirmado."]


def test_commitment_no_dismisses_and_second_tap_changes_nothing(buttons):
    _go(_tap("b1:20261012:m:2:no"))
    assert buttons.status == {12: "dismissed"} and not buttons.confirmed
    _go(_tap("b1:20261012:m:2:ok"))
    assert buttons.status == {12: "dismissed"} and buttons.answers[-1] == "Já estava feito."


def test_promise_ok_marks_it_done(buttons):
    buttons.commitments[12] = "promise"
    _go(_tap("b1:20261012:m:2:ok"))
    assert buttons.promises == [12] and not buttons.confirmed


def test_name_prompt_no_ignores_conversation(buttons):
    _go(_tap("b1:20261012:m:3:no"))
    assert buttons.ignored == ["9@lid"]


def test_scn_ux_09_feedback_last_tap_wins_and_keeps_row(buttons):
    _go(_tap("b1:20261012:m:0:dn"))
    assert buttons.feedback == "down" and _rows(buttons.edits[-1])[-1] == ["👍", "👎 ✓"]
    _go(_tap("b1:20261012:m:0:up"))
    assert buttons.feedback == "up" and _rows(buttons.edits[-1])[-1] == ["👍 ✓", "👎"]
    assert buttons.answers == ["Obrigado!", "Obrigado!"]


# --- guards: kind in the button, fail-closed message id, lock, webhook ---------------------


def _snap(kind, mid, refs, done=None):
    payload = {"kind": kind, "day": "2026-10-12", "message_id": mid, "refs": refs}
    if done is not None:
        payload["done"] = done
    return {"tool_name": "morning_briefing", "created_at": "2026-10-12T10:00:00+00:00", "payload": payload}


def test_snapshot_without_message_id_fails_closed(buttons):
    buttons.snaps[0]["payload"].pop("message_id")
    out = _go(_tap("b1:20261012:m:1:ok"))
    assert out["callback"] == "stale" and not buttons.acked and not buttons.edits and not buttons.replied


def test_callback_without_message_id_fails_closed(buttons):
    out = _go(_tap("b1:20261012:m:1:ok", message_id=None))
    assert out["callback"] == "stale" and not buttons.acked


def test_morning_keyboard_never_resolves_against_the_evening_snapshot(buttons):
    # an evening briefing went out later the same day; item 1 there is a commitment
    buttons.snaps.insert(0, _snap("evening", 88, {"1": "commitment:12"}))
    out = _go(_tap("b1:20261012:m:1:ok", message_id=77))  # morning keyboard
    assert out["callback"] == "done" and buttons.acked == ["5511@s.whatsapp.net"]
    assert not buttons.confirmed and not buttons.status
    # a morning button on the evening message, or an evening button on the morning message
    for data, mid in (("b1:20261012:m:1:ok", 88), ("b1:20261012:e:1:ok", 77)):
        assert _go(_tap(data, message_id=mid))["callback"] == "stale"
    assert not buttons.confirmed and not buttons.status
    # the evening keyboard resolves the evening numbers
    assert _go(_tap("b1:20261012:e:1:ok", message_id=88))["callback"] == "done"
    assert buttons.confirmed == [([12], "telegram_button")]


def test_commitment_no_longer_pending_is_already_resolved_without_side_effects(buttons):
    buttons.status[12] = "dismissed"
    n_snaps = len(buttons.snaps)
    out = _go(_tap("b1:20261012:m:2:ok"))
    assert out["callback"] == "already" and buttons.answers == ["Já estava resolvido."]
    assert len(buttons.snaps) == n_snaps and not buttons.replied and not buttons.turns
    assert not buttons.confirmed


def test_concurrent_taps_do_not_lose_each_others_done_entries(buttons, monkeypatch):
    import threading
    import time

    import tools.reply_debt_tools as rdt

    monkeypatch.setattr(rdt, "acknowledge_debts", lambda jids: time.sleep(0.15))  # widen the race
    buttons.snaps[0]["payload"]["refs"] = {"1": "reply_debt:a@s.whatsapp.net", "2": "reply_debt:b@s.whatsapp.net"}
    threads = [threading.Thread(target=_go, args=(_tap(f"b1:20261012:m:{n}:ok"),)) for n in (1, 2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert buttons.snaps[0]["payload"]["done"] == [1, 2]


def test_webhook_forwards_callback_query_to_the_button_handler(monkeypatch):
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    import main

    monkeypatch.setenv("EVI_API_KEY", "k")
    main.app_state.graph = MagicMock()
    seen = []
    monkeypatch.setattr("services.telegram_handler.handle_briefing_callback",
                        lambda cq: seen.append(cq) or {"ok": True, "callback": "done"})
    body = {"update_id": 1, "callback_query": {"id": "c", "data": "b1:20261012:m:1:ok"}}
    r = TestClient(main.app).post("/webhooks/telegram", json=body, headers={"X-Api-Key": "k"})
    assert r.status_code == 200 and r.json()["callback"] == "done"
    assert seen == [body["callback_query"]]


# --- evening "🔔 lembrar amanhã 9h" (SCN-TIP-03) ----------------------------------------------


@pytest.fixture
def evening(buttons, monkeypatch):
    import db
    import tools.reminder_tools as rt

    buttons.created = []
    buttons.snaps.insert(0, {"tool_name": "morning_briefing", "created_at": "2026-10-12T22:00:00+00:00", "payload": {
        "kind": "evening", "day": "2026-10-12", "message_id": 88,
        "refs": {"1": "task:t1", "2": "commitment:12"},
        "rm": {"1": "«externo:briefing» Pagar boleto «/externo»", "2": "«externo:briefing» Enviar X «/externo»"},
    }})
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER))
    monkeypatch.setattr(rt, "now_local", lambda: TODAY.replace(hour=21))
    monkeypatch.setattr(db, "create_reminder",
                        lambda text, due, rep, chat, src, anchor_day=None: buttons.created.append((text, due, rep, chat, src)) or 1)
    return buttons


def _due(local_day, hour=9):
    return datetime(2026, 10, local_day, hour, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def test_scn_tip_03_tap_bell_creates_reminder_for_tomorrow_9h_with_the_title(evening):
    out = _go(_tap("b1:20261012:e:1:rm", message_id=88))
    assert out["callback"] == "done" and evening.answers == ["🔔 Vou te lembrar amanhã às 9h."]
    [(text, due, rep, chat, src)] = evening.created
    assert text == "Pagar boleto" and due == _due(13) and rep is None and src == "telegram"
    assert evening.snaps[0]["payload"]["rm_done"] == [1]
    assert [r for r in _rows(evening.edits[-1]) if r[0].startswith("1 ")] == []  # its 🔔 is gone
    assert ["2 ✅", "2 ✖", "2 🔔"] in _rows(evening.edits[-1])
    assert evening.turns and evening.replied == [("2026-10-12", "evening")]


def test_bell_second_tap_is_idempotent(evening):
    _go(_tap("b1:20261012:e:1:rm", message_id=88))
    out = _go(_tap("b1:20261012:e:1:rm", message_id=88))
    assert out["callback"] == "already" and evening.answers[-1] == "Já estava agendado."
    assert len(evening.created) == 1


def test_bell_stale_or_foreign_changes_nothing(evening):
    assert _go(_tap("b1:20261011:e:1:rm", message_id=88))["callback"] == "stale"  # old day
    assert _go(_tap("b1:20261012:e:1:rm", message_id=77))["callback"] == "stale"  # other message
    assert _go(_tap("b1:20261012:e:1:rm", message_id=88, chat=999, sender=999))["skipped"] == "chat not allowed"
    assert not evening.created


def test_bell_on_item_without_reminder_or_on_morning_snapshot_is_invalid(evening):
    assert _go(_tap("b1:20261012:e:3:rm", message_id=88))["callback"] == "invalid"
    assert _go(_tap("b1:20261012:m:1:rm", message_id=77))["callback"] == "invalid"  # morning: no `rm`
    assert not evening.created


def test_bell_reminders_disabled_answers_without_marking_done(evening, monkeypatch):
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    out = _go(_tap("b1:20261012:e:1:rm", message_id=88))
    assert out["callback"] == "error" and "desativados" in evening.answers[-1]
    assert "rm_done" not in evening.snaps[0]["payload"] and not evening.created


def test_bell_does_not_disturb_ok_no_done_list(evening):
    _go(_tap("b1:20261012:e:2:rm", message_id=88))
    assert _go(_tap("b1:20261012:e:2:ok", message_id=88))["callback"] == "done"
    assert evening.confirmed == [([12], "telegram_button")]
    assert evening.snaps[0]["payload"]["done"] == [2] and evening.snaps[0]["payload"]["rm_done"] == [2]


def _say(text, monkeypatch):
    sent = []
    monkeypatch.setattr("services.telegram_handler.send_telegram_message",
                        lambda text, chat_id=None, **kw: sent.append(text) or True)
    monkeypatch.setattr("services.telegram_handler._persist_turn", lambda *a: None)
    monkeypatch.setattr("services.telegram_handler.log_telegram_turn", lambda *a, **k: None)

    def no_chat(*a, **k):
        raise AssertionError("deterministic reply never reaches the LLM")

    out = process_telegram_update({"message": {"chat": {"id": OWNER}, "text": text}}, no_chat)
    return out, sent


def test_scn_tip_03_text_reply_lembra_n_creates_the_reminder(evening, monkeypatch):
    out, sent = _say("lembra 1", monkeypatch)
    assert out.get("briefing_reminder") is True
    [(text, due, *_)] = evening.created
    assert text == "Pagar boleto" and due == _due(13)
    assert sent == ["🔔 Vou te lembrar amanhã às 9h."]
    _, sent = _say("Lembra 1.", monkeypatch)  # again: idempotent
    assert len(evening.created) == 1 and sent == ["Já estava agendado."]


def test_text_reply_not_claimed_without_matching_item(evening, monkeypatch):
    from services.telegram_handler import try_reminder_reply

    assert try_reminder_reply("lembra 9", f"telegram-{OWNER}") is None  # no such item
    assert try_reminder_reply("me lembra 1 de algo", f"telegram-{OWNER}") is None
    evening.snaps.insert(0, _snap("morning", 99, {"1": "task:t1"}))  # latest *evening* still decides
    assert try_reminder_reply("lembra 1", f"telegram-{OWNER}") == "🔔 Vou te lembrar amanhã às 9h."
    assert len(evening.created) == 1


# --- Monday "⏳ Esperando resposta deles" (evi-awaiting-their-reply, SCN-AWAIT-03/04) ------------

BRUNO = "5511900000001@s.whatsapp.net"
OUT_AT = "2026-10-08T14:30:00.123456+00:00"


@pytest.fixture
def awaiting(buttons, monkeypatch):
    import db
    import tools.reminder_tools as rt

    buttons.created, buttons.dismissed, buttons.sent_to_contact = [], [], []
    buttons.snaps.insert(0, {"tool_name": "morning_briefing", "created_at": "2026-10-12T10:00:00+00:00", "payload": {
        "kind": "morning", "day": "2026-10-12", "message_id": 66,
        "refs": {"1": f"awaiting:{BRUNO}", "2": "reply_debt:5511@s.whatsapp.net"},
        "aw": {"1": OUT_AT},
        "rm": {"1": "«externo:briefing» Cobrar Bruno: consegue me mandar o contrato? «/externo»"},
    }})
    monkeypatch.setattr(db, "dismiss_awaiting", lambda jid, out_at: buttons.dismissed.append((jid, out_at)))
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OWNER))
    monkeypatch.setattr(rt, "now_local", lambda: TODAY.replace(hour=8))
    monkeypatch.setattr(db, "create_reminder",
                        lambda text, due, rep, chat, src, anchor_day=None: buttons.created.append((text, due, rep, chat, src)) or 1)

    def _never(*a, **k):
        buttons.sent_to_contact.append((a, k))
        raise AssertionError("the EVI never writes to the contact")

    from services import evolution_client

    monkeypatch.setattr(evolution_client, "send_whatsapp_text", _never)
    monkeypatch.setattr(evolution_client._client, "send_text", _never)
    return buttons


def test_scn_await_03_tap_no_dismisses_that_exact_message_and_hides_the_button(awaiting):
    out = _go(_tap("b1:20261012:m:1:no", message_id=66))
    assert out["callback"] == "done" and awaiting.answers == ["Ok, não pergunto mais sobre essa mensagem."]
    [(jid, out_at)] = awaiting.dismissed
    assert jid == BRUNO and out_at.isoformat() == OUT_AT  # the exact outbound message
    assert awaiting.snaps[0]["payload"]["done"] == [1]
    assert ["1 🔔"] in _rows(awaiting.edits[-1]) and ["1 ✖", "1 🔔"] not in _rows(awaiting.edits[-1])
    assert not awaiting.sent_to_contact and not awaiting.acked  # not a "respondido"


def test_awaiting_no_is_idempotent(awaiting):
    _go(_tap("b1:20261012:m:1:no", message_id=66))
    out = _go(_tap("b1:20261012:m:1:no", message_id=66))
    assert out["callback"] == "already" and len(awaiting.dismissed) == 1


def test_awaiting_ok_button_is_invalid(awaiting):
    assert _go(_tap("b1:20261012:m:1:ok", message_id=66))["callback"] == "invalid"
    assert not awaiting.dismissed


def test_scn_await_04_tap_bell_creates_reminder_tomorrow_9h_and_sends_nothing(awaiting):
    out = _go(_tap("b1:20261012:m:1:rm", message_id=66))
    assert out["callback"] == "done" and awaiting.answers == ["🔔 Vou te lembrar amanhã às 9h."]
    [(text, due, rep, chat, src)] = awaiting.created
    assert text == "Cobrar Bruno: consegue me mandar o contrato?" and rep is None and src == "telegram"
    assert due == datetime(2026, 10, 13, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert awaiting.snaps[0]["payload"]["rm_done"] == [1] and not awaiting.sent_to_contact
    assert not awaiting.dismissed  # a reminder does not dismiss
    out = _go(_tap("b1:20261012:m:1:rm", message_id=66))
    assert out["callback"] == "already" and len(awaiting.created) == 1


def test_bell_on_a_morning_item_that_is_not_awaiting_stays_invalid(awaiting):
    awaiting.snaps[0]["payload"]["rm"]["2"] = "«externo:briefing» x «/externo»"
    assert _go(_tap("b1:20261012:m:2:rm", message_id=66))["callback"] == "invalid"
    assert not awaiting.created


def test_text_reply_ignora_n_dismisses_and_is_idempotent(awaiting, monkeypatch):
    out, sent = _say("ignora 1", monkeypatch)
    assert out.get("awaiting_ignore") is True and sent == ["Ok, não pergunto mais sobre essa mensagem."]
    [(jid, out_at)] = awaiting.dismissed
    assert jid == BRUNO and out_at.isoformat() == OUT_AT
    _, sent = _say("Ignora 1", monkeypatch)
    assert len(awaiting.dismissed) == 1 and sent == ["Já estava feito."]
    assert not awaiting.sent_to_contact


def test_text_reply_ignora_is_not_claimed_for_other_items(awaiting):
    from services.telegram_handler import try_awaiting_ignore_reply

    session = f"telegram-{OWNER}"
    assert try_awaiting_ignore_reply("ignora 2", session) is None  # a reply debt
    assert try_awaiting_ignore_reply("ignora 9", session) is None
    assert try_awaiting_ignore_reply("ignora 1 por favor", session) is None
    assert not awaiting.dismissed


def test_text_reply_lembra_n_creates_the_awaiting_reminder(awaiting, monkeypatch):
    out, sent = _say("lembra 1", monkeypatch)
    assert out.get("briefing_reminder") is True and sent == ["🔔 Vou te lembrar amanhã às 9h."]
    [(text, due, *_)] = awaiting.created
    assert text.startswith("Cobrar Bruno: ") and due.day == 13 and due.hour == 9
    _, sent = _say("lembra 1", monkeypatch)
    assert len(awaiting.created) == 1 and sent == ["Já estava agendado."]
    assert not awaiting.sent_to_contact


# --- SCN-PREC-08: 👍/👎 reactions on a briefing message are feedback --------------------------


def _react(emojis, chat=OWNER, message_id=77):
    return {"update_id": 2, "message_reaction": {
        "chat": {"id": chat, "type": "private"}, "message_id": message_id, "user": {"id": chat},
        "old_reaction": [], "new_reaction": [{"type": "emoji", "emoji": e} for e in emojis]}}


def test_scn_prec_08_reaction_last_wins_without_reply(buttons):
    assert _go(_react(["👎"]))["reaction"] == "down" and buttons.feedback == "down"
    _go(_react(["👍"]))
    assert buttons.feedback == "up"
    assert not buttons.answers and not buttons.edits and not buttons.turns


def test_scn_prec_08_uses_last_emoji_of_new_reaction(buttons):
    _go(_react(["👍", "👎"]))
    assert buttons.feedback == "down"


@pytest.mark.parametrize("update", [
    _react(["👍"], chat=111),            # another chat
    _react(["👍"], message_id=999),      # unknown message
    _react(["❤"]),                       # not a thumb
    _react([]),                          # reaction removed
])
def test_scn_prec_08_ignored_reactions_change_nothing(buttons, update):
    out = _go(update)
    assert buttons.feedback is None and "reaction" not in out
    assert not buttons.replied and not buttons.answers


def test_scn_prec_08_reaction_without_or_with_foreign_user_changes_nothing(buttons):
    anonymous = _react(["👍"])
    del anonymous["message_reaction"]["user"]
    anonymous["message_reaction"]["actor_chat"] = {"id": 555}
    foreign = _react(["👍"])
    foreign["message_reaction"]["user"] = {"id": 111}
    for update in (anonymous, foreign):
        assert "reaction" not in _go(update)
    assert buttons.feedback is None


def test_scn_prec_08_reaction_never_raises(buttons, monkeypatch):
    import db

    monkeypatch.setattr(db, "load_tool_snapshots", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db")))
    assert _go(_react(["👍"]))["ok"] is True and buttons.feedback is None
