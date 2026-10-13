"""SCN-SEC-03: the security scanner flags weak config without leaking secret values."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from testing import security_scan as ss

SECRET = "sk-THISISAFAKESECRETVALUE1234567890"


def by_id(findings, fid):
    return next(f for f in findings if f.id == fid)


def write(p: Path, text: str, mode=None):
    p.write_text(text)
    if mode is not None:
        p.chmod(mode)
    return p


# ---- binds
def test_binds_fail_names_service_and_port(tmp_path):
    c = write(tmp_path / "docker-compose.yml", """
services:
  good: {image: a:1, ports: ["127.0.0.1:1:1"]}
  bad: {image: b:1, ports: ["8001:8000"]}
  worse: {image: c:1, ports: ["0.0.0.0:9:9"]}
""")
    f = by_id(ss.check_binds(c), "binds.compose")
    assert f.status == ss.FAIL and "bad" in f.evidence and "worse" in f.evidence and "good" not in f.evidence


def test_binds_pass(tmp_path):
    c = write(tmp_path / "c.yml", "services:\n  a: {image: a:1, ports: ['127.0.0.1:1:1']}\n")
    assert by_id(ss.check_binds(c), "binds.compose").status == ss.PASS


def test_parse_ss_only_docker_proxy_off_loopback():
    text = (
        'LISTEN 0 4096 0.0.0.0:8001 0.0.0.0:* users:(("docker-proxy",pid=1,fd=7))\n'
        'LISTEN 0 4096 127.0.0.1:8002 0.0.0.0:* users:(("docker-proxy",pid=1,fd=7))\n'
        'LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=7))\n'
    )
    assert ss.parse_ss_listeners(text) == ["0.0.0.0:8001"]


# ---- secrets
def test_default_secrets_fail_without_leaking_values(tmp_path):
    env = write(tmp_path / ".env", "EVOLUTION_API_KEY=evi-dev-key\nPOSTGRES_PASSWORD=changeme\n"
                f"WINDMILL_DB_PASSWORD=windmill\nEVI_API_KEY=short\nOPENROUTER_API_KEY={SECRET}\n")
    findings = ss.check_default_secrets(env, None)
    f = by_id(findings, "secrets.env")
    assert f.status == ss.FAIL
    for var in ("EVOLUTION_API_KEY", "POSTGRES_PASSWORD", "WINDMILL_DB_PASSWORD", "EVI_API_KEY", "EVI_REQUIRE_API_KEY"):
        assert var in f.evidence
    blob = json.dumps([x.__dict__ for x in findings])
    for leaked in ("evi-dev-key", "changeme", SECRET):
        assert leaked not in blob
    assert by_id(findings, "secrets.qdrant").status == ss.WARN


def test_default_secrets_pass(tmp_path, monkeypatch):
    monkeypatch.delenv("QDRANT__SERVICE__API_KEY", raising=False)
    env = write(tmp_path / ".env", "EVOLUTION_API_KEY=" + "a" * 40 + "\nPOSTGRES_PASSWORD=" + "b" * 20 +
                "\nWINDMILL_DB_PASSWORD=" + "c" * 20 + "\nEVI_API_KEY=" + "d" * 64 +
                "\nEVI_REQUIRE_API_KEY=true\nQDRANT__SERVICE__API_KEY=" + "e" * 30 + "\n")
    findings = ss.check_default_secrets(env, None)
    assert by_id(findings, "secrets.env").status == ss.PASS
    assert by_id(findings, "secrets.qdrant").status == ss.PASS


def test_compose_hardcoded_fallbacks_warn(tmp_path):
    c = write(tmp_path / "c.yml", "x: ${EVOLUTION_API_KEY:-evi-dev-key} ${NEO4J_PASSWORD:-changeme} ${TZ:-UTC}\n")
    f = by_id(ss.check_default_secrets(tmp_path / "missing.env", c), "secrets.compose")
    assert f.status == ss.WARN and "EVOLUTION_API_KEY" in f.evidence and "evi-dev-key" not in f.evidence


def test_missing_env_skips(tmp_path):
    assert by_id(ss.check_default_secrets(tmp_path / ".env", None), "secrets.env").status == ss.SKIP


# ---- perms
def test_perms(tmp_path):
    write(tmp_path / ".env", "A=1\n", 0o644)
    (tmp_path / "data").mkdir(); (tmp_path / "data").chmod(0o777)
    (tmp_path / "logs").mkdir(); (tmp_path / "logs").chmod(0o700)
    res = {f.id: f for f in ss.check_file_perms(tmp_path)}
    assert res["perms.env"].status == ss.FAIL
    assert res["perms.env_world"].status == ss.FAIL
    assert res["perms.data"].status == ss.FAIL
    assert res["perms.logs"].status == ss.PASS


def test_perms_env_600_ok(tmp_path):
    write(tmp_path / ".env", "A=1\n", 0o600)
    assert by_id(ss.check_file_perms(tmp_path), "perms.env").status == ss.PASS


# ---- git history
def git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    return tmp_path


def test_git_history_finds_secret_without_printing_it(repo):
    write(repo / "cfg.txt", f"key={SECRET}\n")
    git(repo, "add", "cfg.txt"); git(repo, "commit", "-qm", "oops")
    (repo / "cfg.txt").unlink()
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "remove")
    findings = ss.check_git(repo)
    f = by_id(findings, "git.history")
    assert f.status == ss.FAIL and "cfg.txt" in f.evidence
    assert SECRET not in json.dumps([x.__dict__ for x in findings])


def test_git_clean_history_and_tracked_env(repo):
    write(repo / "a.txt", "hello\n")
    write(repo / ".env", "X=1\n")
    git(repo, "add", "-f", "a.txt", ".env"); git(repo, "commit", "-qm", "c")
    findings = ss.check_git(repo)
    assert by_id(findings, "git.history").status == ss.PASS
    assert by_id(findings, "git.tracked").status == ss.FAIL


def test_git_rewrite_dir_warns(repo):
    write(repo / "a.txt", "x\n"); git(repo, "add", "a.txt"); git(repo, "commit", "-qm", "c")
    (repo / ".git-rewrite").mkdir()
    assert by_id(ss.check_git(repo), "git.rewrite").status == ss.WARN


# ---- ruff
def test_ruff_classification(tmp_path):
    write(tmp_path / "a.py", "import subprocess\nsubprocess.run('x', shell=True)\n"
          "q = f'select {x}'  # noqa: S608 — constant table name\nr = 1  # noqa: S608\n")
    out = (
        "a.py:2:1: S602 `subprocess` call with `shell=True`\n"
        "a.py:3:5: S608 Possible SQL injection\n"
        "a.py:4:5: S608 Possible SQL injection\n"
        "a.py:9:1: S101 Use of assert\n" "a.py:9:1: S101 Use of assert\n"
    )
    res = {f.id: f for f in ss.classify_ruff(out, tmp_path)}
    assert res["ruff.blocking"].status == ss.FAIL
    assert "a.py:2" in res["ruff.blocking"].evidence and "a.py:4" in res["ruff.blocking"].evidence
    assert "a.py:3" not in res["ruff.blocking"].evidence
    assert res["ruff.other"].status == ss.WARN and "S101=2" in res["ruff.other"].evidence


# ---- pip-audit
def test_pip_audit_classification():
    assert ss.classify_pip_audit({"dependencies": [{"name": "a", "vulns": []}]})[0].status == ss.PASS
    f = ss.classify_pip_audit({"dependencies": [{"name": "a", "vulns": [
        {"id": "CVE-1", "fix_versions": ["2.0"]}]}]})[0]
    assert f.status == ss.FAIL and "CVE-1" in f.evidence and "2.0" in f.evidence
    f = ss.classify_pip_audit({"dependencies": [{"name": "a", "vulns": [{"id": "X", "fix_versions": []}]}]})[0]
    assert f.status == ss.WARN


# ---- images
def test_images_unpinned_warn(tmp_path):
    c = write(tmp_path / "c.yml", "services:\n  a: {image: q/q:latest}\n  b: {image: w/w:main}\n"
              "  c: {image: nover}\n  d: {image: ok:1.2}\n")
    f = by_id(ss.check_images(c), "images.pinned")
    assert f.status == ss.WARN
    for s in ("a=", "b=", "c="):
        assert s in f.evidence
    assert "d=" not in f.evidence


# ---- routes
APP = """
from fastapi import Depends, FastAPI
app = FastAPI()
@app.get("/health")
def h(): ...
@app.get("/ok")
def ok(_: None = Depends(verify_api_key)): ...
@app.post("/open")
def o(): ...
"""


def test_routes_flags_unlisted_open_route(tmp_path):
    m = write(tmp_path / "main.py", APP)
    res = {f.id: f for f in ss.check_routes(m)}
    assert res["routes.auth"].status == ss.FAIL
    assert "POST /open" in res["routes.auth"].evidence and "/health" not in res["routes.auth"].evidence


def test_unauthenticated_metrics_is_a_failure(tmp_path):
    m = write(tmp_path / "main.py", APP.replace('@app.post("/open")', '@app.get("/metrics")')
              .replace('@app.get("/health")', '@app.get("/health")\ndef r(): ...\n@app.get("/")'))
    res = {f.id: f for f in ss.check_routes(m)}
    assert res["routes.auth"].status == ss.FAIL


def test_real_main_has_no_unlisted_open_routes():
    root = Path(__file__).resolve().parents[2]
    routes = ss.parse_routes((root / "agent/main.py").read_text())
    assert len(routes) > 10
    open_ = {(r["method"], r["path"]) for r in routes if not r["auth"]}
    assert open_ <= ss.PUBLIC_ROUTES | ss.REVIEW_ROUTES


# ---- output / exit code
def test_main_exit_code_and_formats(tmp_path, capsys):
    write(tmp_path / "docker-compose.yml", "services:\n  a: {image: a:1, ports: ['8001:1']}\n")
    assert ss.main(["--root", str(tmp_path), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert {"id", "status", "title", "evidence"} <= set(data[0])
    assert any(d["id"] == "binds.compose" and d["status"] == "FAIL" for d in data)
    ss.main(["--root", str(tmp_path), "--markdown"])
    assert "| Status | Check | Evidence |" in capsys.readouterr().out
