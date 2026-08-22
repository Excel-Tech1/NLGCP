# Evidence Index

Only observed results belong here. Commands are reproducible from the repository root.

| Date | Phase | Contribution | Evidence | Result |
|---|---|---|---|---|
| 2026-08-22 | 1 | Workspace inspection | `rg --files`, `git status` | Empty workspace; no Git repository existed |
| 2026-08-22 | 1 | Host toolchain discovery | Version commands for Python, Go, GCC, CMake, Node, Docker, Compose | Toolchains present; full verification pending |
| 2026-08-22 | 1 | Local quality gate | `make check` | PASS: Ruff, mypy, pytest (1), Go test/vet/format, CTest (1), ESLint, TypeScript, and Next.js production build |
| 2026-08-22 | 1 | Compose syntax | `docker compose config --quiet` | PASS |
| 2026-08-22 | 1 | JavaScript dependency audit | `npm install` audit summary | PASS: 0 known vulnerabilities |
| 2026-08-22 | 1 | Secret pattern scan | `rg` over repository excluding generated dependency trees | PASS: no credentials or private keys found |
| 2026-08-22 | 1 | RTKLIB availability | `rnx2rtkp --help` | PASS: executable responds; exact upstream build provenance unresolved |
| 2026-08-22 | 1 | PRIDE PPP-AR availability | `pdp3 --version` | PASS: version 3.2.8 executable responds; installation provenance unresolved |
| 2026-08-22 | 1 | Live Compose health | `docker compose up -d --build` | BLOCKED: images downloaded, then Docker daemon became unresponsive; service health not claimed |
