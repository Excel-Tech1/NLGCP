# Evidence Index

Only observed results belong here. Commands are reproducible from the repository root.

| Date | Phase | Contribution | Evidence | Result |
|---|---|---|---|---|
| 2026-08-22 | 1 | Workspace inspection | `rg --files`, `git status` | Empty workspace; no Git repository existed |
| 2026-08-22 | 1 | Host toolchain discovery | Version commands for Python, Go, GCC, CMake, Node, Docker, Compose | PASS: required host toolchains discovered and subsequently verified through project quality gates |
| 2026-08-22 | 1 | Local quality gate | `make check` | PASS: Ruff, mypy, pytest (1), Go test/vet/format, CTest (1), ESLint, TypeScript, and Next.js production build |
| 2026-08-22 | 1 | Compose syntax | `docker compose config --quiet` | PASS |
| 2026-08-22 | 1 | JavaScript dependency audit | `npm install` audit summary | PASS: 0 known vulnerabilities |
| 2026-08-22 | 1 | Secret pattern scan | `rg` over repository excluding generated dependency trees | PASS: no credentials or private keys found |
| 2026-08-22 | 1 | RTKLIB provenance | official source checkout, Git tag/commit, SHA-256 comparison | PASS: `rnx2rtkp` matches RTKLIB `v2.4.2-p13` commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807` |
| 2026-08-22 | 1 | PRIDE PPP-AR provenance | official source checkout, Git commit, source/binary SHA-256 comparison | PASS: PRIDE PPP-AR 3.2.8 deployment matches source checkout at commit `4907bfe5ba1e9d9faf90414fcf7a2bed5ad44695` |
| 2026-08-22 | 1 | Live Compose health | `make health` | PASS: PostgreSQL/PostGIS, NATS/JetStream, Redis, API, Frontend, RTKLIB, and PRIDE PPP-AR HEALTHY |
| 2026-08-24 | 2 | P2-S1 station metadata importer unit tests | `.venv/bin/python -m pytest` | PASS: 18 tests, including 12 station metadata importer tests using synthetic-only fixtures |
| 2026-08-24 | 2 | P2-S1 Python lint and typing | `.venv/bin/python -m ruff check .`; `.venv/bin/python -m mypy` | PASS: Ruff clean; mypy clean across 14 source files |
| 2026-08-24 | 2 | Compose syntax | `NLGCP_DATA_ROOT=/tmp/nlgcp-data docker compose config --quiet` | PASS |
| 2026-08-24 | 2 | Diff whitespace integrity | `git diff --check` | PASS |
| 2026-08-24 | 2 | Local quality gate | `make check` | PASS: Ruff, mypy, pytest (26), Go tests, CMake/CTest, ESLint, TypeScript, and Next.js production build |
| 2026-08-24 | 2 | P2-S2 RINEX inventory unit tests | `.venv/bin/python -m pytest apps/api/tests/test_rinex_inventory.py` | PASS: 4 synthetic-only tests covering RINEX 3 observation, gzip RINEX 2 navigation, unsupported `.Z` report-only handling, and deterministic JSON output |
| 2026-08-24 | 2 | Phase 2 expanded Python suite | `.venv/bin/python -m pytest`; `.venv/bin/python -m ruff check .`; `.venv/bin/python -m mypy` | PASS: 22 tests; Ruff clean; mypy clean across 16 source files |
| 2026-08-24 | 2 | P2-S3 data manifest unit tests | `.venv/bin/python -m pytest apps/api/tests/test_data_manifest.py` | PASS: 4 synthetic-only tests covering duplicate checksum detection, conflicting-path reporting, malformed RINEX warning propagation, and deterministic output |
| 2026-08-24 | 2 | Phase 2 expanded Python suite | `.venv/bin/python -m pytest`; `.venv/bin/python -m ruff check .`; `.venv/bin/python -m mypy` | PASS: 26 tests; Ruff clean; mypy clean across 18 source files |
