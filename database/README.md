# Database

PostgreSQL/PostGIS is the authoritative structured store for NLGCP station metadata and control-plane state.

## Migration strategy

Phase 1 bootstraps a new PostgreSQL volume using SQL files under `database/migrations/`.

The Phase 1 bootstrap:

- enables PostGIS;
- creates the legacy `schema_migrations` ledger;
- records `001_enable_postgis`.

Docker initialization SQL runs only when PostgreSQL creates an empty data volume. It is not the mechanism for applying later schema changes to an existing database.

From Phase 2 onward, schema migrations are managed with Alembic.

Alembic configuration is stored in:

- `alembic.ini`
- `database/alembic/env.py`
- `database/alembic/versions/`

The existing Phase 1 database is represented by the empty Alembic baseline revision:

`8a8bd64d3102`

The initial Phase 2 station-registry migration is:

`45cf4a80f5ae`

It creates:

- `metadata_sources`
- `providers`
- `stations`
- `station_coordinates`
- `station_equipment`

The Phase 2 provider provenance migration is:

`5d50ff0e583d`

It adds:

- `metadata_sources.source_path`
- deterministic source identity uniqueness for importer idempotency
- `providers.metadata_source_id`

Station coordinates and equipment are stored as effective-dated historical records. Unknown scientific metadata must remain NULL rather than being fabricated.

Large GNSS observation files do not belong in PostgreSQL. They remain in the external data vault referenced by `NLGCP_DATA_ROOT`. PostgreSQL stores structured metadata, provenance, catalogue information, quality-control state, and relationships.

## Migration commands

Load the local environment before running Alembic:

    set -a
    source .env
    set +a

Inspect the current revision:

    .venv/bin/alembic current

Apply migrations:

    .venv/bin/alembic upgrade head

Inspect migration history:

    .venv/bin/alembic history

Downgrades should first be tested against a disposable database before being used against persistent environments.

## Data integrity

Do not place fabricated stations, coordinates, equipment records, or observations in `seeds/`.

Real station metadata must enter the authoritative registry through provenance-controlled Phase 2 acquisition/import workflows.

Raw GNSS data is immutable and remains outside the repository.
