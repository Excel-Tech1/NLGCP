# Database

PostgreSQL/PostGIS is the future authoritative store for station metadata and control-plane state. Phase 1 creates only PostGIS and a migration ledger. SQL files in `migrations/` run in lexical order when Docker initializes an empty volume; already-initialized volumes are not replayed. `seeds/` must never contain fabricated stations or observations.

Verify with `make health`. Phase 2 will select a migration tool before adding the station registry.
