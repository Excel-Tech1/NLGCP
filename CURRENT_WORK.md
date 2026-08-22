# Current Work

## Active Phase

Phase 1 — Engineering Foundation

## Current Milestone

Phase 1 Closure

## Status

Complete

## Completed

- Repository governance, documentation index, data policy, VS Code, CI, security, and handoff foundations established.
- FastAPI, Go, mixed C/C++, and Next.js foundations created and verified.
- PostgreSQL/PostGIS, NATS JetStream, Redis, API, and web services are running and healthy under Docker Compose.
- PostgreSQL/PostGIS health verified from the NLGCP Compose service.
- NATS JetStream health verified.
- Redis health verification corrected to target the NLGCP Compose service rather than the host Redis instance.
- API and frontend runtime health verified.
- Host port defaults aligned to avoid conflicts with existing system PostgreSQL and Redis services:
  - PostgreSQL: 15432
  - Redis: 16379
- `make health` passes for PostgreSQL/PostGIS, NATS/JetStream, Redis, API, Frontend, RTKLIB, and PRIDE PPP-AR.
- `make check` passes Ruff, mypy, pytest, Go formatting/vet/tests, CMake/CTest, ESLint, TypeScript, and Next.js production build.
- RTKLIB provenance resolved to the official RTKLIB repository, tag `v2.4.2-p13`, commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`; installed `rnx2rtkp` matches the source-tree build by SHA-256.
- PRIDE PPP-AR 3.2.8 provenance resolved to the official PrideLab repository at commit `4907bfe5ba1e9d9faf90414fcf7a2bed5ad44695`.
- PRIDE core `src/` contains no tracked modifications.
- Installed PRIDE compiled binaries match the source-tree `bin/` binaries by SHA-256.
- Installed `pdp3` wrapper exactly matches `scripts/pdp3.sh`.
- PRIDE runtime table updates were identified and hashed separately for reproducibility.

## In Progress

- Phase 1 closure commit.

## Not Started

- Phase 2 — Data Acquisition & Station Registry.
- Scientific GNSS implementation beyond the engineering foundation.

## Blocked

None for Phase 1.

## Known Issues

- Native Next.js SWC terminates with `Bus error` on this host; the verified production build currently uses the Next.js WASM compiler workaround.
- ESLint 9 is required by the current Next.js lint plugin chain but npm reports that major as unsupported; npm audit reports zero known vulnerabilities.
- PRIDE runtime tables may update independently of the pinned application source and therefore must be recorded with experiment provenance.

## Decisions Made

- Bootstrap remains in the existing `NLGCP` directory.
- GNSS tools remain external to the repository but must have pinned provenance recorded.
- Raw scientific GNSS data will remain outside Git and immutable.
- Phase completion remains evidence-based; compilation alone is not scientific validation.

## Next Action

Record final Phase 1 evidence, commit the verified engineering foundation changes, then proceed to Phase 2 — Data Acquisition & Station Registry. Do not begin Phase 3 automatically.

## Last Verified Commit

Current pre-closure HEAD: `a3371e7`.

## Last Updated

2026-08-22
