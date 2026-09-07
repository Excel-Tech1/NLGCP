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

### Follow-on shorter-baseline control sprint (on `phase3/single-base-scaffold`)

- Verified-baseline matrix logic added to `src/nlgcp_single_base/control.py` (pure/testable): eligibility filtering by `scientifically_valid` + verified ECEF, unordered-pair matrix, shortest-available selection, distance ranking, `control_shortest_available`/`milestone_long_baseline` source tagging, faithful comparison-row assembly that never coerces an unattained FIX into a TTFF value.
- Only 4 of 8 stations are scientifically valid with verified IGS20/PRIDE coords (ABFC, EKAK, MGBO, PHRI); BKFP invalid, UNEC/FUTY/ULAG no coordinate entry. Six eligible unordered pairs; shortest available = **EKAK-PHRI 105.553 km**.
- Ran the control experiment EKAK->PHRI (105.553 km) on DOY 2024/026 with the identical RTKLIB `rnx2rtkp v2.4.2-p13` configuration: `execution_status=complete`, gates open, rc=0 (29.6 s), 2880/2880 epochs, 100% availability, **FLOAT-only (fix_rate 0.0, TTFF not achieved)**, horiz RMSE 0.968 m, vert RMSE 0.584 m, 3D RMSE 1.130 m.
- Control shows materially better accuracy than the 470-690 km baselines (horiz 0.968 vs 1.09-1.38 m; vert 0.584 vs 0.90-1.86 m) while confirming FLOAT-only persists even at the shortest verified baseline: the FLOAT-only outcome is a property of the single-base broadcast-ephemeris configuration across the verified range, not an artefact of the very-long baselines.
- Multi-day extension is a **hard limitation**: only DOY 026 has converted sessions + broadcast nav in the real-data enclave; no other day was converted (documented, not substituted).
- Comparative deliverables regenerated from stored manifests under `processed/single-base/`: `tables/{baseline-matrix,baseline-comparison,rmse-comparison,fix-float-comparison,blocked-experiments}.*`, `_phase3-summary/followon-comparison.json`, and figures `fig{3,4,5,6,7,8}*` plus `sb-2024d026-ekak-phri-static-{status-timeline,enu-residuals}.png`.
- `validation/reports/phase3-validation-report.md` extended with **Addendum A — Shorter-Baseline Control Experiment**; original milestone sections 1-25 unchanged.
- Added `tests/test_control.py` (10 tests) covering matrix/eligibility/ranking/tagging/FLOAT-preservation; `make check` Python portion green: Ruff (all checks passed), mypy (32 source files, strict), pytest (50 passed).

## In Progress

- Phase 4 GNSS QC and station-health validation on `main` (engine merged; recorded real-data QC validation run still pending).
- Phase 3 follow-on validation push and closure (historical reference on `phase3/single-base-scaffold`; content preserved in `main` via the Phase 4 line).

## Not Started

- Fixed-ambiguity single-base processing (requires a shorter baseline rover or denser station geometry; the 105 km control remains FLOAT-only, confirming the reference-geometry constraint on this dataset).

## Blocked

None for the current Phase 3 baseline. Deriving a fixed-ambiguity (RTK-fixed) result on these ≥400 km baselines is limited by network geometry and not attempted here; that is a documented follow-on, not a defect in this baseline. Multi-day extension is a hard limitation: only DOY 026 has converted sessions + broadcast nav in the real-data enclave.

## Known Issues

- Native Next.js SWC terminates with `Bus error` on this host; the verified production build currently uses the Next.js WASM compiler workaround.
- ESLint 9 is required by the current Next.js lint plugin chain but npm reports that major as unsupported; npm audit previously reported zero known vulnerabilities.
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

Run the recorded Phase 4 real-data QC validation (`scripts/run_gnss_qc.py dataset` against the canonical 2024 manifest under `${NLGCP_DATA_ROOT}`) and record the evidence; do not mark Phase 4 Complete on code existence alone. Do not begin Phase 5 automatically.

## Consolidation Record (2026-09-07)

- Aborted a stale in-progress merge of historical `phase3/single-base-scaffold` (`4ab8d26`) into `main`; verified byte-identical Phase 3 preservation in the Phase 4 line (`git diff 4ab8d26 26c7d25` empty for `research/single_base_rtk/`, `scripts/run_single_base_rtk.py`, `validation/`, `pyproject.toml`; only Phase 2 additions + doc headers differ).
- Merged only `phase4/gnss-qc-station-health` into `main` with `git merge --no-ff` (zero conflicts): `main` now contains Phase 1 + Phase 2 + Phase 3 + Phase 4 code on one authoritative line.
- Historical `phase3/single-base-scaffold` retained as reference; `phase4/gnss-qc-station-health` retained as merge source. Old worktrees `~/NLGCP-phase3`, `~/NLGCP-phase4` pending removal approval.
- Phase 4 milestone commits on the merged line: `fdf7ab6` (QC + station-health engine) and `b18b814` (parallel/resumable dataset QC).
- `main` `.venv` synced via declared deps only (`.venv/bin/python -m pip install -e '.[dev]'`); `pyproject.toml` already declared `numpy`/`matplotlib`, no new packages added to silence errors.

## Last Verified Commit

`main` merge `de40037` (Phase 4 GNSS QC and station health); `make check` green (Ruff, mypy 58 files strict, pytest 120 passed, Go, CTest, ESLint, tsc, Next.js build).

## Last Updated

2026-09-07
