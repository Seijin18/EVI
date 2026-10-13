"""Rotate the stack's default/static secrets (change evi-security-review, task 3.2).

Dry-run by default. ``--apply`` backs up, changes the roles/keys inside the running
services, rewrites ``.env`` atomically, recreates only the affected services and
verifies them. Secret VALUES never reach stdout/stderr, argv or exception text:
only names, paths and statuses are printed, and captured subprocess output is
scrubbed of every known old/new value before it is shown.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

SAFE_VALUE = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
URL_CRED = re.compile(r"^(?P<head>\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*['\"]?[A-Za-z][A-Za-z0-9+.-]*://)"
                      r"(?P<user>[^:/@\s'\"]+):(?P<pw>[^@\s'\"]*)@")
ENV_LINE = re.compile(r"^(?P<indent>\s*)(?P<export>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
                      r"(?P<pre>[ \t]*)=(?P<post>[ \t]*)(?P<val>.*)$")

PLACEHOLDER_PREFIX = "CHANGE_ME"


@dataclass(frozen=True)
class SecretSpec:
    name: str
    env_keys: Tuple[str, ...]            # written to .env (appended when missing)
    optional_keys: Tuple[str, ...]       # rewritten only if already present
    services: Tuple[str, ...]            # recreated after the change
    what: str


SPECS: Dict[str, SecretSpec] = {s.name: s for s in (
    SecretSpec("EVOLUTION_API_KEY", ("EVOLUTION_API_KEY",), (), ("evolution-api", "agent-api"),
               "Evolution AUTHENTICATION_API_KEY + agent client key"),
    SecretSpec("POSTGRES_PASSWORD", ("POSTGRES_PASSWORD",), (), ("evolution-api", "agent-api"),
               "main DB role (agent DATABASE_URL, Evolution DATABASE_CONNECTION_URI, DATABASE_URL in .env)"),
    SecretSpec("WINDMILL_DB_PASSWORD", ("WINDMILL_DB_PASSWORD",), (), ("windmill-server", "windmill-worker"),
               "Windmill DB role"),
    SecretSpec("NEO4J_PASSWORD", ("NEO4J_PASSWORD",), (), ("neo4j", "agent-api"),
               "Neo4j login (agent graph client)"),
    SecretSpec("QDRANT__SERVICE__API_KEY", ("QDRANT__SERVICE__API_KEY",), ("QDRANT_API_KEY",),
               ("qdrant", "agent-api"), "Qdrant api-key (agent receives it as QDRANT_API_KEY)"),
)}
ALIASES = {"QDRANT": "QDRANT__SERVICE__API_KEY", "QDRANT_API_KEY": "QDRANT__SERVICE__API_KEY"}
ORDER = list(SPECS)

# Files (relative to root) searched for rotated values outside .env.
EMBED_SCAN = ("windmill", "scripts", "docs", "tests/sim", ".github", "Makefile", "README.md",
              "docker-compose.yml", "docker-compose.smoke.yml", "docker-compose.sim.yml")
EMBED_SKIP_SUFFIX = (".pyc", ".png", ".jpg", ".gz", ".sqlite", ".db")


# --------------------------------------------------------------- primitives
def generate_secret() -> str:
    """URL-safe: survives inside DATABASE_URL, a shell and a psql string unescaped."""
    return secrets.token_urlsafe(32)


def redact(text: str, values: Sequence[str]) -> str:
    for v in sorted({v for v in values if v}, key=len, reverse=True):
        text = text.replace(v, "***")
    return text


def read_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for raw in path.read_text(errors="replace").splitlines():
        m = ENV_LINE.match(raw)
        if m and not raw.lstrip().startswith("#"):
            v = m.group("val").strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            env[m.group("key")] = v
    return env


def rewrite_env_text(text: str, updates: Dict[str, str], optional: Dict[str, str],
                     url_passwords: Dict[str, str]) -> str:
    """Return ``text`` with only the target keys and URL passwords replaced.

    ``updates``: written (appended when absent). ``optional``: only if present.
    ``url_passwords``: {db_user: new_password}, swapped inside ``scheme://user:pw@`` values.
    Comments, blank lines, ordering and every other line stay byte-identical.
    """
    seen = set()
    out: List[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        eol = line[len(body):]
        stripped = body.lstrip()
        if stripped and not stripped.startswith("#"):
            m = ENV_LINE.match(body)
            if m:
                key = m.group("key")
                newval = updates.get(key) if key in updates else optional.get(key)
                if newval is not None:
                    seen.add(key)
                    out.append(f"{m.group('indent')}{m.group('export') or ''}{key}{m.group('pre')}={m.group('post')}"
                               f"{newval}{eol or chr(10)}")
                    continue
                um = URL_CRED.match(body)
                if um and um.group("user") in url_passwords:
                    new = url_passwords[um.group("user")]
                    out.append(body[:um.start("pw")] + new + body[um.end("pw"):] + eol)
                    continue
        out.append(line)
    result = "".join(out)
    missing = [k for k in updates if k not in seen]
    if missing:
        if result and not result.endswith("\n"):
            result += "\n"
        result += "".join(f"{k}={updates[k]}\n" for k in missing)
    return result


def write_atomic(path: Path, text: str) -> None:
    """Temp file in the same dir, mode 600, fsync, rename over the target."""
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def psql_role_sql(role: str, password: str) -> str:
    """psql script (fed on stdin, never argv) that sets a role password quoting-safely."""
    if not SAFE_IDENT.match(role):
        raise ValueError(f"unsafe role name: {role!r}")
    if not SAFE_VALUE.match(password):
        raise ValueError("password has characters outside [A-Za-z0-9_-]")
    return (
        "\\set ON_ERROR_STOP on\n"
        f"\\set rot_role '{role}'\n"
        f"\\set rot_pw '{password}'\n"
        "SELECT format('ALTER ROLE %I PASSWORD %L', :'rot_role', :'rot_pw') \\gexec\n"
    )


def neo4j_alter_cypher(old: str, new: str) -> str:
    for v in (old, new):
        if not SAFE_VALUE.match(v):
            raise ValueError("neo4j password has characters outside [A-Za-z0-9_-]")
    return (f":param old => '{old}';\n:param new => '{new}';\n"
            "ALTER CURRENT USER SET PASSWORD FROM $old TO $new;\n")


# ------------------------------------------------------------------ plumbing
class RotationError(RuntimeError):
    pass


Runner = Callable[..., Tuple[int, str, str]]
HttpGet = Callable[[str, Dict[str, str]], Tuple[int, str]]


def default_runner(argv: Sequence[str], *, input: Optional[str] = None,
                   env: Optional[Dict[str, str]] = None, stdout_path: Optional[Path] = None,
                   cwd: Optional[Path] = None, timeout: int = 600) -> Tuple[int, str, str]:
    if stdout_path is not None:
        fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            res = subprocess.run(list(argv), input=(input.encode() if input else None), stdout=fh,
                                 stderr=subprocess.PIPE, env=env, cwd=cwd, timeout=timeout)
        return res.returncode, "", res.stderr.decode(errors="replace")
    res = subprocess.run(list(argv), input=input, capture_output=True, text=True,
                         env=env, cwd=cwd, timeout=timeout)
    return res.returncode, res.stdout, res.stderr


def default_http_get(url: str, headers: Dict[str, str]) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read(65536).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


@dataclass
class Plan:
    secrets: List[SecretSpec]
    services: List[str]
    steps: List[str]
    warnings: List[str] = field(default_factory=list)
    embeds: Dict[str, List[str]] = field(default_factory=dict)   # secret name -> file paths
    neo4j_running: bool = False


def parse_only(only: Optional[str]) -> List[SecretSpec]:
    if not only:
        return [SPECS[n] for n in ORDER]
    chosen: List[SecretSpec] = []
    for raw in only.split(","):
        name = ALIASES.get(raw.strip().upper(), raw.strip().upper())
        if name not in SPECS:
            raise SystemExit(f"unknown secret {raw!r}; choose from: {', '.join(ORDER)}")
        if SPECS[name] not in chosen:
            chosen.append(SPECS[name])
    return chosen


def scan_embeds(root: Path, old_values: Dict[str, str]) -> Dict[str, List[str]]:
    """Files outside .env that contain an old value (paths only, never the value)."""
    needles = {n: v for n, v in old_values.items() if len(v) >= 12 and not v.startswith(PLACEHOLDER_PREFIX)}
    found: Dict[str, List[str]] = {}
    if not needles:
        return found
    for rel in EMBED_SCAN:
        base = root / rel
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = sorted(p for p in base.rglob("*") if p.is_file())
        else:
            files = []
        for f in files:
            if f.suffix in EMBED_SKIP_SUFFIX or "__pycache__" in f.parts or "node_modules" in f.parts:
                continue
            try:
                txt = f.read_text(errors="ignore")
            except OSError:
                continue
            for name, val in needles.items():
                if val in txt:
                    found.setdefault(name, []).append(str(f.relative_to(root)))
    return found


class Rotator:
    def __init__(self, root: Path, *, runner: Runner = default_runner,
                 http_get: HttpGet = default_http_get, env_file: Optional[Path] = None,
                 now: Callable[[], datetime] = datetime.now, sleep: Callable[[float], None] = time.sleep,
                 gen: Callable[[], str] = generate_secret, out=None, force_new: bool = False):
        self.root = root
        self.env_path = env_file or root / ".env"
        self.run = runner
        self.http_get = http_get
        self.now = now
        self.sleep = sleep
        self.gen = gen
        self.out = out or sys.stdout
        self.known: List[str] = []        # every value that must never be printed
        self.paths: Dict[str, Path] = {}
        self.stage = "preflight"
        self.recreate_cmd = ""
        self.force_new = force_new

    # ------------------------------------------------------------ helpers
    def say(self, msg: str = "") -> None:
        print(redact(msg, self.known), file=self.out)

    def _compose(self, args: Sequence[str], *, graph: bool = False, input: Optional[str] = None,
                 stdout_path: Optional[Path] = None, rotated: Sequence[str] = ()) -> Tuple[int, str, str]:
        argv = ["docker", "compose"] + (["--profile", "graph"] if graph else []) + list(args)
        # Shell-exported values override .env interpolation: never let a stale one in.
        env = {k: v for k, v in os.environ.items() if k not in rotated}
        rc, out, err = self.run(argv, input=input, env=env, stdout_path=stdout_path, cwd=self.root)
        # Raw on purpose: callers PARSE this. Only text that is printed/raised is redacted
        # (say(), _must(), the hint), never data the program compares.
        return rc, out, err

    def _must(self, step: str, rc_out_err: Tuple[int, str, str]) -> str:
        rc, out, err = rc_out_err
        if rc != 0:
            tail = redact((err.strip().splitlines() or ["no stderr"])[-1][:200], self.known)
            raise RotationError(f"{step} failed (exit {rc}): {tail}")
        return out

    def _service_running(self, name: str) -> bool:
        rc, out, _ = self._compose(["ps", "-q", name], graph=True)
        return rc == 0 and bool(out.strip())

    def _postgres_healthy(self) -> bool:
        rc, out, _ = self._compose(["ps", "postgres", "--format", "json"])
        if rc != 0 or not out.strip():
            return False
        rows: list = []
        text = out.strip()
        try:
            data = json.loads(text)
            rows = data if isinstance(data, list) else [data]
        except ValueError:
            for ln in text.splitlines():
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    pass
        return any(r.get("Service") == "postgres" and r.get("Health") == "healthy" for r in rows)

    # --------------------------------------------------------------- plan
    def build_plan(self, chosen: List[SecretSpec], env: Dict[str, str]) -> Plan:
        names = [s.name for s in chosen]
        neo = False
        if "NEO4J_PASSWORD" in names:
            try:
                neo = self._service_running("neo4j")
            except Exception:
                neo = False
        services: List[str] = []
        for s in chosen:
            for svc in s.services:
                if svc == "neo4j" and not neo:
                    continue
                if svc not in services:
                    services.append(svc)
        pg_user = env.get("POSTGRES_USER", "")
        wm_user = env.get("WINDMILL_DB_USER", "windmill")
        steps = [
            "check: docker compose ps shows postgres healthy (else refuse)",
            "backup: pg_dumpall -> data/backups/pre-rotate-<ts>.sql (0600, abort if empty)",
            "backup: .env -> data/backups/env-pre-rotate-<ts> (0600); NEW values -> data/backups/env-post-rotate-<ts> "
            "(0600, plain text; deleted after a verified success)",
        ]
        if "POSTGRES_PASSWORD" in names:
            steps.append(f"postgres: ALTER ROLE {pg_user or '<POSTGRES_USER>'} (password via psql stdin)")
        if "WINDMILL_DB_PASSWORD" in names:
            steps.append(f"postgres: ALTER ROLE {wm_user} (password via psql stdin)")
        if "NEO4J_PASSWORD" in names:
            steps.append("neo4j: ALTER CURRENT USER (cypher on stdin)" if neo
                         else "neo4j: not running -> only .env changes")
        keys = [k for s in chosen for k in s.env_keys]
        steps.append("write .env atomically (0600): " + ", ".join(keys)
                     + (", password inside DATABASE_URL" if "POSTGRES_PASSWORD" in names else ""))
        steps.append("recreate (force, no-deps, --wait): " + ", ".join(services))
        steps.append("verify: agent /health 200; Evolution /instance/fetchInstances 200 with the key (invalid key 401/403); "
                     "Windmill /api/version; Qdrant 200 with key / 401 without")
        plan = Plan(chosen, services, steps, neo4j_running=neo)
        if "NEO4J_PASSWORD" in names and not neo:
            plan.warnings.append("neo4j is not running: only .env changes. NEO4J_AUTH applies only to a fresh "
                                 "data dir; if data/neo4j is already initialised run ALTER CURRENT USER "
                                 "after starting it.")
        if "POSTGRES_PASSWORD" in names and not pg_user:
            plan.warnings.append("POSTGRES_USER missing from .env")
        old = {s.name: env.get(s.env_keys[0], "") for s in chosen}
        plan.embeds = scan_embeds(self.root, old)
        for name, files in sorted(plan.embeds.items()):
            plan.warnings.append(f"{name}: current value is embedded outside .env in: {', '.join(sorted(set(files)))}")
        plan.warnings.append("Windmill resources/variables set through its UI live in the windmill DB and are not "
                             "scanned: check any that hold EVOLUTION_API_KEY / EVI_API_KEY copies.")
        if "WINDMILL_DB_PASSWORD" in names:
            plan.warnings.append("scripts/postgres-init/01-windmill-db.sql hard-codes the initial windmill role "
                                 "password (fresh data dir only); the rotation ALTERs it.")
        return plan

    def print_plan(self, plan: Plan, apply: bool) -> None:
        self.say(f"== evi-rotate-secrets ({'APPLY' if apply else 'DRY-RUN'}) ==")
        self.say("Secrets to rotate (names only):")
        for s in plan.secrets:
            extra = f" (+{', '.join(s.optional_keys)} if present)" if s.optional_keys else ""
            self.say(f"  - {s.name}{extra}: {s.what}")
        self.say("Services recreated: " + (", ".join(plan.services) or "none"))
        self.say("Steps:")
        for i, st in enumerate(plan.steps, 1):
            self.say(f"  {i}. {st}")
        if plan.warnings:
            self.say("Warnings:")
            for w in plan.warnings:
                self.say(f"  ! {w}")
        if not apply:
            self.say("Nothing changed. Re-run with --apply to rotate.")

    # -------------------------------------------------------------- apply
    def apply(self, chosen: List[SecretSpec]) -> int:
        ts = self.now().strftime("%Y%m%d-%H%M%S")
        bdir = self.root / "data" / "backups"
        self.paths = {"sql": bdir / f"pre-rotate-{ts}.sql", "env": bdir / f"env-pre-rotate-{ts}",
                      "new": bdir / f"env-post-rotate-{ts}"}
        env: Dict[str, str] = {}
        try:
            env = read_env(self.env_path)
            return self._apply(chosen, env, bdir)
        except Exception as e:      # noqa: BLE001 - never a raw traceback; message is scrubbed
            msg = str(e) if isinstance(e, RotationError) else f"{type(e).__name__}: {e}"
            self.say(f"FAILED: {msg}")
            self._rollback_hint(chosen, env)
            return 1

    def _apply(self, chosen: List[SecretSpec], env: Dict[str, str], bdir: Path) -> int:
        old_vals = {k: v for k, v in env.items() if any(k in s.env_keys + s.optional_keys for s in chosen)}
        new_vals = {s.name: self.gen() for s in chosen}
        for v in new_vals.values():
            if not SAFE_VALUE.match(v):
                raise RotationError("generated secret has unsafe characters")
        # Even short (default) old values are redacted: better a mangled service
        # name in the output than a leaked password.
        self.known = [v for v in list(old_vals.values()) + list(new_vals.values()) if len(v) >= 6]
        plan = self.build_plan(chosen, env)
        self.print_plan(plan, apply=True)
        names = [s.name for s in chosen]
        rotated_keys = [k for s in chosen for k in s.env_keys + s.optional_keys]
        sql_bak, env_bak, new_bak = self.paths["sql"], self.paths["env"], self.paths["new"]
        pg_user = env.get("POSTGRES_USER", "")
        wm_user = env.get("WINDMILL_DB_USER", "windmill")
        roles = ([pg_user] if "POSTGRES_PASSWORD" in names else []) + (
            [wm_user] if "WINDMILL_DB_PASSWORD" in names else [])

        self.say("[a] preflight (no changes yet)")
        if not self._postgres_healthy():
            raise RotationError("postgres is not healthy (docker compose ps); refusing to rotate")
        if not SAFE_IDENT.match(pg_user):
            raise RotationError("POSTGRES_USER missing or unsafe in .env")
        for role in roles:
            psql_role_sql(role, "x" * 43)                    # name validation only
        if roles:
            quoted = ",".join(f"'{r}'" for r in roles)
            out = self._must("role lookup", self._compose(
                ["exec", "-T", "postgres", "psql", "-U", pg_user, "-d", "postgres", "-X", "-Atc",
                 f"SELECT rolname FROM pg_roles WHERE rolname IN ({quoted})"]))
            missing = sorted(set(roles) - set(out.split()))
            if missing:
                raise RotationError(f"DB role(s) not found in pg_roles: {', '.join(missing)}")
        self._check_unfinished(bdir, names)
        self._ensure_images(plan.services)

        self.say("[b] backing up all databases (pg_dumpall)")
        bdir.mkdir(parents=True, exist_ok=True)
        os.chmod(bdir, 0o700)
        rc, _, err = self._compose(["exec", "-T", "postgres", "pg_dumpall", "-U", pg_user],
                                   stdout_path=sql_bak)
        if rc != 0 or not sql_bak.exists() or sql_bak.stat().st_size == 0:
            try:
                sql_bak.unlink()
            except OSError:
                pass
            raise RotationError("pg_dumpall backup failed or empty: "
                                + redact((err.strip().splitlines() or ["empty dump"])[-1][:200], self.known))
        os.chmod(sql_bak, 0o600)
        self.say(f"    {sql_bak.relative_to(self.root)}")

        self.say("[c] backing up .env and saving the NEW values (0600) before any change")
        self._write_private(env_bak, self.env_path.read_text())
        updates = {k: new_vals[s.name] for s in chosen for k in s.env_keys}
        optional = {k: new_vals[s.name] for s in chosen for k in s.optional_keys}
        self._write_private(new_bak, "".join(f"{k}={v}\n" for k, v in {**updates, **{
            k: v for k, v in optional.items() if k in env}}.items()))
        self.say(f"    {env_bak.relative_to(self.root)}")
        self.say(f"    {new_bak.relative_to(self.root)}")
        self.stage = "backed_up"

        self.say("[d] changing credentials inside the running services")
        self.stage = "altering"
        if "POSTGRES_PASSWORD" in names:
            self._alter_pg_role(pg_user, pg_user, new_vals["POSTGRES_PASSWORD"])
        if "WINDMILL_DB_PASSWORD" in names:
            self._alter_pg_role(pg_user, wm_user, new_vals["WINDMILL_DB_PASSWORD"])
        if "NEO4J_PASSWORD" in names and plan.neo4j_running:
            self._alter_neo4j(env, new_vals["NEO4J_PASSWORD"])

        self.say("[e] rewriting .env atomically")
        url_pw: Dict[str, str] = {}
        if "POSTGRES_PASSWORD" in names:
            url_pw[pg_user] = new_vals["POSTGRES_PASSWORD"]
        if "WINDMILL_DB_PASSWORD" in names:
            url_pw[wm_user] = new_vals["WINDMILL_DB_PASSWORD"]
        write_atomic(self.env_path, rewrite_env_text(self.env_path.read_text(), updates, optional, url_pw))
        self.stage = "env_written"

        self.say("[f] recreating affected services")
        self.recreate_cmd = ("docker compose " + ("--profile graph " if "neo4j" in plan.services else "")
                             + "up -d --force-recreate --no-deps " + " ".join(plan.services))
        self._must("docker compose up", self._compose(
            ["up", "-d", "--force-recreate", "--no-deps", "--wait", "--wait-timeout", "240"] + plan.services,
            graph="neo4j" in plan.services, rotated=rotated_keys))
        self.stage = "recreated"

        self.say("[g] verifying")
        self._verify(names, plan.services, read_env(self.env_path))
        try:
            new_bak.unlink()
            self.say(f"    deleted {new_bak.relative_to(self.root)} (it held the new secrets in plain text; "
                     "removed after successful verification)")
        except OSError:
            self.say(f"    WARNING: could not delete {new_bak.relative_to(self.root)} "
                     "(plain-text new secrets): rm it yourself")
        self.say("OK: rotation complete. Kept (0600, hold the OLD secrets/data): "
                 f"{env_bak.relative_to(self.root)}, {sql_bak.relative_to(self.root)}; delete when no longer needed.")
        for name, files in sorted(plan.embeds.items()):
            self.say(f"REMINDER: update {name} copies in: {', '.join(sorted(set(files)))}")
        return 0

    def _check_unfinished(self, bdir: Path, names: List[str]) -> None:
        """A leftover env-post-rotate newer than .env = a half-finished earlier run."""
        env_mtime = self.env_path.stat().st_mtime
        stale = sorted(f for f in bdir.glob("env-post-rotate-*") if f.stat().st_mtime > env_mtime)
        if not stale:
            return
        listing = ", ".join(str(f.relative_to(self.root)) for f in stale)
        neo = (" Neo4j: its password may already be the one in that file, while the ALTER here "
               "authenticates with the (old) value from .env." if "NEO4J_PASSWORD" in names else "")
        if not self.force_new:
            raise RotationError(
                f"unfinished earlier run: {listing} is newer than .env (new secrets that never reached .env). "
                "Resume by copying its values into .env and recreating the services, or discard them "
                "and re-run with --force-new-secrets." + neo)
        self.say(f"    WARNING: --force-new-secrets: ignoring {listing}." + neo)

    @staticmethod
    def _write_private(path: Path, text: str) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(path, 0o600)

    def _ensure_images(self, services: List[str]) -> None:
        """Every image of the recreated services must exist locally (no pulls)."""
        rc, out, err = self._compose(["config", "--images"] + list(services), graph="neo4j" in services)
        if rc != 0:
            raise RotationError("docker compose config --images failed")
        for image in sorted({ln.strip() for ln in out.splitlines() if ln.strip()}):
            if self.run(["docker", "image", "inspect", image], cwd=self.root)[0] == 0:
                continue
            repo, _, tag = image.partition("@")[0].rpartition(":")
            if repo and tag and "/" not in tag and self._retag_from_latest(repo, tag):
                self.say(f"    tagged {image} from {repo}:latest (same build, no network)")
                continue
            raise RotationError(f"image not available locally: {image} (no pull is attempted; "
                                f"pull or tag it first)")

    def _retag_from_latest(self, repo: str, tag: str) -> bool:
        fmt = '{{index .Config.Labels "org.opencontainers.image.version"}}'
        rc, out, _ = self.run(["docker", "image", "inspect", "--format", fmt, f"{repo}:latest"], cwd=self.root)
        if rc != 0 or out.strip() != tag:
            return False
        return self.run(["docker", "tag", f"{repo}:latest", f"{repo}:{tag}"], cwd=self.root)[0] == 0

    def _alter_pg_role(self, superuser: str, role: str, password: str) -> None:
        sql = psql_role_sql(role, password)
        self._must(f"ALTER ROLE {role}", self._compose(
            ["exec", "-T", "postgres", "psql", "-U", superuser, "-d", "postgres", "-X", "-q"], input=sql))
        self.say(f"    role {role}: password changed")

    def _alter_neo4j(self, env: Dict[str, str], new: str) -> None:
        old = env.get("NEO4J_PASSWORD", "")
        _, cid, _ = self._compose(["ps", "-q", "neo4j"], graph=True)
        container = cid.strip().splitlines()[0] if cid.strip() else ""
        if not container:
            raise RotationError("neo4j container id not found")
        cenv = {**os.environ, "NEO4J_USERNAME": env.get("NEO4J_USER", "neo4j"), "NEO4J_PASSWORD": old}
        # -e NAME (no value): docker reads it from OUR environment, so argv stays clean.
        rc, out, err = self.run(["docker", "exec", "-i", "-e", "NEO4J_USERNAME", "-e", "NEO4J_PASSWORD",
                                 container, "cypher-shell"],
                                input=neo4j_alter_cypher(old, new), env=cenv, cwd=self.root)
        self._must("neo4j ALTER CURRENT USER", (rc, out, err))
        self.say("    neo4j: password changed")

    # ------------------------------------------------------------- verify
    def _retry(self, what: str, fn: Callable[[], bool], tries: int = 30) -> None:
        for _ in range(tries):
            if fn():
                self.say(f"    ok: {what}")
                return
            self.sleep(2)
        raise RotationError(f"verification failed: {what}")

    def _health_ok(self, need: Sequence[str]) -> bool:
        """/health answers 200 even when degraded: the body's checks decide."""
        status, body = self.http_get("http://127.0.0.1:8002/health", {})
        if status != 200:
            return False
        try:
            checks = json.loads(body).get("checks") or {}
        except (ValueError, AttributeError):
            return False
        return all(isinstance(checks.get(n), dict) and checks[n].get("ok") is True for n in need)

    def _verify(self, names: List[str], services: List[str], env: Dict[str, str]) -> None:
        if "agent-api" in services:
            need = ["postgres"] + (["qdrant"] if "QDRANT__SERVICE__API_KEY" in names else [])
            self._retry(f"agent /health 200 with checks {'+'.join(need)} ok", lambda: self._health_ok(need))
        if "EVOLUTION_API_KEY" in names or "POSTGRES_PASSWORD" in names:
            # Evolution crash-loops on a bad DB password and --wait does not notice.
            # fetchInstances has no instance in the path, so auth is decided before any 404.
            url = "http://127.0.0.1:8082/instance/fetchInstances"
            key = env.get("EVOLUTION_API_KEY", "")
            self._retry("Evolution fetchInstances 200 with the key",
                        lambda: self.http_get(url, {"apikey": key})[0] == 200)
            if self.http_get(url, {"apikey": "rotation-probe-invalid"})[0] not in (401, 403):
                raise RotationError("verification failed: Evolution accepted an invalid key")
            self.say("    ok: Evolution rejects an invalid key")
        if "WINDMILL_DB_PASSWORD" in names:
            self._retry("Windmill /api/version 200",
                        lambda: self.http_get("http://127.0.0.1:8001/api/version", {})[0] == 200)
        if "QDRANT__SERVICE__API_KEY" in names:
            url = "http://127.0.0.1:6333/collections"
            self._retry("Qdrant 200 with api-key",
                        lambda: self.http_get(url, {"api-key": env["QDRANT__SERVICE__API_KEY"]})[0] == 200)
            if self.http_get(url, {})[0] != 401:
                raise RotationError("verification failed: Qdrant answered without a key (expected 401)")
            self.say("    ok: Qdrant 401 without a key")

    def _rollback_hint(self, chosen: List[SecretSpec], env: Dict[str, str]) -> None:
        env_bak, sql_bak, new_bak = self.paths["env"], self.paths["sql"], self.paths["new"]
        rel = lambda p: p.relative_to(self.root)      # noqa: E731
        svc_cmd = self.recreate_cmd or "docker compose up -d --force-recreate --no-deps <affected services>"
        self.say("")
        self.say(f"FAILED at stage: {self.stage}. Nothing was reverted automatically.")
        if self.stage in ("preflight", "backed_up"):
            self.say("  Nothing was changed in the services or in .env"
                     + (" (only backup files were written)." if self.stage == "backed_up" else "."))
        elif self.stage == "altering":
            self.say("  DB roles / Neo4j may already have the NEW passwords while .env still has the old ones.")
            self.say(f"  1. Copy the values from {rel(new_bak)} into .env (do NOT restore {rel(env_bak)}).")
            self.say(f"  2. Then recreate: {svc_cmd}")
        elif self.stage == "env_written":
            self.say("  .env already holds the new values and the roles were changed: do not restore anything.")
            self.say(f"  Re-run the recreate: {svc_cmd}")
        else:
            self.say("  Services were recreated with the new values but verification failed: investigate "
                     "(docker compose logs <service>, docker compose ps) before rolling back.")
        if self.stage != "preflight" and new_bak.exists():
            self.say(f"  New values (plain text, 0600): {rel(new_bak)}")
        roles = []
        if any(s.name == "POSTGRES_PASSWORD" for s in chosen):
            roles.append(env.get("POSTGRES_USER", "<POSTGRES_USER>"))
        if any(s.name == "WINDMILL_DB_PASSWORD" for s in chosen):
            roles.append(env.get("WINDMILL_DB_USER", "windmill"))
        if self.stage != "preflight" and env_bak.exists():
            self.say("  Last resort - rollback:")
            self.say(f"    cp -p {rel(env_bak)} .env   (the OLD values)")
            if roles and self.stage != "backed_up":
                self.say(f"    ALTER ROLE back to the old values for: {', '.join(roles)} "
                         "(docker compose exec -T postgres psql -U <superuser> -d postgres, script on stdin; "
                         "see docs/security.md, \"Rotação de segredos\")")
            self.say(f"    then: {svc_cmd}")
        if sql_bak.exists():
            self.say(f"  Full dump: {rel(sql_bak)} (restore only if data is damaged)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Rotate default/static secrets (dry-run unless --apply)")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--apply", action="store_true", help="perform the rotation (default: dry-run)")
    ap.add_argument("--force-new-secrets", action="store_true",
                    help="ignore an unfinished earlier run (stale env-post-rotate-*) and generate new secrets")
    ap.add_argument("--only", help="comma list: " + ", ".join(ORDER) + " (QDRANT alias)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    env_path = root / ".env"
    if not env_path.is_file():
        print("no .env found; create it from .env.example first", file=sys.stderr)
        return 2
    chosen = parse_only(args.only)
    rot = Rotator(root, force_new=args.force_new_secrets)
    if args.apply:
        return rot.apply(chosen)       # catches everything itself and exits 1 with the hint
    try:
        env = read_env(env_path)
        # dry-run prints no values by construction; only long (real) ones are scrubbed as a
        # safety net so default words like 'windmill' do not mangle service names.
        rot.known = [v for k, v in env.items() if len(v) >= 12 and any(
            k in sp.env_keys + sp.optional_keys for sp in chosen)]
        rot.print_plan(rot.build_plan(chosen, env), apply=False)
    except Exception as e:      # noqa: BLE001
        rot.say(f"FAILED: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
