-- Phase 1 infrastructure migration. No station registry schema is created here.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version) VALUES ('001_enable_postgis')
ON CONFLICT (version) DO NOTHING;
