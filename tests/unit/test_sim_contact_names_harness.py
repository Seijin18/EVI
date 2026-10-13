"""evi-sim extensions for evi-contact-names: People API fake, Monday clock, job response, bare-number contact."""
import json
from datetime import date

import pytest

from testing.sim import runner, schema
from testing.sim.fake_google import FakeGoogle
from testing.sim.schema import ScenarioError, parse_relative, parse_scenario

TZ = "America/Sao_Paulo"
AUTH = {"Authorization": "Bearer tok"}
PEOPLE = "https://people.googleapis.com/v1/people/me/connections"


def _get(g, url):
    status, body, _ = g.handle("GET", url, AUTH, None)
    return status, json.loads(body)


def test_fake_people_api_pages_and_keeps_extra_fields_for_the_script_to_drop():
    g = FakeGoogle()
    g.seed({"contacts": [{"name": f"P{i}", "phones": [f"(11) 9{i:04d}-0000"], "email": f"p{i}@x.test"} for i in range(5)]})
    st, page1 = _get(g, f"{PEOPLE}?personFields=names,phoneNumbers&pageSize=2")
    assert st == 200 and len(page1["connections"]) == 2 and page1["nextPageToken"] == "2"
    st, page3 = _get(g, f"{PEOPLE}?personFields=names,phoneNumbers&pageSize=2&pageToken=4")
    assert len(page3["connections"]) == 1 and "nextPageToken" not in page3
    assert page1["connections"][0]["emailAddresses"][0]["value"] == "p0@x.test"
    assert _get(g, PEOPLE)[0] == 400  # personFields mask is required, like the real API
    g.reset()
    assert _get(g, f"{PEOPLE}?personFields=names")[1]["connections"] == []


def test_real_list_contacts_script_returns_only_name_and_phones_from_the_fake():
    from pathlib import Path

    from testing.sim.fake_windmill import FakeWindmill

    g = FakeGoogle()
    g.seed({"contacts": [{"name": "Marina Costa", "phones": ["(11) 95555-0501"], "email": "m@x.test"}]})
    scripts = Path(__file__).resolve().parents[2] / "windmill/f/integrations"
    assert (scripts / "list_contacts.py").is_file()
    w = FakeWindmill(g, scripts_dir=str(scripts))
    status, body, _ = w.handle(
        "POST", "/api/w/evi/jobs/run_wait_result/p/f/integrations/list_contacts", {}, json.dumps({"gcontacts": "$res:gcontacts"}).encode()
    )
    assert status == 200
    assert json.loads(body) == [{"name": "Marina Costa", "phones": ["(11) 95555-0501"]}]


def test_monday_relative_dates():
    tue = date(2026, 3, 10)  # Tuesday
    assert parse_relative("M0 07:00", tue, TZ).date() == date(2026, 3, 9)
    assert parse_relative("M1 11:00", tue, TZ).date() == date(2026, 3, 16)
    assert parse_relative("M-1", tue, TZ).date() == date(2026, 3, 2)
    mon = date(2026, 3, 9)
    assert parse_relative("M0 09:00", mon, TZ).date() == mon
    assert parse_relative("M0 09:00", date(2026, 3, 15), TZ).date() == mon  # Sunday -> the Monday before
    assert schema.is_relative("M1 06:00") and not schema.is_relative("M")


def test_contact_names_job_and_seed_are_accepted():
    scn = parse_scenario({
        "id": "SIM-X",
        "seed": {"contacts": [{"name": "A", "phones": ["1"]}]},
        "clock": "M0 07:00",
        "steps": [{"job": "contact-names-sync", "expect": {"job_response_matches": "protected_user"}}],
    })
    assert scn.steps[0].value == "contact-names-sync"


def test_job_response_matches_only_on_job_steps_and_evaluates():
    with pytest.raises(ScenarioError):
        parse_scenario({"id": "SIM-X", "steps": [{"telegram": "oi", "expect": {"job_response_matches": "x"}}]})
    exp = {"job_response_matches": '"protected_user": 1'}
    assert schema.eval_expect(exp, {"job_response": '{"status": "ok", "protected_user": 1}'}) == []
    assert schema.eval_expect(exp, {"job_response": '{"protected_user": 0}'})
    assert schema.eval_expect(exp, {})


def test_empty_push_name_removes_the_profile_name():
    named = runner.build_webhook_payload("oi", "5511999990001@s.whatsapp.net", push_name="Ana")
    bare = runner.build_webhook_payload("oi", "5511999990001@s.whatsapp.net", push_name="")
    assert named["data"]["messages"][0]["pushName"] == "Ana"
    assert "pushName" not in bare["data"]["messages"][0]
