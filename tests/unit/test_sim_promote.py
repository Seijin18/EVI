"""evi-sim promote: anonymization, stable mapping, TODO expect refusal (SCN-USE-07)."""
from datetime import datetime, timezone

import pytest
import yaml

from testing.sim import promote, schema
from testing.sim.schema import ScenarioError, load_file, load_scenarios

LEAKS = ["5511955550123", "95555-0123", "fulana@empresa.com.br", "Fulana Exemplo", "Fulana", "Beltrano Souza"]


def _data(**turn_over):
    turn = {
        "id": 42,
        "ts": datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc),
        "session_id": "s1",
        "channel": "telegram",
        "user_text": "Salva o contato Fulana Exemplo: 5511955550123, email fulana@empresa.com.br",
        "reply_text": "Ok, salvei Fulana Exemplo (+55 11 95555-0123). Falar com o Beltrano Souza?",
        "tools": [{"name": "learn_whatsapp_contact", "ok": True, "args": {"phone": "5511955550123"}}],
        "feedback": None,
        "feedback_note": None,
    }
    turn.update(turn_over)
    return {
        "turn": turn,
        "previous": {"user_text": "oi, ligue para 5511955550123@s.whatsapp.net", "reply_text": "claro"},
        "next": {"user_text": "e o email fulana@empresa.com.br?", "reply_text": "x"},
        "known_names": [],
    }


def test_no_source_data_in_yaml():
    _, text = promote.build_yaml(_data())
    for leak in LEAKS:
        assert leak not in text, leak
    assert "+55 11 90000-00" in text and "@exemplo.com" in text
    assert "learn_whatsapp_contact" in text  # tool names only as hint
    assert "args" not in text


def test_registry_names_and_single_first_names():
    data = _data(user_text="Pergunte pra fulana sobre a reuniao", reply_text="Ok")
    data["known_names"] = ["Fulana Exemplo"]
    _, text = promote.build_yaml(data)
    assert "fulana" not in text.lower()


def test_mapping_stable_and_distinct():
    a = promote.Anonymizer()
    t1 = a.anonymize("Fulana Exemplo 5511955550123 e Beltrano Souza 5511944440000")
    t2 = a.anonymize("Fulana Exemplo +55 11 95555-0123 fulana@empresa.com.br fulana@empresa.com.br")
    fake_name = t1.split("+55")[0].strip()
    assert fake_name and fake_name != "Fulana Exemplo"
    assert t2.startswith(fake_name)
    assert t2.count("pessoa1@exemplo.com") == 2
    # same phone in two formats -> same fake; different phone -> different fake
    p = promote.Anonymizer()
    x = p.anonymize("5511955550123 / +55 11 95555-0123 / 5511944440000")
    fakes = [f for f in x.split(" / ")]
    assert fakes[0] == fakes[1] != fakes[2]
    # deterministic across runs
    assert promote.Anonymizer().anonymize("Fulana Exemplo 5511955550123") == promote.Anonymizer().anonymize(
        "Fulana Exemplo 5511955550123"
    )


def test_dates_and_times_survive():
    out = promote.Anonymizer().anonymize("reuniao 2026-10-10 às 09:30, valor 1234")
    assert out == "reuniao 2026-10-10 às 09:30, valor 1234"


def test_yaml_validates_but_runner_refuses_todo(tmp_path):
    name, text = promote.build_yaml(_data())
    assert name == "2026-10-09-42.yaml"
    path = promote.save(text, tmp_path)
    assert path.name == name
    raw = yaml.safe_load(text)
    assert raw["steps"][0]["expect"] == {"todo": "preencher"}
    assert "TODO" in text
    with pytest.raises(ScenarioError, match=r"SIM-USE-42 has TODO expect — fill it before running"):
        load_file(path)
    with pytest.raises(ScenarioError, match="TODO expect"):
        load_scenarios(tmp_path)
    # once the human fills expect, the otherwise-unchanged draft validates
    raw["steps"][0]["expect"] = {"reply_within_s": 60, "outbound_to_third_parties": 0}
    scn = schema.parse_scenario(raw, "x")
    assert scn.steps[0].type == "telegram" and scn.source == "real-usage"


def test_whatsapp_control_step_and_unsupported_channel():
    _, text = promote.build_yaml(_data(channel="whatsapp_control"))
    assert "whatsapp_control" in yaml.safe_load(text)["steps"][0]
    with pytest.raises(promote.PromoteError):
        promote.build_yaml(_data(channel="job"))


def test_promote_uses_injected_loader(tmp_path):
    seen = []

    def loader(tid):
        seen.append(tid)
        return _data()

    path = promote.promote("42", loader, tmp_path)
    assert seen == ["42"] and path.exists()
    content = path.read_text(encoding="utf-8")
    assert all(leak not in content for leak in LEAKS)


def test_jid_is_phone_not_email():
    out = promote.Anonymizer().anonymize("5511955550123@s.whatsapp.net e +55 11 95555-0123")
    assert "@s.whatsapp.net" in out and "exemplo.com" not in out and "5511955550123" not in out
    assert out.split("@")[0].endswith("01")
