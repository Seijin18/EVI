-- Windmill RLS roles (https://www.windmill.dev/docs/advanced/self_host#use-an-external-database)
-- Run as superuser (evi) against database windmill.

CREATE ROLE windmill_user;

GRANT ALL ON ALL TABLES IN SCHEMA public TO windmill_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO windmill_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO windmill_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO windmill_user;

CREATE ROLE windmill_admin WITH BYPASSRLS;
GRANT windmill_user TO windmill_admin;

GRANT windmill_admin TO windmill;
GRANT windmill_user TO windmill;

GRANT USAGE ON SCHEMA public TO windmill_admin, windmill_user;
