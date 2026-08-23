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
| 2026-08-23 | 3 | RTKLIB availability/provenance precheck | `which rnx2rtkp`; `rnx2rtkp -h`; `sha256sum $(command -v rnx2rtkp)` | PASS: `/home/excellence/.local/bin/rnx2rtkp` present; help probe responds with no-input diagnostic; SHA-256 `b4a96cd0d5ffc00b44dab3a4fda214318c9f69cccee52128aec8bc26ad4f7d21` |
| 2026-08-23 | 3 | Phase 3 scaffold quality gate | `make check` | PASS: Ruff, mypy, pytest (5), Go vet/tests, CMake/CTest, ESLint, TypeScript, and Next.js production build |
| 2026-08-23 | 3 | RTKLIB option/source verification for hardening | inspected `/home/excellence/RTKLIB` at tag `v2.4.2-p13`, commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`; `app/rnx2rtkp/rnx2rtkp.c`; `src/options.c`; `src/solution.c`; `src/rtklib.h` | PASS: verified `-ts/-te/-ti`, `-r x y z`, `ant2-postype/ant2-pos*`, `out-timeform`, `out-height`, `stats-eratio1`, `.pos` LLH column order, and SOLQ quality codes |
| 2026-08-23 | 3 | Phase 3 hardening focused tests | `.venv/bin/python -m pytest research/single_base_rtk/tests` | PASS: 15 synthetic tests |
| 2026-08-23 | 3 | Phase 3 hardening style/type/diff checks | `.venv/bin/python -m ruff check .`; `.venv/bin/python -m mypy`; `git diff --check` | PASS |
| 2026-08-23 | 3 | Phase 3 hardening full quality gate | `make check` | PASS: Ruff, mypy, pytest (16), Go vet/tests, CMake/CTest, ESLint, TypeScript, and Next.js production build |
