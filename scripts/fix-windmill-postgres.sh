#!/usr/bin/env bash
# Idempotent fix when windmill DB exists but windmill_admin / windmill_user roles are missing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${EVI_POSTGRES_CONTAINER:-evi-postgres-1}"
PGUSER="${POSTGRES_USER:-evi}"

psql_as_evi() {
  docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$1"
}

echo "==> Ensuring windmill database and login role..."
psql_as_evi postgres <<'SQL' || true
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'windmill') THEN
    CREATE USER windmill WITH PASSWORD 'windmill';
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'windmill') THEN
    CREATE DATABASE windmill OWNER windmill;
  END IF;
END $$;
SQL

echo "==> Creating Windmill RLS roles (skip if already present)..."
psql_as_evi windmill <<'SQL'
DO $$ BEGIN CREATE ROLE windmill_user; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE windmill_admin WITH BYPASSRLS; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT ALL ON ALL TABLES IN SCHEMA public TO windmill_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO windmill_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO windmill_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO windmill_user;
GRANT windmill_user TO windmill_admin;
GRANT windmill_admin TO windmill;
GRANT windmill_user TO windmill;
GRANT USAGE ON SCHEMA public TO windmill_admin, windmill_user;
SQL

echo "==> Restarting Windmill containers..."
cd "$ROOT"
docker compose restart windmill-server windmill-worker

echo "==> Waiting for http://localhost:8001 ..."
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 http://localhost:8001/ 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then
    echo "OK: Windmill responded HTTP $code"
    exit 0
  fi
  sleep 2
done
echo "WARN: Windmill did not return 200 yet (last code: $code). Check: docker logs evi-windmill-server-1 --tail 30"
exit 1
