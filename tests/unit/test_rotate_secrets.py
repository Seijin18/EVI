"""SCN-SEC-04: secret rotation tooling never leaks values and rewrites .env safely."""
import io
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

import pytest

from testing import rotate_secrets as rs

ROOT = Path(__file__).resolve().parents[2]
OLD = {
    "EVOLUTION_API_KEY": "old-evolution-key-AAAAAAAAAAAA",
    "POSTGRES_PASSWORD": "old-postgres-pass-BBBBBBBBBBB",
    "WINDMILL_DB_PASSWORD": "old-windmill-pass-CCCCCCCCCCC",
    "NEO4J_PASSWORD": "old-neo4j-pass-DDDDDDDDDDDDDD",
}
ENV_TEXT = f"""# top comment
POSTGRES_DB=evidb
POSTGRES_USER=evi
POSTGRES_PASSWORD={OLD['POSTGRES_PASSWORD']}
WINDMILL_DB_USER=windmill
WINDMILL_DB_PASSWORD={OLD['WINDMILL_DB_PASSWORD']}

EVOLUTION_API_KEY={OLD['EVOLUTION_API_KEY']}
NEO4J_PASSWORD={OLD['NEO4J_PASSWORD']}
DATABASE_URL=postgresql://evi:{OLD['POSTGRES_PASSWORD']}@localhost:5433/evidb
OTHER_URL=postgresql://someone:keepme@host/db
# EVOLUTION_API_KEY=commented-stays
TELEGRAM_BOT_TOKEN=123456:keep-this-token-untouched
"""


def values_of(text):
    return {m.group(1): m.group(2) for m in re.finditer(r"^([A-Z_0-9]+)=(.*)$", text, re.M)}


# ------------------------------------------------------------- generator
def test_generated_secrets_are_long_and_url_safe():
    seen = {rs.generate_secret() for _ in range(50)}
    assert len(seen) == 50
    for s in seen:
        assert len(s) >= 32
        assert re.fullmatch(r"[A-Za-z0-9_-]+", s)
        assert not set("$'\"@:/\\ `;&|") & set(s)


# ----------------------------------------------------------- .env rewrite
def test_rewrite_touches_only_target_keys_and_database_url_password():
    new = {"EVOLUTION_API_KEY": "N" * 43, "POSTGRES_PASSWORD": "P" * 43}
    out = rs.rewrite_env_text(ENV_TEXT, new, {}, {"evi": new["POSTGRES_PASSWORD"]})
    before, after = ENV_TEXT.splitlines(), out.splitlines()
    assert len(before) == len(after)
    changed = {b.split("=")[0] for b, a in zip(before, after) if b != a}
    assert changed == {"POSTGRES_PASSWORD", "EVOLUTION_API_KEY", "DATABASE_URL"}
    vals = values_of(out)
    assert vals["DATABASE_URL"] == f"postgresql://evi:{'P' * 43}@localhost:5433/evidb"
    assert vals["OTHER_URL"] == "postgresql://someone:keepme@host/db"
    assert "# EVOLUTION_API_KEY=commented-stays" in out
    assert "# top comment" in out and "TELEGRAM_BOT_TOKEN=123456:keep-this-token-untouched" in out


def test_rewrite_appends_missing_key_and_skips_absent_optional():
    out = rs.rewrite_env_text("A=1\nB=2", {"QDRANT__SERVICE__API_KEY": "Q" * 43},
                              {"QDRANT_API_KEY": "Q" * 43}, {})
    assert out == "A=1\nB=2\nQDRANT__SERVICE__API_KEY=" + "Q" * 43 + "\n"
    out2 = rs.rewrite_env_text("A=1\nQDRANT_API_KEY=old\n", {"QDRANT__SERVICE__API_KEY": "x" * 43},
                               {"QDRANT_API_KEY": "x" * 43}, {})
    assert "QDRANT_API_KEY=" + "x" * 43 in out2


def test_write_atomic_is_600_and_replaces(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\n")
    p.chmod(0o644)
    rs.write_atomic(p, "A=2\n")
    assert p.read_text() == "A=2\n"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert [f.name for f in tmp_path.iterdir()] == [".env"]      # no temp file left behind


# ------------------------------------------------------------ psql / cypher
def test_psql_sql_quotes_safely_and_rejects_unsafe_input():
    sql = rs.psql_role_sql("evi", "abcDEF_123-xyz")
    assert "format('ALTER ROLE %I PASSWORD %L'" in sql
    assert "\\gexec" in sql
    with pytest.raises(ValueError):
        rs.psql_role_sql("evi; DROP", "x")
    with pytest.raises(ValueError):
        rs.psql_role_sql("evi", "pa'ss")
    with pytest.raises(ValueError):
        rs.neo4j_alter_cypher("ok", "bad value")


# ----------------------------------------------------------- fake runner
class FakeRunner:
    def __init__(self, healthy=True, dump=b"-- dump\n", fail_on=None, neo4j=False,
                 roles=("evi", "windmill"), missing_images=(), latest_version="v1.18.0",
                 images=("qdrant/qdrant:v1.18.0", "postgres:15-alpine")):
        self.calls = []        # (argv, input, env)
        self.healthy, self.dump, self.fail_on, self.neo4j = healthy, dump, fail_on, neo4j
        self.roles, self.missing, self.latest_version, self.images = roles, set(missing_images), latest_version, images

    def __call__(self, argv, *, input=None, env=None, stdout_path=None, cwd=None, timeout=600):
        self.calls.append((list(argv), input, env))
        a = " ".join(argv)
        if self.fail_on and self.fail_on in a + (input or ""):
            return 1, "", "boom " + (input or "")      # stderr echoing stdin: must be scrubbed
        if "ps postgres --format json" in a:
            return 0, json.dumps([{"Service": "postgres", "Health": "healthy" if self.healthy else "starting"}]), ""
        if argv[-2:] == ["-q", "neo4j"]:
            return (0, "abc123\n", "") if self.neo4j else (0, "", "")
        if "-Atc" in argv:
            return 0, "\n".join(self.roles) + "\n", ""
        if "config" in argv and "--images" in argv:
            return 0, "\n".join(self.images) + "\n", ""
        if argv[:3] == ["docker", "image", "inspect"]:
            if "--format" in argv:
                return 0, self.latest_version + "\n", ""
            return (1, "", "no such image") if argv[-1] in self.missing else (0, "", "")
        if argv[:2] == ["docker", "tag"]:
            self.missing.discard(argv[-1])
            return 0, "", ""
        if "pg_dumpall" in a and stdout_path is not None:
            fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.write(fd, self.dump)
            os.close(fd)
        return 0, "", ""


def make_root(tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV_TEXT)
    env.chmod(0o600)
    return tmp_path


def rotator(tmp_path, runner, http=None, **kw):
    seq = iter(f"New{i}" + "x" * 40 for i in range(100))
    buf = io.StringIO()
    r = rs.Rotator(tmp_path, runner=runner, http_get=http or ok_http,
                   now=lambda: datetime(2026, 10, 13, 1, 2, 3), sleep=lambda s: None,
                   gen=lambda: next(seq), out=buf, **kw)
    return r, buf


def health(**checks):
    return json.dumps({"status": "ok", "checks": {k: {"ok": v} for k, v in checks.items()}})


def make_http(pg=True, qd=True, evo_new=200, evo_bad=401, qdrant_nokey=401):
    """Fake endpoints. Keys rotated by the fake generator start with 'New'."""
    def http(url, headers):
        if "8002" in url:
            return 200, health(postgres=pg, qdrant=qd)
        if "8001" in url:
            return 200, ""
        if "8082" in url:
            return (evo_new if headers.get("apikey", "").startswith("New") else evo_bad), ""
        if "6333" in url:
            return (200 if headers.get("api-key", "").startswith("New") else qdrant_nokey), ""
        return 0, ""
    return http


ok_http = make_http()


# ---------------------------------------------------------------- dry-run
def test_dry_run_prints_names_never_values(tmp_path, capsys):
    root = make_root(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts" / "leaky.sh").write_text(f"KEY={OLD['EVOLUTION_API_KEY']}\n")
    assert rs.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    for name in ("EVOLUTION_API_KEY", "POSTGRES_PASSWORD", "WINDMILL_DB_PASSWORD", "NEO4J_PASSWORD",
                 "QDRANT__SERVICE__API_KEY"):
        assert name in out
    assert "evolution-api" in out and "DRY-RUN" in out
    for v in OLD.values():
        assert v not in out
    assert "scripts/leaky.sh" in out            # embedded copy is reported by path
    assert (root / ".env").read_text() == ENV_TEXT      # nothing touched
    assert not (root / "data").exists()


def test_only_selects_subset_and_alias():
    assert [s.name for s in rs.parse_only("QDRANT, evolution_api_key")] == [
        "QDRANT__SERVICE__API_KEY", "EVOLUTION_API_KEY"]
    with pytest.raises(SystemExit):
        rs.parse_only("NOPE")


# ------------------------------------------------------------------ apply
def test_apply_order_and_no_secret_in_argv(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, FakeRunner(), ok_http)
    assert r.apply(rs.parse_only(None)) == 0
    calls = r.run.calls
    joined = [" ".join(c[0]) for c in calls]

    def idx(needle):
        return next(i for i, j in enumerate(joined) if needle in j)

    assert idx("ps postgres --format json") < idx("-Atc") < idx("pg_dumpall") < idx("psql -U evi -d postgres -X -q") < idx("up -d --force-recreate")
    # .env was rewritten between ALTER ROLE and the recreate: new values are in place by then
    final = values_of((root / ".env").read_text())
    for name in ("EVOLUTION_API_KEY", "POSTGRES_PASSWORD", "WINDMILL_DB_PASSWORD", "QDRANT__SERVICE__API_KEY"):
        assert final[name].startswith("New")
    assert final["DATABASE_URL"].startswith(f"postgresql://evi:{final['POSTGRES_PASSWORD']}@")
    secrets_all = [final[k] for k in ("EVOLUTION_API_KEY", "POSTGRES_PASSWORD",
                                                                   "WINDMILL_DB_PASSWORD", "QDRANT__SERVICE__API_KEY")]
    for argv, stdin, _ in calls:
        for v in secrets_all + list(OLD.values()):
            assert v not in " ".join(argv)
    alters = [c for c in calls if c[1] and "ALTER ROLE" in c[1]]
    assert len(alters) == 2 and all("ALTER ROLE" in c[1] for c in alters)
    assert "-c" not in alters[0][0] and "-Atc" not in alters[0][0]                       # SQL goes through stdin
    up = next(c for c in calls if "up" in c[0] and "--force-recreate" in c[0])
    assert up[0][-5:] == ["evolution-api", "agent-api", "windmill-server", "windmill-worker", "qdrant"]
    assert "--no-deps" in up[0]
    out = buf.getvalue()
    for v in secrets_all + list(OLD.values()):
        assert v not in out
    # backups exist and are private
    bdir = root / "data" / "backups"
    assert stat.S_IMODE((bdir / "pre-rotate-20261013-010203.sql").stat().st_mode) == 0o600
    envbak = bdir / "env-pre-rotate-20261013-010203"
    assert stat.S_IMODE(envbak.stat().st_mode) == 0o600 and envbak.read_text() == ENV_TEXT
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600


def test_recreate_env_excludes_stale_exported_secrets(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    monkeypatch.setenv("EVOLUTION_API_KEY", "stale-exported")
    monkeypatch.setenv("UNRELATED_VAR", "kept")
    runner = FakeRunner()
    r, _ = rotator(root, runner, ok_http)
    r.apply(rs.parse_only("EVOLUTION_API_KEY"))
    up = next(c for c in runner.calls if "--force-recreate" in c[0])
    assert "EVOLUTION_API_KEY" not in up[2] and up[2]["UNRELATED_VAR"] == "kept"


def test_refuses_when_postgres_not_healthy(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner(healthy=False)
    r, buf = rotator(root, runner)
    assert r.apply(rs.parse_only(None)) == 1
    assert (root / ".env").read_text() == ENV_TEXT
    assert not any("pg_dumpall" in " ".join(c[0]) for c in runner.calls)
    assert "not healthy" in buf.getvalue()


def test_empty_dump_aborts_before_any_change(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner(dump=b"")
    r, buf = rotator(root, runner)
    assert r.apply(rs.parse_only(None)) == 1
    assert (root / ".env").read_text() == ENV_TEXT
    assert not any(c[1] and "ALTER ROLE" in c[1] for c in runner.calls)
    assert not list((root / "data" / "backups").glob("pre-rotate-*.sql"))


def test_failed_verification_prints_rollback_hint_without_values(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, FakeRunner(), lambda url, h: (500, ""))
    assert r.apply(rs.parse_only("EVOLUTION_API_KEY")) == 1
    out = buf.getvalue()
    assert "FAILED at stage: recreated" in out and "env-pre-rotate-20261013-010203" in out
    for v in list(OLD.values()) + [values_of((root / ".env").read_text())["EVOLUTION_API_KEY"]]:
        assert v not in out
    # not auto-rolled back: .env keeps the new key
    assert values_of((root / ".env").read_text())["EVOLUTION_API_KEY"].startswith("New")


def test_subprocess_error_output_is_scrubbed(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, FakeRunner(fail_on="ALTER ROLE"))
    assert r.apply(rs.parse_only("WINDMILL_DB_PASSWORD")) == 1
    out = buf.getvalue()
    assert "ALTER ROLE windmill failed" in out
    assert not re.search(r"New\d+x{40}", out)       # generated values never shown
    assert OLD["WINDMILL_DB_PASSWORD"] not in out


def test_neo4j_only_when_running(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner(neo4j=True)
    r, _ = rotator(root, runner, ok_http)
    assert r.apply(rs.parse_only("NEO4J_PASSWORD")) == 0
    ex = next(c for c in runner.calls if c[0][:2] == ["docker", "exec"])
    assert "NEO4J_PASSWORD" in ex[0] and OLD["NEO4J_PASSWORD"] not in " ".join(ex[0])
    assert "ALTER CURRENT USER" in ex[1]

    root2 = tmp_path / "b"
    root2.mkdir()
    make_root(root2)
    runner2 = FakeRunner(neo4j=False)
    r2, _ = rotator(root2, runner2, ok_http)
    assert r2.apply(rs.parse_only("NEO4J_PASSWORD")) == 0
    assert not any(c[0][:2] == ["docker", "exec"] for c in runner2.calls)
    assert "neo4j" not in next(c for c in runner2.calls if "--force-recreate" in c[0])[0]


# --------------------------------------------------------- compose / example
def test_compose_has_no_insecure_fallbacks():
    text = (ROOT / "docker-compose.yml").read_text()
    for bad in (":-evi-dev-key", ":-changeme", "evi-dev-key", "changeme", "PASSWORD:-windmill"):
        assert bad not in text
    for var in ("EVOLUTION_API_KEY", "POSTGRES_PASSWORD", "WINDMILL_DB_PASSWORD"):
        uses = re.findall(r"\$\{" + var + r"([^}]*)\}", text)
        assert uses, var
        # required where the service needs it; an EMPTY default is tolerated elsewhere
        assert all(u.startswith(":?") or u == ":-" for u in uses), (var, uses)
        assert any(u.startswith(":?") for u in uses), var
    assert all(not u or u == ":-" for u in re.findall(r"\$\{NEO4J_PASSWORD([^}]*)\}", text))


def test_compose_images_pinned():
    text = (ROOT / "docker-compose.yml").read_text()
    assert re.search(r"image: qdrant/qdrant:v\d+\.\d+\.\d+\b", text)
    assert "qdrant:latest" not in text
    assert text.count("windmill:main@sha256:") == 2


def test_security_scan_accepts_digest_pins():
    from testing.security_scan import _image_unpinned
    assert not _image_unpinned("ghcr.io/x/y:main@sha256:" + "a" * 64)
    assert _image_unpinned("ghcr.io/x/y:main")


def test_env_example_has_no_real_looking_defaults():
    text = (ROOT / ".env.example").read_text()
    for bad in ("evi-dev-key", "changeme", "WINDMILL_DB_PASSWORD=windmill"):
        assert bad not in text
    vals = values_of(text)
    for k in ("POSTGRES_PASSWORD", "WINDMILL_DB_PASSWORD", "EVOLUTION_API_KEY"):
        assert vals[k].startswith("CHANGE_ME")


# ----------------------------------------------- reviewer round: blockers 1-3
def test_degraded_health_body_fails_even_with_http_200(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, FakeRunner(), make_http(pg=False))
    assert r.apply(rs.parse_only("EVOLUTION_API_KEY")) == 1
    assert "verification failed" in buf.getvalue() and "FAILED at stage" in buf.getvalue()


def test_qdrant_health_check_required_only_when_qdrant_rotated(tmp_path):
    root = make_root(tmp_path)
    r, _ = rotator(root, FakeRunner(), make_http(qd=False))
    assert r.apply(rs.parse_only("QDRANT")) == 1
    root2 = tmp_path / "b"
    root2.mkdir()
    make_root(root2)
    r2, _ = rotator(root2, FakeRunner(), make_http(qd=False))
    assert r2.apply(rs.parse_only("EVOLUTION_API_KEY")) == 0


def test_postgres_rotation_probes_evolution(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, FakeRunner(), make_http(evo_new=401))      # crash-looping / rejecting
    assert r.apply(rs.parse_only("POSTGRES_PASSWORD")) == 1
    assert "Evolution" in buf.getvalue()
    root2 = tmp_path / "b"
    root2.mkdir()
    make_root(root2)

    def http(url, headers):       # the (unrotated) Evolution key is still the old one
        if "8082" in url:
            return (200 if headers.get("apikey") == OLD["EVOLUTION_API_KEY"] else 401), ""
        return make_http()(url, headers)

    r2, _ = rotator(root2, FakeRunner(), http)
    assert r2.apply(rs.parse_only("POSTGRES_PASSWORD")) == 0


class SnoopRunner(FakeRunner):
    def __init__(self, root, **kw):
        super().__init__(**kw)
        self.root, self.snap = root, None

    def __call__(self, argv, **kw):
        if kw.get("input") and "ALTER ROLE" in kw["input"] and self.snap is None:
            f = self.root / "data" / "backups" / "env-post-rotate-20261013-010203"
            self.snap = (f.exists(), stat.S_IMODE(f.stat().st_mode) if f.exists() else None,
                         f.read_text() if f.exists() else "")
        return super().__call__(argv, **kw)


def test_new_values_saved_0600_before_first_alter(tmp_path):
    root = make_root(tmp_path)
    runner = SnoopRunner(root)
    r, buf = rotator(root, runner, make_http(pg=False))        # fail afterwards to see the hint
    assert r.apply(rs.parse_only("POSTGRES_PASSWORD,QDRANT")) == 1
    exists, mode, text = runner.snap
    assert exists and mode == 0o600
    assert set(values_of(text)) == {"POSTGRES_PASSWORD", "QDRANT__SERVICE__API_KEY"}
    assert "env-post-rotate-20261013-010203" in buf.getvalue()
    assert text.split("=")[1].strip() not in buf.getvalue()


def test_preflight_missing_role_aborts_before_any_change(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner(roles=("evi",))
    r, buf = rotator(root, runner)
    assert r.apply(rs.parse_only(None)) == 1
    assert "windmill" in buf.getvalue() and "pg_roles" in buf.getvalue()
    assert not any("pg_dumpall" in " ".join(c[0]) or (c[1] and "ALTER" in c[1]) for c in runner.calls)
    assert (root / ".env").read_text() == ENV_TEXT


def test_unsafe_role_name_aborts_in_preflight(tmp_path):
    root = make_root(tmp_path)
    (root / ".env").write_text(ENV_TEXT.replace("WINDMILL_DB_USER=windmill", "WINDMILL_DB_USER=wm'; drop"))
    runner = FakeRunner()
    r, buf = rotator(root, runner)
    assert r.apply(rs.parse_only("WINDMILL_DB_PASSWORD")) == 1
    assert not any("pg_dumpall" in " ".join(c[0]) for c in runner.calls)


class BoomRunner(FakeRunner):
    def __init__(self, exc, when, **kw):
        super().__init__(**kw)
        self.exc, self.when = exc, when

    def __call__(self, argv, **kw):
        if self.when in " ".join(argv) + (kw.get("input") or ""):
            raise self.exc
        return super().__call__(argv, **kw)


@pytest.mark.parametrize("exc,when", [
    (__import__("subprocess").TimeoutExpired("docker", 5), "pg_dumpall"),
    (OSError("disk full"), "pg_dumpall"),
    (ValueError("bad"), "ALTER ROLE"),
])
def test_any_exception_gives_hint_and_exit_1_not_traceback(tmp_path, exc, when):
    root = make_root(tmp_path)
    r, buf = rotator(root, BoomRunner(exc, when))
    assert r.apply(rs.parse_only(None)) == 1
    out = buf.getvalue()
    assert "FAILED:" in out and "FAILED at stage" in out and "Traceback" not in out


def test_exception_message_is_scrubbed(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, BoomRunner(RuntimeError(f"conn {OLD['WINDMILL_DB_PASSWORD']}"), "ALTER ROLE"))
    assert r.apply(rs.parse_only("WINDMILL_DB_PASSWORD")) == 1
    assert OLD["WINDMILL_DB_PASSWORD"] not in buf.getvalue()


# ------------------------------------------------------ suspects 4-7
def test_missing_pinned_tag_is_tagged_from_latest_without_network(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner(missing_images=("qdrant/qdrant:v1.18.0",))
    r, _ = rotator(root, runner)
    assert r.apply(rs.parse_only("QDRANT")) == 0
    tag = [c[0] for c in runner.calls if c[0][:2] == ["docker", "tag"]]
    assert tag == [["docker", "tag", "qdrant/qdrant:latest", "qdrant/qdrant:v1.18.0"]]
    assert not any("pull" in c[0] for c in runner.calls)


def test_unavailable_image_aborts_before_any_change(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner(missing_images=("qdrant/qdrant:v1.18.0",), latest_version="v9.9.9")
    r, buf = rotator(root, runner)
    assert r.apply(rs.parse_only("QDRANT")) == 1
    assert "image not available locally" in buf.getvalue()
    assert not any("pg_dumpall" in " ".join(c[0]) for c in runner.calls)
    assert (root / ".env").read_text() == ENV_TEXT


def test_short_values_are_redacted_too(tmp_path):
    root = make_root(tmp_path)
    (root / ".env").write_text(ENV_TEXT.replace(OLD["EVOLUTION_API_KEY"], "q7Zk9xP"))
    r, buf = rotator(root, BoomRunner(RuntimeError("leak q7Zk9xP"), "ALTER ROLE"))
    r.apply(rs.parse_only("EVOLUTION_API_KEY,POSTGRES_PASSWORD"))
    assert "q7Zk9xP" not in buf.getvalue() and "FAILED" in buf.getvalue()


def test_evolution_probe_uses_fetch_instances_and_404_is_failure(tmp_path):
    root = make_root(tmp_path)
    urls = []

    def http(url, headers):
        urls.append(url)
        return make_http()(url, headers)

    r, _ = rotator(root, FakeRunner(), http)
    assert r.apply(rs.parse_only("EVOLUTION_API_KEY")) == 0
    assert all("connectionState" not in u for u in urls)
    assert any(u.endswith("/instance/fetchInstances") for u in urls)
    root0 = tmp_path / "z"
    root0.mkdir()
    make_root(root0)
    r0, _ = rotator(root0, FakeRunner(), make_http(evo_new=404))
    assert r0.apply(rs.parse_only("EVOLUTION_API_KEY")) == 1
    root2 = tmp_path / "b"
    root2.mkdir()
    make_root(root2)
    r2, _ = rotator(root2, FakeRunner(), make_http(evo_new=200, evo_bad=200))    # no auth at all
    assert r2.apply(rs.parse_only("EVOLUTION_API_KEY")) == 1
    root3 = tmp_path / "c"
    root3.mkdir()
    make_root(root3)
    r3, _ = rotator(root3, FakeRunner(), make_http(evo_new=401))
    assert r3.apply(rs.parse_only("EVOLUTION_API_KEY")) == 1


def test_env_variants_updated_in_place_no_duplicates():
    text = ("  EVOLUTION_API_KEY = old1\nexport POSTGRES_PASSWORD  =old2\n"
            "\tDATABASE_URL = postgresql://evi:old2@h:1/d\nWINDMILL_DB_PASSWORD= old3\n")
    out = rs.rewrite_env_text(text, {"EVOLUTION_API_KEY": "N1", "POSTGRES_PASSWORD": "N2",
                                     "WINDMILL_DB_PASSWORD": "N3"}, {}, {"evi": "N2"})
    assert out == ("  EVOLUTION_API_KEY = N1\nexport POSTGRES_PASSWORD  =N2\n"
                   "\tDATABASE_URL = postgresql://evi:N2@h:1/d\nWINDMILL_DB_PASSWORD= N3\n")
    assert out.count("EVOLUTION_API_KEY") == 1


def test_read_env_accepts_indent_and_spaces(tmp_path):
    p = tmp_path / ".env"
    p.write_text("  A = 1\nexport B=2\n# C=3\n")
    assert rs.read_env(p) == {"A": "1", "B": "2"}


def test_docs_mention_digest_pin_exemption():
    assert "sha256" in (ROOT / "docs" / "security.md").read_text()


# ------------------------------------------------------------ round 2
WM_IMG = "ghcr.io/windmill-labs/windmill:main@sha256:" + "a" * 64
WM_IMAGES = ("qdrant/qdrant:v1.18.0", "postgres:15-alpine", WM_IMG)


def test_parsed_output_is_not_redacted_default_windmill_pair(tmp_path):
    """Old WINDMILL_DB_PASSWORD == 'windmill' must not corrupt role lookup / image names."""
    root = make_root(tmp_path)
    (root / ".env").write_text(ENV_TEXT.replace(OLD["WINDMILL_DB_PASSWORD"], "windmill"))
    runner = FakeRunner(images=WM_IMAGES, missing_images=())
    r, buf = rotator(root, runner)
    assert r.apply(rs.parse_only("WINDMILL_DB_PASSWORD")) == 0, buf.getvalue()
    inspected = [c[0][-1] for c in runner.calls if c[0][:3] == ["docker", "image", "inspect"]]
    assert WM_IMG in inspected                     # real name, not "ghcr.io/***-labs/***"


def test_old_password_substring_of_postgres_does_not_break_health_parse(tmp_path):
    root = make_root(tmp_path)
    (root / ".env").write_text(ENV_TEXT.replace(OLD["POSTGRES_PASSWORD"], "postgre"))
    def http(url, headers):       # Evolution's own key is unrotated here
        if "8082" in url:
            return (200 if headers.get("apikey") == OLD["EVOLUTION_API_KEY"] else 401), ""
        return ok_http(url, headers)

    r, buf = rotator(root, FakeRunner(), http)
    assert r.apply(rs.parse_only("POSTGRES_PASSWORD")) == 0, buf.getvalue()
    assert "not healthy" not in buf.getvalue()


def test_printed_text_still_redacts_short_old_values(tmp_path):
    root = make_root(tmp_path)
    (root / ".env").write_text(ENV_TEXT.replace(OLD["WINDMILL_DB_PASSWORD"], "windmill"))
    r, buf = rotator(root, BoomRunner(RuntimeError("password windmill rejected"), "ALTER ROLE"))
    assert r.apply(rs.parse_only("WINDMILL_DB_PASSWORD")) == 1
    assert "password windmill rejected" not in buf.getvalue()


def test_image_preflight_scoped_to_recreated_services(tmp_path):
    root = make_root(tmp_path)
    runner = FakeRunner()
    r, _ = rotator(root, runner)
    assert r.apply(rs.parse_only("QDRANT")) == 0
    cfg = next(c[0] for c in runner.calls if c[0][-3:-2] == ["--images"] or "--images" in c[0])
    assert cfg[cfg.index("--images") + 1:] == ["qdrant", "agent-api"]


def stale_setup(tmp_path):
    root = make_root(tmp_path)
    r, _ = rotator(root, BoomRunner(RuntimeError("down"), "ALTER ROLE"))
    assert r.apply(rs.parse_only(None)) == 1
    env = root / ".env"
    old = env.stat().st_mtime - 100
    os.utime(env, (old, old))                      # .env older than env-post-rotate-*
    return root


def test_second_apply_refuses_after_half_failure_unless_forced(tmp_path):
    root = stale_setup(tmp_path)
    runner = FakeRunner()
    r2, buf = rotator(root, runner)
    assert r2.apply(rs.parse_only(None)) == 1
    out = buf.getvalue()
    assert "unfinished earlier run" in out and "env-post-rotate-20261013-010203" in out
    assert "--force-new-secrets" in out
    assert not any(c[1] and "ALTER ROLE" in c[1] for c in runner.calls)
    r3, buf3 = rotator(root, FakeRunner(), ok_http, force_new=True)
    assert r3.apply(rs.parse_only(None)) == 0
    assert "WARNING" in buf3.getvalue() and "Neo4j" in buf3.getvalue()


def test_no_refusal_when_env_is_newer_than_post_rotate(tmp_path):
    root = make_root(tmp_path)
    r, _ = rotator(root, FakeRunner(), ok_http)
    assert r.apply(rs.parse_only("QDRANT")) == 0
    r2, _ = rotator(root, FakeRunner(), ok_http)
    assert r2.apply(rs.parse_only("QDRANT")) == 0


def hint_for(tmp_path, runner, http=None, only=None):
    root = make_root(tmp_path)
    r, buf = rotator(root, runner, http)
    assert r.apply(rs.parse_only(only)) == 1
    return buf.getvalue()


def test_hint_before_alter_says_nothing_changed(tmp_path):
    out = hint_for(tmp_path, FakeRunner(roles=("evi",)))
    assert "stage: preflight" in out and "Nothing was changed" in out
    assert "cp -p" not in out
    (tmp_path / "x").mkdir()
    out2 = hint_for(tmp_path / "x", FakeRunner(dump=b""))
    assert "Nothing was changed" in out2


def test_hint_after_alter_before_env_write_says_copy_new_values(tmp_path):
    out = hint_for(tmp_path, BoomRunner(RuntimeError("x"), "ALTER ROLE"))
    assert "stage: altering" in out
    assert "Copy the values from data/backups/env-post-rotate-" in out and "do NOT restore" in out


def test_hint_after_env_write_gives_exact_recreate_command(tmp_path):
    out = hint_for(tmp_path, BoomRunner(RuntimeError("x"), "--force-recreate"), only="QDRANT")
    assert "stage: env_written" in out
    assert "docker compose up -d --force-recreate --no-deps qdrant agent-api" in out
    assert "do not restore anything" in out


def test_hint_after_recreate_says_investigate_and_rollback_last(tmp_path):
    out = hint_for(tmp_path, FakeRunner(), make_http(pg=False), only="EVOLUTION_API_KEY")
    assert "stage: recreated" in out and "investigate" in out
    assert out.index("investigate") < out.index("Last resort - rollback")


def test_post_rotate_deleted_after_verified_success_pre_backups_kept(tmp_path):
    root = make_root(tmp_path)
    r, buf = rotator(root, FakeRunner(), ok_http)
    assert r.apply(rs.parse_only("QDRANT")) == 0
    bdir = root / "data" / "backups"
    assert not list(bdir.glob("env-post-rotate-*"))
    assert list(bdir.glob("env-pre-rotate-*")) and list(bdir.glob("pre-rotate-*.sql"))
    assert "deleted data/backups/env-post-rotate-" in buf.getvalue()


def test_dry_run_mentions_post_rotate_file(tmp_path, capsys):
    rs.main(["--root", str(make_root(tmp_path))])
    assert "env-post-rotate" in capsys.readouterr().out
