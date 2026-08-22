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
