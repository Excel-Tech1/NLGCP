# Current Work

## Active Phase

Phase 8 — Hybrid Correction Decision Engine (implemented on
`phase8/hybrid-correction-decision-engine`; real DOY 026 pilot COMPLETE;
automatic VRS remains BLOCKED pending the independent Phase 6/7
scientific review)

## Current Milestone

Phase 8 Implementation and Real-Data Pilot

## Status

Engineering + real pilot COMPLETE (Phase 8 decision request/response
models, VRS/single-base/no-correction paths, fail-closed gates, reason
codes, versioned policy, provenance/fingerprints, traces, CLI, and
Phase 9 handoff implemented with 52 synthetic-only tests and a
derived-from-evidence DOY 026 pilot)

## Completed (Phase 8)

- Hybrid decision package added under
  `research/hybrid_decision_engine` (`nlgcp_hybrid_decision`:
  models, policy, discovery, network, single_base, vrs, integrity,
  provenance, decision, reporting) consuming Phase 4 QC, verified
  coordinates, and navigation evidence without duplicating Phase 4/5/6
  functionality; stable `SpatialCorrectionAssessment` / Phase 7
  `VRSCapabilityAssessment` contracts isolate Phase 8 from the
  parallel unreviewed Phase 7 implementation.
- Fail-closed hierarchy validated-VRS → single-base fallback → no
  correction with `AUTO` / `VRS_ONLY` / `SINGLE_BASE_ONLY` routing,
  stable reason codes, transparent `PASS`/`DEGRADED`/`BLOCKED`
  integrity (no numeric scores), watermarked `DIAGNOSTIC_ONLY` mode,
  versioned policy `v1.0` (3-reference floor; PROVISIONAL distance
  bands: preferred ≤150 km, degraded ≤500 km, maximum ≤1100 km),
  full provenance and decision fingerprinting, human-readable traces,
  machine-readable outputs plus `CorrectionDecisionPhase9` handoff,
  and CLI `scripts/run_hybrid_decision.py`
  (`inspect`/`plan`/`decide`/`explain`/`summarize`, `--dry-run`).
- 52 synthetic-only Phase 8 tests
  (`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`);
  `pyproject.toml` registers the new package, tests, and script.
- Real pilot 2024 DOY 026 at PHRI00NGA (pre-review defaults: Phase 6
  `UNAVAILABLE`, Phase 7 `NOT_VALIDATED`): `AUTO` → `SINGLE_BASE`/`OK`
  via EKAK00NGA (105.553 km, fallback, `SINGLE_BASE_SELECTED`,
  VRS blocked `VRS_UPSTREAM_REVIEW_PENDING`); `VRS_ONLY` →
  `NO_CORRECTION`/`BLOCKED`; `SINGLE_BASE_ONLY` → `SINGLE_BASE` via
  EKAK00NGA. Held-out AUTO probes: ABFC → PHRI 470.870 km `DEGRADED`,
  EKAK → PHRI 105.553 km `OK`, MGBO → ABFC 689.687 km `DEGRADED`.
  Outcomes derived by the engine from observed evidence, not
  hard-coded. Evidence in
  `research/hybrid_decision_engine/PILOT_EVIDENCE.md`; outputs under
  `${NLGCP_DATA_ROOT}/processed/hybrid-decisions/` (outside Git).
- No scientific validity manufactured: no VRS-superiority,
  centimetre-accuracy, validated-network-model, fixed-ambiguity, or
  production-availability claims. Automatic VRS stays BLOCKED until
  reviewed Phase 6/7 evidence is integrated (JSON assessments,
  fingerprint-invalidated).

## Completed (Phase 6)

- Atmospheric/spatial modelling package added under
  `research/atmospheric_spatial_model` (`nlgcp_atmospheric_model`:
  models, observations, combinations, satellite_geometry, ionosphere,
  troposphere, spatial, interpolation, validation, metrics, provenance,
  pipeline, reporting) reusing Phase 5 admission/geometry and Phase 4 QC
  fingerprints without duplication; documented observation model in
  `docs/phase6-atmospheric-spatial-model.md` (code/carrier equations,
  single/double differences, GPS L1/L2 geometry-free combination with
  IS-GPS-200 frequencies, Saastamoinen/Niell troposphere, symbols, units,
  IGS20 frame, GPST/UTC conventions, limitations, references).
- Fail-closed admission requires the Phase 5 experiment admission
  (ACCEPT-only stations), verified IGS20 coordinates, and present RINEX
  files; RTKLIB `.pos` satellite fields declared unavailable with the
  reason recorded — satellite observables are extracted from RINEX 2.11
  observation files with exact line-consumption parsing (blank lines
  inside satellite blocks are structural; regression-tested).
- Deterministic observable discovery (per-station codes/constellations/
  satellites/epochs, common codes, GPS L1/L2 compatibility) and the
  common-epoch/common-satellite engine with per-epoch statistics (no
  interpolation across missing observations).
- GPS broadcast-geometry layer (RINEX 3 merged BRDC, IS-GPS-200 Kepler,
  recorded nav hash, fail-closed non-GPS/missing records) and the
  standard-atmosphere tropospheric a priori chain (Berg/Saastamoinen/
  Niell, labelled not measured meteorology).
- Arc-detrended geometry-free SD proxies with stride-aware gap handling
  (gaps open new arcs, never rejoin), LLI-change segmentation (static
  PHRI L2 LLI=4 converter annotation documented with full-cycle
  evidence), and 0.5 m GF-jump protection; datum-anchored spatial
  records (datum self-differences identically zero); target-fit
  reference sets exclude the target (no leakage).
- Interpolation candidates zero/nearest/IDW/planar with method minimums
  (no kriging: 3 references cannot support it) and extrapolation flags;
  identical-sample LOOCV over all 4 rotations with bias/MAE/RMSE/std/
  correlation/coverage; pilot RMS-vs-distance decorrelation labelled
  representative-only.
- CLI `scripts/run_atmospheric_model.py` (`inspect`, `plan`, `derive`,
  `fit`, `validate`, `summarize`) with dry-run support and
  machine-readable output; fingerprint-gated resumability; tables
  (baseline matrix, LOOCV summary, decorrelation), figures
  (LOOCV RMSE, decorrelation, common-satellite availability), and
  cross-experiment summary CSVs.
- 76 synthetic-only Phase 6 tests (parsing incl. blank-line alignment,
  common selection, GF reference values, arc rules, geometry, tropo,
  interpolation, LOOCV, provenance, pipeline admission, reporting);
  `pyproject.toml` registers the new package, tests, and script.
- Real pilot `atm-2024d026-phri-target` (stride 6, 180 s): derive
  COMPLETE (480 common epochs; median 16 common sats, 9 GPS L1/L2;
  100% usable; pair-SD RMS 4.18 m over ±25 m; tropo 20848 terms),
  fit COMPLETE (21656 predictions, 21095 fitted), validate COMPLETE
  (17768 identical samples; zero RMSE 2.984 m beats IDW 3.546,
  nearest 4.004, planar 15.300; decorrelation slope 0.59 mm/km,
  corr 0.48, pilot-only). Nearest-reference non-improvement and the
  zero-control win are reported, not hidden. Evidence in
  `research/atmospheric_spatial_model/PILOT_EVIDENCE.md`; outputs under
  `${NLGCP_DATA_ROOT}/processed/atmospheric-model/` (outside Git).
- Six implementation defects found by the real pilot and fixed with
  regression tests (parser alignment, stride-aware arcs, gap/LLI rules,
  fit leakage, datum anchoring, identical-sample ranking); buggy-run
  products deleted and regenerated under new fingerprints.

## Completed (Phase 5)

- Offline network RTK package added under `research/network_rtk`
  (`nlgcp_network_rtk`: models, admission, geometry, overlap, baselines,
  residuals, metrics, runner, summarize, io) reusing Phase 3 RTKLIB/solution
  infrastructure and Phase 4 QC outputs without duplication.
- Fail-closed admission requires Phase 4 `network_rtk` ACCEPT (diagnostic
  runs explicitly labelled); records station, DOY, paths, QC profile/status,
  reject/block reasons, hashes, Phase 4 fingerprints, metadata provenance,
  equipment, sampling interval, and time coverage.
- Network minimum documented and enforced: 3 admitted reference stations
  (triangle/polygon floor for later Phase 6 modelling); geometry adequacy
  assessed separately.
- Deterministic geometry (baseline matrix, centroid, ref-to-rover distances,
  nearest/farthest/mean, extent, triangle area) from verified coordinates only.
- Common-epoch overlap from actual first/last epochs (no whole-day assumption).
- Per-baseline RTKLIB execution (`rnx2rtkp v2.4.2-p13`, recorded SHA) labelled
  as network INPUT/baseline solutions; residual dataset with unavailable
  satellite fields documented as null; aggregate metrics labelled NOT VRS.
- CLI `scripts/run_network_rtk.py` (`discover`, `plan`, `validate`, `run`,
  `summarize`) with dry-run support and machine-readable output.
- Fingerprint-gated resumability; bounded (≤8) parallel workers with
  order-deterministic outputs; unexpected failures isolated from
  REJECT/BLOCKED science states.
- 44 synthetic-only Phase 5 tests (admission, geometry, overlap, metrics,
  runner, determinism, reproducibility); `pyproject.toml` registers the new
  package, tests, and script for Ruff/mypy/pytest.
- Real-data discovery: only DOY 026 admits ≥3 `network_rtk` sessions
  (ABFC/EKAK/MGBO/PHRI); all other 2024 days BLOCKED with reasons.
- Real pilot `net-2024d026-phri-rover` executed: 3/3 baselines COMPLETE,
  100% availability, 8640 epochs (ABFC→PHRI FLOAT-only 1.093/1.664 m
  reproducing Phase 3; EKAK→PHRI FLOAT-only 0.968/1.130 m reproducing the
  control; MGBO→PHRI 1029 km with 2 isolated FIX epochs, effectively
  FLOAT-only 1.802/2.598 m). Nearest single reference outperforms the
  network-input mean: no improvement claimed. Evidence summary in
  `research/network_rtk/PILOT_EVIDENCE.md`; full outputs under
  `${NLGCP_DATA_ROOT}/processed/network-rtk/` (outside Git).

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

- Phase 8 branch verification (`make check`) and merge preparation. Do
  not begin Phase 9 (recorded RTCM replay, live ingestion, RTCM
  generation, NTRIP) in this task. Do not merge unreviewed Phase 7 or
  the Phase 6/7 review branch.

## Phase 5 Integration Record (2026-09-07)

- Merged latest `main` (Phase 4 closure `345646d`) into
  `phase5/offline-network-rtk` (merge `9c47203`; Phase 5 commit `8976de3`
  retained unamended): Phase 4 closure code, README, and closure evidence
  preserved; Phase 5 implementation, pilot definition, and pilot evidence
  preserved; status docs reconciled.
- Merged `phase5/offline-network-rtk` into `main` with `git merge --no-ff`
  (merge `9a2d870`); post-merge `make check` green on `main`.
- Final authoritative state: Phase 4 engineering COMPLETE, Phase 4 2024
  validation COMPLETE, Phase 4 scientific thresholds PROVISIONAL;
  Phase 5 engineering COMPLETE, Phase 5 real-data pilot COMPLETE,
  Phase 5 scientific scope representative DOY 026 only (no general NRTK
  improvement proven or claimed).

## Phase 4 Validation Closure (2026-09-07)

- Full 2024 canonical QC run executed against `${NLGCP_DATA_ROOT}` (`/home/excellence/nlgcp-data`): 1290 canonical observation sessions, 8 stations, 3 profiles, 3870 profile results, 0 unexpected processing failures.
- Archive: ACCEPT 694, WARN 596, REJECT 0, BLOCKED 0. Single-base RTK: ACCEPT 4, WARN 0, REJECT 341, BLOCKED 945. Network RTK: ACCEPT 4, WARN 0, REJECT 341, BLOCKED 945.
- Navigation coverage: 7 navigation-covered sessions; 1283 navigation-blocked RTK sessions. RTK BLOCKED denotes missing required external evidence/dependency (strongly associated with limited navigation/product coverage), not software failure. RTK REJECT denotes observed-data QC failure, not missing navigation.
- RTK-profile dataset: 371 partial/severely truncated sessions, 263 major-gap sessions, 1 excluded exact duplicate (EKAK DOY 200), 4 explicit aliases resolved (BIKE->BKFP, YLAD->FUTY, LGLA->ULAG, ENEN->UNEC).
- Only DOY 026 provides a four-station ACCEPT-only network overlap (ABFC00NGA, EKAK00NGA, MGBO00NGA, PHRI00NGA).
- External product inventory: `external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz` (IGS merged broadcast navigation via BKG archive) with recorded acquisition provenance and SHA-256 `a64183872be90e6052bd2d8e6aed43b59b897abd81a5636a36911c24c1aa7b2b`.
- Fixed the validation-report Known Limitations inconsistency: the report generator (`research/gnss_qc/src/nlgcp_gnss_qc/aggregate.py`) now derives the provenance sentence deterministically from the catalogued product inventory instead of hard-coding that provenance is unrecorded. Added 5 aggregation tests (provenance present/missing, no fabrication, empty inventory, determinism); QC suite passes (43 tests).
- Regenerated all three profile summaries; canonical report at `/home/excellence/nlgcp-data/validation/reports/phase4-gnss-qc-validation-report.md` with per-profile tables (9 CSVs) and figures (4 SVGs) under `/home/excellence/nlgcp-data/processed/qc/profiles/<profile>/{tables,figures}`.
- Phase 4 engineering milestone: COMPLETE. Phase 4 real 2024 QC run: COMPLETE. Phase 4 profile calibration status: PROVISIONAL (thresholds version 1.0; calibration against reviewed Nigerian field evidence is a documented follow-on validation requirement, not claimed here).

## Phase 5 Integration Record (2026-09-07)

- Merged latest `main` (Phase 4 closure `345646d`) into
  `phase5/offline-network-rtk`: Phase 4 closure code (`aggregate.py`
  provenance fix, 5 aggregation tests), README, and closure evidence rows
  preserved; Phase 5 implementation, pilot definition, and pilot evidence
  preserved; status docs reconciled to carry both lines.

## Not Started

- Fixed-ambiguity single-base processing (requires a shorter baseline rover or denser station geometry; the 105 km control remains FLOAT-only, confirming the reference-geometry constraint on this dataset).
- Phase 7 VRS generation; live RTCM/NTRIP work (explicitly out of scope for Phase 6).

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

Run `make check` on the Phase 8 branch, then merge to `main`. Then wait
for Phase 6/7 scientific validation, integrate reviewed upstream
evidence, and proceed to Phase 9.

## Consolidation Record (2026-09-07)

- Aborted a stale in-progress merge of historical `phase3/single-base-scaffold` (`4ab8d26`) into `main`; verified byte-identical Phase 3 preservation in the Phase 4 line (`git diff 4ab8d26 26c7d25` empty for `research/single_base_rtk/`, `scripts/run_single_base_rtk.py`, `validation/`, `pyproject.toml`; only Phase 2 additions + doc headers differ).
- Merged only `phase4/gnss-qc-station-health` into `main` with `git merge --no-ff` (zero conflicts): `main` now contains Phase 1 + Phase 2 + Phase 3 + Phase 4 code on one authoritative line.
- Historical `phase3/single-base-scaffold` retained as reference; `phase4/gnss-qc-station-health` retained as merge source. Old worktrees `~/NLGCP-phase3`, `~/NLGCP-phase4` pending removal approval.
- Phase 4 milestone commits on the merged line: `fdf7ab6` (QC + station-health engine) and `b18b814` (parallel/resumable dataset QC).
- `main` `.venv` synced via declared deps only (`.venv/bin/python -m pip install -e '.[dev]'`); `pyproject.toml` already declared `numpy`/`matplotlib`, no new packages added to silence errors.

## Last Verified Commit

`main` merge `9a2d870` (Merge Phase 5 offline network RTK) atop Phase 4
closure `345646d` and Phase 5 commits `8976de3` + integration `9c47203`;
pilot `net-2024d026-phri-rover` outputs preserved; post-merge `make check`
green (see EVIDENCE_INDEX).

## Last Updated

2026-09-09 (Phase 8 implementation sprint)
