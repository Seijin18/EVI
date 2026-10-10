"""Find (and with --apply delete) harness rows left in production tables.

Self-contained on purpose (stdlib + psycopg2, no `db`/`services` imports): the
wrapper pipes this file to `python -` inside the running container, so it works
even when the image predates it. Dry-run by default; `--apply` deletes inside a
single transaction and prints what it removed.
"""

from __future__ import annotations

import argparse
import os
import sys

# Mirrors services.turn_log.TEST_SESSION_PREFIXES (a unit test keeps them equal).
TEST_SESSION_PREFIXES = ("evi-test", "test-", "health-check", "tg-digest-verify")


def _like_any(column: str) -> str:
    return "(" + " OR ".join(f"{column} LIKE '{p}%'" for p in TEST_SESSION_PREFIXES) + ")"


# name -> (table, WHERE clause, sample columns "id, text")
TARGETS = {
    "turn_log": (
        "turn_log",
        "is_test = true",
        "id, user_text",
    ),
    "pending_commitments": (
        "pending_commitments",
        "source = 'evi-test' AND source_id LIKE 'tg-digest-verify-%'",
        "id, title",
    ),
    "messages": (
        "messages",
        _like_any("session_id"),
        "id, session_id || ': ' || content",
    ),
}


def _sample(text) -> str:
    return " ".join(str(text or "").split())[:60]


def run(conn, apply: bool = False, out=print) -> dict[str, int]:
    """List every target; with apply=True delete them in one transaction."""
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        present = set()
        for name, (table, _w, _c) in TARGETS.items():
            cur.execute("SELECT to_regclass(%s)", (table,))
            if cur.fetchone()[0] is not None:
                present.add(name)
        for name, (table, where, cols) in TARGETS.items():
            if name not in present:
                out(f"[{name}] table absent, skipped")
                counts[name] = 0
                continue
            cur.execute(f"SELECT count(*) FROM {table} WHERE {where}")
            counts[name] = int(cur.fetchone()[0])
            out(f"[{name}] {counts[name]} row(s)  WHERE {where}")
            cur.execute(f"SELECT {cols} FROM {table} WHERE {where} ORDER BY id LIMIT 5")
            for rid, text in cur.fetchall():
                out(f"    id={rid}  {_sample(text)}")
        if apply:
            for name, (table, where, _cols) in TARGETS.items():
                if name not in present:
                    continue
                cur.execute(f"DELETE FROM {table} WHERE {where}")
                out(f"DELETED {cur.rowcount} row(s) from {name}")
            conn.commit()
        else:
            conn.rollback()
            out("Dry run: nothing deleted (use --apply to delete).")
    return counts


def main(argv: list[str] | None = None) -> int:
    where_help = "\n".join(f"  {n}: DELETE FROM {t} WHERE {w}" for n, (t, w, _c) in TARGETS.items())
    ap = argparse.ArgumentParser(
        description="List harness/test rows in production tables; delete only with --apply.",
        epilog="Exact WHERE clauses:\n" + where_help,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--apply", action="store_true", help="delete the listed rows (transaction)")
    args = ap.parse_args(argv)
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    import psycopg2

    conn = psycopg2.connect(url)
    try:
        run(conn, apply=args.apply)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
