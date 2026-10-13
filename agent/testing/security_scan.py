"""Read-only security scanner for the EVI repository (change evi-security-review).

Each check is a small function returning ``list[Finding]``. Evidence strings never
contain secret values: only names, counts, commit hashes and file paths.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# Routes that intentionally answer without the API key.
PUBLIC_ROUTES = {("GET", "/"), ("GET", "/health")}
# Reachable without a key but only informational; reported as WARN, not FAIL.
REVIEW_ROUTES = {("GET", "/metrics")}

WEAK_DEFAULTS = {
    "EVOLUTION_API_KEY": {"evi-dev-key", ""},
    "POSTGRES_PASSWORD": {"changeme", ""},
    "WINDMILL_DB_PASSWORD": {"windmill", ""},
}
SECRET_VAR_HINTS = ("KEY", "PASSWORD", "TOKEN", "SECRET")
KNOWN_DEFAULT_VALUES = {"evi-dev-key", "changeme", "windmill"}

HISTORY_PATTERN = (
    r"(sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,}|xox[bap]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|OPENROUTER_API_KEY=[A-Za-z0-9_-]{10,}"
    r"|GEMINI_API_KEY=[A-Za-z0-9_-]{10,}|TELEGRAM_BOT_TOKEN=[0-9]{6,}:[A-Za-z0-9_-]{20,})"
)
FORBIDDEN_TRACKED = (".env", "data/", "logs/", "EVI_WORKSPACE/MEMORY.md", "EVI_WORKSPACE/USER.md")

BLOCKING_S_RULES = {"S102", "S307", "S602", "S604", "S605", "S608"}
TRIVY_IMAGE = "aquasec/trivy:0.75.0"
TRIVY_CACHE_VOLUME = "evi-trivy-cache"


@dataclass
class Finding:
    id: str
    status: str
    title: str
    evidence: str


def parse_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.is_file():
        return env
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.removeprefix("export ").strip()] = v.strip().strip("'\"")
    return env


def _load_compose(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text()) or {}


def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, errors="replace"
    )


# ---------------------------------------------------------------- 1. binds
def _port_host(entry) -> Optional[str]:
    """Host IP of a compose ports entry; '' when unspecified (= all interfaces)."""
    if isinstance(entry, dict):
        return entry.get("host_ip", "") or ""
    parts = str(entry).split(":")
    if len(parts) >= 3:
        return parts[0].strip("[]")
    return ""


def check_binds(compose_path: Path) -> List[Finding]:
    out: List[Finding] = []
    services = _load_compose(compose_path).get("services") or {}
    bad, total = [], 0
    for name, svc in services.items():
        for entry in svc.get("ports") or []:
            total += 1
            if _port_host(entry) != "127.0.0.1":
                bad.append(f"{name} ({entry if not isinstance(entry, dict) else entry.get('published')})")
    if bad:
        out.append(Finding("binds.compose", FAIL, "Published ports bound to loopback",
                           "not on 127.0.0.1: " + ", ".join(bad)))
    else:
        out.append(Finding("binds.compose", PASS, "Published ports bound to loopback",
                           f"{total} published port(s), all 127.0.0.1"))
    return out


def parse_ss_listeners(text: str) -> List[str]:
    """Non-loopback listeners owned by docker-proxy from `ss -ltnpH` output."""
    hits = []
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 4 or "docker-proxy" not in line:
            continue
        local = cols[3]
        host = local.rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "::1"):
            hits.append(local)
    return hits


def check_host_listeners() -> List[Finding]:
    if not shutil.which("ss"):
        return [Finding("binds.host", SKIP, "Host listeners", "ss not available")]
    try:
        res = _run(["ss", "-ltnpH"], timeout=15)
    except Exception as exc:  # pragma: no cover
        return [Finding("binds.host", SKIP, "Host listeners", f"ss failed: {type(exc).__name__}")]
    hits = sorted(set(parse_ss_listeners(res.stdout)))
    if hits:
        return [Finding("binds.host", WARN, "Host docker-proxy listeners off loopback", ", ".join(hits))]
    return [Finding("binds.host", PASS, "Host docker-proxy listeners off loopback",
                    "none visible (ss may hide other users' processes)")]


# -------------------------------------------------------- 2. default secrets
def check_default_secrets(env_path: Path, compose_path: Optional[Path]) -> List[Finding]:
    out: List[Finding] = []
    if not env_path.is_file():
        out.append(Finding("secrets.env", SKIP, "Default secrets in .env", ".env not present"))
        env: Dict[str, str] = {}
    else:
        env = parse_env(env_path)
        bad = []
        for var, weak in WEAK_DEFAULTS.items():
            val = env.get(var, "")
            if val in weak or val.startswith("CHANGE_ME"):
                bad.append(f"{var} (default/empty)")
        key = env.get("EVI_API_KEY", "")
        if len(key) < 32:
            bad.append(f"EVI_API_KEY ({'empty' if not key else 'shorter than 32 chars'})")
        if env.get("EVI_REQUIRE_API_KEY", "").lower() != "true":
            bad.append("EVI_REQUIRE_API_KEY (not true)")
        if bad:
            out.append(Finding("secrets.env", FAIL, "Default/weak secrets in .env", "; ".join(bad)))
        else:
            out.append(Finding("secrets.env", PASS, "Default/weak secrets in .env", "none found"))

    qdrant_set = bool(env.get("QDRANT__SERVICE__API_KEY")) or bool(os.environ.get("QDRANT__SERVICE__API_KEY"))
    if qdrant_set:
        out.append(Finding("secrets.qdrant", PASS, "Qdrant API key", "QDRANT__SERVICE__API_KEY set"))
    else:
        out.append(Finding("secrets.qdrant", WARN, "Qdrant API key", "QDRANT__SERVICE__API_KEY unset (no auth)"))

    if compose_path is not None and compose_path.is_file():
        hard = set()
        for m in re.finditer(r"\$\{([A-Z0-9_]+):-([^}]*)\}", compose_path.read_text()):
            var, default = m.group(1), m.group(2)
            if any(h in var for h in SECRET_VAR_HINTS) and default in KNOWN_DEFAULT_VALUES:
                hard.add(var)
            elif var.endswith("PASSWORD") and default:
                hard.add(var)
        if hard:
            out.append(Finding("secrets.compose", WARN, "Hard-coded secret fallbacks in compose",
                               "defaults for: " + ", ".join(sorted(hard))))
        else:
            out.append(Finding("secrets.compose", PASS, "Hard-coded secret fallbacks in compose", "none"))
    return out


# ----------------------------------------------------------- 3. permissions
def check_file_perms(root: Path) -> List[Finding]:
    out: List[Finding] = []
    env = root / ".env"
    if env.exists():
        mode = stat.S_IMODE(env.stat().st_mode)
        if mode != 0o600:
            out.append(Finding("perms.env", FAIL, ".env mode 600", f".env is {mode:03o}"))
        else:
            out.append(Finding("perms.env", PASS, ".env mode 600", "600"))
    for name in ("data", "logs"):
        p = root / name
        if not p.exists():
            continue
        mode = stat.S_IMODE(p.stat().st_mode)
        if mode & stat.S_IWOTH:
            out.append(Finding(f"perms.{name}", FAIL, f"{name}/ not world-writable", f"{name}/ is {mode:03o}"))
        elif mode & (stat.S_IWGRP | stat.S_IROTH):
            out.append(Finding(f"perms.{name}", WARN, f"{name}/ not group-writable / world-readable",
                               f"{name}/ is {mode:03o}"))
        else:
            out.append(Finding(f"perms.{name}", PASS, f"{name}/ permissions", f"{mode:03o}"))
    if env.exists() and stat.S_IMODE(env.stat().st_mode) & stat.S_IROTH:
        out.append(Finding("perms.env_world", FAIL, ".env not world-readable", ".env readable by others"))
    return out


# ------------------------------------------------------------ 4. git history
def check_git(root: Path, max_seconds: int = 120) -> List[Finding]:
    out: List[Finding] = []
    if not (root / ".git").exists():
        return [Finding("git.history", SKIP, "Secrets in git history", "not a git repository")]
    try:
        ls = _run(["git", "ls-files"], cwd=root).stdout.splitlines()
        bad = sorted({
            f for f in ls
            for pat in FORBIDDEN_TRACKED
            if f == pat or (pat.endswith("/") and f.startswith(pat))
        })
        if bad:
            out.append(Finding("git.tracked", FAIL, "Forbidden files tracked", ", ".join(bad[:10])))
        else:
            out.append(Finding("git.tracked", PASS, "Forbidden files tracked", "none"))

        res = _run(["git", "log", "--all", "-G", HISTORY_PATTERN, "--format=%h", "--name-only",
                    "--diff-filter=AM"], cwd=root, timeout=max_seconds)
        # -G lists commits touching matching lines; confirm per commit/file via -p is costly,
        # so report commit+file candidates only (never the matched text).
        hits: Dict[str, List[str]] = {}
        cur = None
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            if re.fullmatch(r"[0-9a-f]{7,40}", line.strip()):
                cur = line.strip()
                hits.setdefault(cur, [])
            elif cur:
                hits[cur].append(line.strip())
        # Narrow candidates: files that really contain a match in that commit's diff.
        confirmed: List[str] = []
        rx = re.compile(HISTORY_PATTERN)
        for sha, files in hits.items():
            for f in files:
                if f.endswith((".lock",)):
                    continue
                p = _run(["git", "show", f"{sha}:{f}"], cwd=root, timeout=30)
                if p.returncode == 0 and rx.search(p.stdout):
                    confirmed.append(f"{sha}:{f}")
        if confirmed:
            out.append(Finding("git.history", FAIL, "Secret-like strings in git history",
                               f"{len(confirmed)} location(s): " + ", ".join(confirmed[:8])
                               + (" ..." if len(confirmed) > 8 else "")))
        else:
            out.append(Finding("git.history", PASS, "Secret-like strings in git history",
                               f"{len(hits)} candidate commit(s), 0 confirmed"))
    except subprocess.TimeoutExpired:
        out.append(Finding("git.history", WARN, "Secrets in git history", f"scan exceeded {max_seconds}s"))
    rewrite = root / ".git-rewrite"
    if rewrite.exists():
        out.append(Finding("git.rewrite", WARN, "Stale .git-rewrite directory", ".git-rewrite/ present (untracked)"))
    return out


# --------------------------------------------------------------- 5. ruff S
_RUFF_LINE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):\d+: (?P<code>S\d{3}) ")


def classify_ruff(output: str, root: Path) -> List[Finding]:
    counts: Dict[str, int] = {}
    blocking: List[str] = []
    for line in output.splitlines():
        m = _RUFF_LINE.match(line)
        if not m:
            continue
        code = m.group("code")
        counts[code] = counts.get(code, 0) + 1
        if code in BLOCKING_S_RULES:
            f = m.group("file")
            try:
                src = (root / f).read_text(errors="replace").splitlines()
                text = src[int(m.group("line")) - 1] if src else ""
            except OSError:
                text = ""
            # ruff honours bare noqa codes; require a justification when present
            if "noqa" in text and not re.search(r"noqa:\s*S\d+\s*[—-]\s*\S", text):
                blocking.append(f"{f}:{m.group('line')} {code} (noqa without reason)")
            elif "noqa" not in text:
                blocking.append(f"{f}:{m.group('line')} {code}")
    out: List[Finding] = []
    if blocking:
        out.append(Finding("ruff.blocking", FAIL, "Blocking ruff S rules",
                           f"{len(blocking)}: " + ", ".join(blocking[:8]) + (" ..." if len(blocking) > 8 else "")))
    else:
        out.append(Finding("ruff.blocking", PASS, "Blocking ruff S rules", "S102/S307/S602/S604/S605/S608: none"))
    other = {k: v for k, v in counts.items() if k not in BLOCKING_S_RULES}
    if other:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(other.items()))
        out.append(Finding("ruff.other", WARN, "Other ruff S findings", f"{sum(other.values())}: {summary}"))
    else:
        out.append(Finding("ruff.other", PASS, "Other ruff S findings", "none"))
    return out


def check_ruff(root: Path) -> List[Finding]:
    ruff = root / ".venv/bin/ruff"
    exe = str(ruff) if ruff.exists() else shutil.which("ruff")
    if not exe:
        return [Finding("ruff", SKIP, "ruff --select S", "ruff not installed")]
    res = _run([exe, "check", "agent/", "--select", "S", "--output-format", "concise", "--no-cache"],
               cwd=root, timeout=120)
    return classify_ruff(res.stdout, root)


# ------------------------------------------------------------ 6. dependencies
def classify_pip_audit(data: dict) -> List[Finding]:
    vulns = []
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            fixes = ",".join(v.get("fix_versions") or []) or "no fix"
            vulns.append((dep.get("name"), v.get("id"), fixes))
    if not vulns:
        return [Finding("deps.audit", PASS, "Known vulnerabilities (pip-audit)", "none")]
    # pip-audit JSON carries no severity; a fix being available makes it actionable -> FAIL.
    fixable = [v for v in vulns if v[2] != "no fix"]
    status = FAIL if fixable else WARN
    ev = "; ".join(f"{n} {i} (fix: {f})" for n, i, f in vulns[:10]) + (" ..." if len(vulns) > 10 else "")
    return [Finding("deps.audit", status, "Known vulnerabilities (pip-audit)", f"{len(vulns)}: {ev}")]


def check_dependencies(root: Path) -> List[Finding]:
    exe = root / ".venv/bin/pip-audit"
    exe_s = str(exe) if exe.exists() else shutil.which("pip-audit")
    req = root / "agent/requirements.txt"
    if not exe_s:
        return [Finding("deps.audit", SKIP, "pip-audit", "pip-audit not installed")]
    try:
        res = _run([exe_s, "-r", str(req), "--format", "json", "--progress-spinner", "off",
                    "--no-deps", "--disable-pip"], timeout=300)
    except subprocess.TimeoutExpired:
        return [Finding("deps.audit", SKIP, "pip-audit", "timed out")]
    try:
        data = json.loads(res.stdout)
    except ValueError:
        reason = (res.stderr.strip().splitlines() or ["no output"])[-1][:160]
        return [Finding("deps.audit", SKIP, "pip-audit", f"unavailable (network?): {reason}")]
    return classify_pip_audit(data)


# ---------------------------------------------------------------- 7. images
def _image_unpinned(image: str) -> bool:
    if "@sha256:" in image:     # a digest pins the exact build whatever the tag says
        return False
    ref = image.split("@")[0]
    last = ref.rsplit("/", 1)[-1]
    if ":" not in last:
        return True
    return last.split(":", 1)[1] in ("latest", "main", "master", "")


def compose_images(compose_path: Path) -> Dict[str, str]:
    return {n: s["image"] for n, s in (_load_compose(compose_path).get("services") or {}).items() if s.get("image")}


def check_images(compose_path: Path) -> List[Finding]:
    imgs = compose_images(compose_path)
    bad = sorted(f"{n}={i}" for n, i in imgs.items() if _image_unpinned(i))
    if bad:
        return [Finding("images.pinned", WARN, "Images pinned to a version", "unpinned: " + ", ".join(bad))]
    return [Finding("images.pinned", PASS, "Images pinned to a version", f"{len(imgs)} image(s) pinned")]


def check_trivy(compose_path: Path, root: Path) -> List[Finding]:
    if not shutil.which("docker"):
        return [Finding("images.trivy", SKIP, "Image CVEs (trivy)", "docker not available")]
    out: List[Finding] = []
    for image in sorted(set(compose_images(compose_path).values())):
        have = _run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], timeout=30)
        if have.returncode != 0:
            out.append(Finding(f"images.trivy.{image}", SKIP, f"Trivy {image}", "image not pulled locally"))
            continue
        try:
            res = _run(["docker", "run", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock:ro",
                        "-v", f"{TRIVY_CACHE_VOLUME}:/root/.cache", TRIVY_IMAGE, "image",
                        "--severity", "HIGH,CRITICAL", "--quiet", "--format", "json", image], timeout=900)
            data = json.loads(res.stdout or "{}")
        except (subprocess.TimeoutExpired, ValueError):
            out.append(Finding(f"images.trivy.{image}", SKIP, f"Trivy {image}", "scan failed or timed out"))
            continue
        hi = cr = 0
        for r in data.get("Results") or []:
            for v in r.get("Vulnerabilities") or []:
                if v.get("Severity") == "CRITICAL":
                    cr += 1
                elif v.get("Severity") == "HIGH":
                    hi += 1
        status = FAIL if cr else (WARN if hi else PASS)
        out.append(Finding(f"images.trivy.{image}", status, f"Trivy {image}", f"CRITICAL={cr} HIGH={hi}"))
    return out


# ------------------------------------------------------------ 8. route auth
_HTTP = {"get", "post", "put", "delete", "patch", "head", "options"}
AUTH_DEP = "verify_api_key"


def _depends_on_auth(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Depends":
            if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == AUTH_DEP:
                return True
    return False


def parse_routes(source: str) -> List[dict]:
    routes = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in _HTTP and dec.args
                    and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str)):
                routes.append({"method": dec.func.attr.upper(), "path": dec.args[0].value,
                               "auth": _depends_on_auth(node), "line": node.lineno})
    return routes


def check_routes(main_path: Path) -> List[Finding]:
    if not main_path.is_file():
        return [Finding("routes.auth", SKIP, "Routes require API key", f"{main_path.name} not found")]
    src = main_path.read_text()
    routes = parse_routes(src)
    if not routes:
        return [Finding("routes.auth", FAIL, "Routes require API key", "no routes parsed")]
    # Auth is per-route Depends(verify_api_key); a router include would bypass the scan.
    if re.search(r"include_router\(", src):
        return [Finding("routes.auth", FAIL, "Routes require API key",
                        "include_router used: scanner cannot verify auth of included routes")]
    open_ = [r for r in routes if not r["auth"]]
    unlisted = [r for r in open_ if (r["method"], r["path"]) not in PUBLIC_ROUTES | REVIEW_ROUTES]
    review = [r for r in open_ if (r["method"], r["path"]) in REVIEW_ROUTES]
    stale = sorted(f"{m} {p}" for m, p in PUBLIC_ROUTES
                   if not any(r["method"] == m and r["path"] == p and not r["auth"] for r in routes))
    out: List[Finding] = []
    if unlisted:
        out.append(Finding("routes.auth", FAIL, "Routes require API key",
                           "unauthenticated, not public: " + ", ".join(f"{r['method']} {r['path']}" for r in unlisted)))
    else:
        out.append(Finding("routes.auth", PASS, "Routes require API key",
                           f"{len(routes)} routes, {len(routes) - len(open_)} authenticated, "
                           f"{len(open_) - len(review)} public"))
    if review:
        out.append(Finding("routes.review", WARN, "Unauthenticated informational routes",
                           ", ".join(f"{r['method']} {r['path']}" for r in review)))
    if stale:
        out.append(Finding("routes.allowlist", WARN, "PUBLIC_ROUTES entries not matching a public route",
                           ", ".join(stale)))
    return out


# --------------------------------------------------------------------- main
def run_all(root: Path, images: bool = False) -> List[Finding]:
    compose = root / "docker-compose.yml"
    results: List[Finding] = []
    if compose.is_file():
        results += check_binds(compose)
    results += check_host_listeners()
    results += check_default_secrets(root / ".env", compose if compose.is_file() else None)
    results += check_file_perms(root)
    results += check_git(root)
    results += check_ruff(root)
    results += check_dependencies(root)
    if compose.is_file():
        results += check_images(compose)
        if images:
            results += check_trivy(compose, root)
    results += check_routes(root / "agent/main.py")
    return results


def render_table(findings: List[Finding]) -> str:
    w = max(len(f.id) for f in findings) if findings else 4
    lines = [f"{f.status:<5} {f.id:<{w}}  {f.title} — {f.evidence}" for f in findings]
    c = {s: sum(1 for f in findings if f.status == s) for s in (PASS, WARN, FAIL, SKIP)}
    lines.append(f"\nSummary: PASS={c[PASS]} WARN={c[WARN]} FAIL={c[FAIL]} SKIP={c[SKIP]}")
    return "\n".join(lines)


def render_markdown(findings: List[Finding]) -> str:
    rows = ["| Status | Check | Evidence |", "|---|---|---|"]
    for f in findings:
        rows.append(f"| {f.status} | `{f.id}` {f.title} | {f.evidence.replace('|', '/')} |")
    return "\n".join(rows)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="EVI read-only security scan")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--images", action="store_true", help="also run trivy on locally pulled images (slow)")
    args = ap.parse_args(argv)
    findings = run_all(Path(args.root), images=args.images)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    elif args.markdown:
        print(render_markdown(findings))
    else:
        print(render_table(findings))
    return 1 if any(f.status == FAIL for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
