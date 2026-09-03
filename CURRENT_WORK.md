# Current Work

## Active Phase

Phase 3 — Single-Base RTK Baseline

## Current Milestone

Phase 3 Real Scientific Benchmark Execution and Reporting

## Status

Validation

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
- Phase 3 single-base RTK research package added under `research/single_base_rtk`.
- Phase 3 pipeline prepares external experiment directories under `${NLGCP_DATA_ROOT}/processed/single-base/<experiment-id>/`.
- Phase 3 scientific execution gate fails closed until verified Phase 2 inputs are available.
- RTKLIB provenance capture and binary SHA-256 matching are implemented before real execution.
- Synthetic parser/metric/gate tests are labelled and cannot support scientific results.
- `make check` passes after the Phase 3 scaffold additions.
- Phase 3 scientific correctness hardening completed:
  - input file existence/type and checksum verification fail closed;
  - `${NLGCP_DATA_ROOT}` must be configured, existing, and a directory;
  - blocked experiments do not report scientific-looking baselines when coordinate/reference-frame gates are unresolved;
  - RTKLIB base ECEF coordinate is explicit via source-verified `rnx2rtkp -r` and `ant2-postype=xyz`/`ant2-pos*`;
  - `.pos` parser is header-aware, reports malformed rows, maps RTKLIB quality codes, and fixes age/ratio indexing;
  - TTFF, fix-rate, solution-availability, and RMSE metrics now use timestamped solution epochs and expected epoch counts;
  - zero-valid-epoch and structural parser failures do not mark experiments complete;
  - material-input fingerprints prevent accidental experiment-id overwrite with different inputs;
  - NLGCP commit and dirty working-tree status are recorded in experiment manifests.

- Input SHA-256s wired through the pipeline (observation per-station, navigation broadcast) and enforced from the conversion manifest via the scientific execution gate.
- Real Phase 3 scientific benchmark executed for DOY 2024/026 with ABFC (ABFC00NGA) as base on all three ≥400 km baselines using source-verified RTKLIB `rnx2rtkp v2.4.2-p13`:
  - PHRI — 470.870 km, 100% availability, 2880 epochs, 6 sats, FLOAT-only, horiz RMSE 1.093 m / 3D 1.664 m / vert 1.254 m.
  - EKAK — 487.636 km, 100% availability, 2880 epochs, 6 sats, FLOAT-only, horiz RMSE 1.255 m / 3D 2.247 m / vert 1.864 m.
  - MGBO — 689.687 km, 100% availability, 2880 epochs, 6 sats, FLOAT-only, horiz RMSE 1.377 m / 3D 1.646 m / vert 0.901 m.
  - All three baselines were FLOAT-only (fix_rate 0.0); long-baseline ambiguity resolution did not converge, so no fixed-ambiguity accuracy is claimed.
- Experiment manifests record recorded/observed SHA-256 matches for all inputs plus config/material fingerprints, execution status, NLGCP commit, and dirty-tree state.
- Analysis finalised: baseline metrics and per-baseline aggregates written to `processed/single-base/_phase3-summary/`.
- Deliverables generated under `processed/single-base/`: 14 figures, tables (CSV/JSON/Markdown), `validation/reports/phase3-validation-report.md`, and `validation/reports/phase3-thesis-evidence.md`.
- `make check` Python portion green for the implementation: Ruff, mypy (30 source files, strict), pytest (46 passed), and the single-base test suite.

## In Progress

- Phase 3 validation-review wrap-up and milestone commit.

## Not Started

- Fixed-ambiguity single-base processing (requires a shorter baseline rover or denser station geometry).

## Blocked

None for the current Phase 3 baseline. Deriving a fixed-ambiguity (RTK-fixed) result on these ≥400 km baselines is limited by network geometry and not attempted here; that is a documented follow-on, not a defect in this baseline.

## Known Issues

- Native Next.js SWC terminates with `Bus error` on this host; the verified production build currently uses the Next.js WASM compiler workaround.
- ESLint 9 is required by the current Next.js lint plugin chain but npm reports that major as unsupported; npm audit reports zero known vulnerabilities.
- PRIDE runtime tables may update independently of the pinned application source and therefore must be recorded with experiment provenance.
- `tools/rtklib/README.md` had stale unresolved-provenance wording after Phase 1 closure; it has been updated to match recorded evidence.
- `make setup` initially hit an npm registry timeout fetching `ajv`; retrying `npm --prefix apps/web install` succeeded with zero vulnerabilities.
- `apps/web/tsconfig.tsbuildinfo` is generated by TypeScript/Next verification and was restored after checks.

## Decisions Made

- Bootstrap remains in the existing `NLGCP` directory.
- GNSS tools remain external to the repository but must have pinned provenance recorded.
- Raw scientific GNSS data will remain outside Git and immutable.
- Phase completion remains evidence-based; compilation alone is not scientific validation.
- Phase 3 may create dry-run artefacts with unavailable data, but may not run or claim metrics from real experiments until the Phase 2 gate is open.

## Next Action

Close out the Phase 3 real-benchmark milestone: commit the implementation, deliverables, and handoff. Review the FLOAT-only limitation on ≥400 km baselines as a follow-on and decide whether a shorter-baseline fixed-ambiguity demonstration is needed before proceeding to Phase 4.

## Last Verified Commit

Pending milestone commit on `phase3/single-base-scaffold` (base merged at `2fea34a`).

## Last Updated

2026-09-04
