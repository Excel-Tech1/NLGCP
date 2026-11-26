# B-00 Stage Zero — Initial Repository, Data, and Environment Audit

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-00 — Research Archive, Data Provenance and Reproducibility Foundation
**Date:** 2026-11-26
**Audit Mode:** Strictly read-only (zero files moved, modified, renamed, or deleted)

---

## 1. Repository State (Git)

- **Repository root:** `/home/excellence/NLGCP`
- **Active branch:** `research/nlgcp-14-day-beta-sprint`
- **HEAD commit:** `5b5217a0033191134effebe0027d4ee16f70de5f` (`Complete Day 7 audit, Phase 6/7 VRS sprint, and B-02 rover positioning benchmark`)
- **Prior sprint lineage:** `5b5217a` → `0cea5ba` (Day 6) → `459143e` (Days 4–5) → `8d10f30` (Days 1–3; `origin/research/nlgcp-14-day-beta-sprint`, local ahead by 3 commits)
- **Working tree at audit start:** Clean (`0` staged, `0` unstaged, `0` untracked)
- **Remote (`origin`):** `https://github.com/Excel-Tech1/NLGCP.git` (read-only inspection; unmodified)
- **Relevant project branches (`16` total):** `main` (`4b81f84`), `staging` (`6174ceb`), `phase3/single-base-scaffold` (`4ab8d26`), `phase4/gnss-qc-station-health` (`b18b814`), `phase5/offline-network-rtk` (`9c47203`), `phase6/atmospheric-spatial-error-model` (`0e358eb`), `phase67/scientific-validation-geometry-hardening` (`5225ff8`), `phase7/vrs-generator` (`59c986a`), `phase8/hybrid-correction-decision-engine` (`6bef6da`), `phase9/recorded-rtcm-replay` (`2e1b031`), `phase10/live-cors-ntrip-ingestion` (`63f86a7`), `pre-cors/phase10-hardening-phase11-scaffold` (`5b97939`), `interim/scientific-expansion` (`46b90f3`), `research/southern-nigeria-data-audit` (`b50230b`), `research/southern-coordinate-provenance-navigation-recovery` (`d789da0`), and `research/nlgcp-14-day-beta-sprint` (`5b5217a`).

---

## 2. Existing Documentation Inventory

| Directory / File | Count / Contents | Observed Status |
|---|---|---|
| Root governance & status | `AGENTS.md`, `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`, `CONTRIBUTING.md`, `SECURITY.md`, `README.md` | Active; authoritative history through B-02 |
| `docs/technical-baseline/v1.0/` | 24 core specs (incl. `23-research-experiment-and-reproducibility-plan.md`), 12 ADRs (`ADR-001`..`ADR-012`, incl. `ADR-009` immutable raw archive & `ADR-011` fail-closed integrity), 6 diagrams, 5 runbooks, 2 schemas | Authoritative architectural baseline v1.0 |
| `docs/research/` | 13 research reports: Southern Nigeria audit & nav recovery (`2`), Phase 6/7 atmospheric & VRS sprint (`7`), B-02 rover benchmark (`4`) | Active; no central catalogues/registers yet |
| `docs/sprints/14-day-beta-sprint/` | 14 sprint deliverables (`01`–`14`, Days 1–7 incl. backend architecture audit, 14-finding security review, readiness matrix & tracker) | Active |
| `docs/phase*.md` & `docs/thesis/` | Phase 2, 6, 7, 6/7 review, 8, 9, 10, 11 specs + `docs/thesis/scientific-expansion-2024-evidence.md` | Active |
| `research/*/PILOT_EVIDENCE.*` | 7 module-level pilot evidence summaries (`network_rtk`, `atmospheric_spatial_model`, `vrs_generator` MD+JSON, `hybrid_decision_engine`, `rtcm_replay`, `ntrip_ingestion`) | Active, decentralized |
| `docs/project/`, `docs/operations/`, `docs/architecture/`, `docs/sprints/b00-research-archive/` | **Do not yet exist** | To be created in B-00 without altering existing docs |

---

## 3. External Research Data Inventory (`/home/excellence/nlgcp-data`, ~23 GiB)

| Directory | Observed Size | Contents & Provenance State |
|---|---:|---|
| `incoming/southern-nignet/` | `5.5 GiB` | `NIGNET2011.zip` (`5,820,369,120 B`, SHA-256 `8ccb0045…44fcf`, 3,018 RINEX 2.11 files, 11 stations, 2011-01-01..2011-12-31, `PROVISIONAL` OSGoF coords; immutable) |
| `00-deliveries/osgof-2024/batch-001/` | `1.3 GiB` | Original OSGoF 2024 RINEX delivery (immutable) |
| `raw/nignet/2024/` | `1.3 GiB` | Canonicalized 2024 raw RINEX archive (`1,290` canonical station-days across 8 stations, 294 observed days; indexed by `manifests/canonical-raw-archive-2024.json` & `manifests/files.csv`) |
| `external-products/brdc/2024/` | `267 MiB` | `220` validated BKG/IGS merged broadcast nav files (`BRDC00IGS_R_2024*.rnx.gz`, incl. DOY 026 SHA `a6418387…`) |
| `external-products/igs/2024/` | Empty (`0` files) | Subdirs (`biases`, `clocks`, `erp`, `ionosphere`, `precise-orbits`) exist but hold **zero files** — external DCB/IONEX/2011 SP3 absent |
| `manifests/` | `852 KiB` | `canonical-raw-archive-2024.json` (`4f97149b…`), `files.csv` (`1,291` rows, `84436be1…`), endpoint check logs (`miranet`/`nignet` web checks, NOT casters) |
| `metadata/` | `84 KiB` | Station/equipment/coordinate source metadata |
| `working/` | `14 GiB` | QC-converted 2024 RINEX (`working/qc-converted/2024/{PHRI,EKAK,ABFC,MGBO}00NGA/026/*.24O`), PRIDE PPP-AR 3.2.8 runs (`pos_2024026_phri`, `ztd_2024026_*`, `WUM0MGXRAP_20240260000_01D_05M_ORB.SP3`), synthetic Phase 9/10 fixtures (`rtcm-replay-fixtures/`, `ntrip-pilot-synthetic/`) |
| `processed/` | `498 MiB` | Phase 3 (`single-base/`, 6 baselines + `derived-coordinates.json`), Phase 4 (`qc/`), Phase 5 (`network-rtk/`), Phase 6 (`atmospheric-model/` `geometry-v3` + `sprint-phase67/`), Phase 7 (`vrs/` `geometry-v3` + `sprint-phase67/` 2 RTCM streams), Phase 8 (`hybrid-decisions/`), Phase 9 (`rtcm-replay/`), **B-02 (`rover-benchmark/b02/`, 311 hashed artifacts)** |
| `validation/` | `68 MiB` | `scientific-expansion-2024/`, `southern-nignet/run-20261030T125136Z/` (audit), `southern-nignet/coordinate-navigation-recovery/run-20261123T163056Z/` (`66` validated BKG 2011 GPS+GLONASS nav files incl. `brdc0790.11n.Z` `52cc6c9b…`, OSGoF `coordinate_provenance.csv` `e48cd164…`) |
| `quarantine/` | `20 KiB` | Quarantine subdirectories (`corrupt`, `duplicate`, `incomplete`, `unknown`) |

---

## 4. Existing Experiment Inventory

Observed historical research experiments with on-disk outputs and/or repository evidence:
1. **Phase 2 / Southern Nigeria Recovery & 2024 Scientific Expansion:** 2024 canonical archive + 220 BKG BRDC (`scientific-expansion-2024`); 2011 NIGNET archive audit (`run-20261030T125136Z`); 2011 BKG navigation recovery (`run-20261123T163056Z`, 66/66 BKG validated, 132 CDDIS `AUTHENTICATION_REQUIRED`).
2. **Phase 3 Single-Base RTK Benchmark + Control:** `sb-2024d026-{abfc,ekak,mgbo}-*` (`6` baselines, DOY 2024/026, all FLOAT-only; `EKAK→PHRI` 105.553 km `0.968/0.584/1.130 m`).
3. **Phase 4 GNSS QC Engine:** Full 2024 canonical dataset (`1,290` sessions × `3` profiles = `3,870` evaluations; only DOY 026 admits 4 `network_rtk` ACCEPT stations; thresholds `PROVISIONAL`).
4. **Phase 5 Offline Network RTK:** `net-2024d026-phri-rover` (`3` baselines, nearest single ref beats network mean).
5. **Phase 6 Atmospheric Modelling (Pilot `geometry-v3` + Multi-Day Sprint):** `atm-2024d026-phri-target-geometry-v3` (supersedes pre-review `atm-2024d026-phri-target`; `zero` wins `3.076 m`, all 4 folds extrapolation) and `sprint-phase67` multi-day stratified LOOCV (`+26.1%` to `+30.0%` interior hull gains on 2011 provisional data; UNB3m vs PRIDE ZTD `1.85 mm` ZHD RMSE, `12.6 cm` coastal-vs-Harmattan ZWD contrast).
6. **Phase 7 VRS Synthesis (Pilot `geometry-v3` + Experimental VRS Sprint):** `vrs-2024d026-{phri,abfc,ekak,mgbo}-geometry-v3` (supersedes unversioned/`v1`/`v2`; `ZERO / VRS_GEOMETRY_ONLY`) and `sprint-phase67` observation-based experimental VRS + RTCM `1005/1074` + `NLGCP_VRS_EXP` + gLAB `1005` cross-decoder.
7. **Phase 8 Hybrid Decision Engine:** `pilot-d026-phri-{auto,vrs-only,single-base-only}` (`AUTO` → `SINGLE_BASE` EKAK fallback; VRS blocked).
8. **Phase 9 Recorded RTCM Replay:** Synthetic framework pilot (`run-a..run-e`; `REAL PILOT = BLOCKED`).
9. **Phase 10 Live CORS Ingestion:** Synthetic loopback pilot (`loopback-001`; `REAL LIVE INGESTION = BLOCKED`).
10. **Phase 11 RTCM 1005/1074/1084 Generation:** Synthetic encoders verified against RTKLIB `convbin` + native `input_rtcm3()` (`SYNTHETICALLY_VALIDATED`).
11. **Phase 12 Local Loopback NTRIP + Day 6 Integration Assurance:** Loopback `NLGCP_TEST` (`10/10` stages, 55 tests, synthetic-only).
12. **Day 7 Backend Architecture & Security Audit:** 14 classified security findings (`SEC-01`..`SEC-14`: 2 CRITICAL, 4 HIGH, 4 MEDIUM, 3 LOW, 1 INFO).
13. **Milestone B-02 Offline Rover Positioning Benchmark (2024 PHRI verified + 2011 OSGF interior):** `52` full-24h (`2,880` ep) RTKLIB runs, `311` hashed artifacts, `12/12` fail-closed failure checks, `0.0%` genuine FIX (`7` false fixes exposed), zero rover leakage via epoch-0 SPP GGA virtual ARP.

---

## 5. Existing Provenance Capabilities & Archive Tooling

- **Existing module-local provenance helpers:** `research/{atmospheric_spatial_model,hybrid_decision_engine,rtcm_replay,ntrip_ingestion,rtcm_generation}/src/*/provenance.py`, `research/rover_benchmark/src/nlgcp_rover_benchmark/{models,rtklib_pipeline,benchmark}.py`, `scripts/phase2/build_data_manifest.py`, and `apps/api/src/nlgcp_api/{data_manifest,rinex_inventory}.py`.
- **Existing CLI convention:** Standalone Python runners under `scripts/run_*.py`; `pyproject.toml` currently has **no** `[project.scripts]` section (`nlgcp` CLI entry point does not yet exist).
- **Existing schema conventions:** Strict typed Python `dataclasses` + `StrEnum` + sorted-key JSON manifests (`pyproject.toml` enforces strict `mypy` and `ruff`); `PyYAML==6.0.3` is already installed in `.venv` for YAML interoperability if needed.

---

## 6. Software & Execution Environment (Directly Verified)

| Component | Verified Version / Revision | Path / Provenance |
|---|---|---|
| OS / Kernel / Arch | Ubuntu 24.04 Linux `7.0.0-28-generic` `x86_64` | Host `elora` |
| Python | `3.12.3` (`.venv`, 51 installed packages incl. `PyYAML 6.0.3`, `numpy 2.5.3`, `matplotlib 3.11.1`, `fastapi 0.141.1`, `pytest 8.4.2`, `mypy 1.20.2`, `ruff 0.16.4`) | `/home/excellence/NLGCP/.venv/bin/python` |
| Go / Node / npm | Go `1.25.6`, Node `v20.20.2`, npm `10.8.2` | Host toolchains |
| C/C++ / Build | GCC/G++ `13.3.0`, CMake `3.28.3` | Host toolchains |
| Docker / Compose | Docker `29.4.3` (`055a478`), Compose `v2.5.0` | Host daemon |
| **RTKLIB** | `v2.4.2-p13`, commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807` | `/home/excellence/RTKLIB`; `rnx2rtkp` SHA `b4a96cd0…4f7d21`; `convbin` SHA `b575f81e…08e278` |
| **PRIDE PPP-AR** | `3.2.8`, commit `4907bfe5ba1e9d9faf90414fcf7a2bed5ad44695` | `/home/excellence/PRIDE-PPPAR`; `/home/excellence/.PRIDE_PPPAR_BIN/pdp3` SHA `9e526f55…ccb7` (matches `scripts/pdp3.sh`) |
| **ESA/gAGE-UPC gLAB** | `6.0.0` (C source + `gLAB_linux` binary; RTCM 1005/CRC-24Q only, MSM4 unsupported) | `/opt/gLAB/gLAB_linux` SHA `ca530155…31eb8`; `input.c` SHA `16fd82ea…6bfb62` |

---

## 7. Gaps and Risks

1. **Fragmented provenance:** Datasets, experiments, hashes, and `PILOT_EVIDENCE` summaries live across 12 separate directories with no unified cross-referencing registry or single verification CLI.
2. **Missing central project & operations registers:** `docs/project/`, `docs/operations/`, and research catalogues/publication evidence maps do not exist yet.
3. **Partial historical reproducibility:** Early experiments (e.g., Phase 3/4/5/6/7) were executed from feature branches/worktrees whose exact runtime CLI invocations or environment snapshots were not all archived uniformly; some precise products (`WUM*CLK`/`BIA`/`ERP` from 2024 PRIDE runs) were cleaned/transformed by PRIDE inside `working/pride/` while `ORB.SP3` persists.
4. **External storage dependency:** ~23 GiB of datasets and experiment outputs live outside Git under `/home/excellence/nlgcp-data`; archive verification must degrade honestly (`ACCESS_DENIED` / exit `3` or `MISSING`) when external storage is unavailable rather than claiming verification.

---

## 8. Proposed Implementation Plan

1. **Architecture (`Stage One`):** Document the archive architecture (`docs/architecture/b00_research_archive_architecture.md`) and data model (`docs/architecture/b00_archive_data_model.md`) aligned with `research/` packages and `docs/technical-baseline/v1.0/docs/23-research-experiment-and-reproducibility-plan.md`.
2. **Package & CLI (`Stages Two–Five, Eight, Ten`):** Implement `research/research_archive/src/nlgcp_research_archive/` (`models`, `validator`, `hash_verifier`, `provenance`, `registry`, `cli`), `scripts/run_research_archive.py`, and `[project.scripts]` `nlgcp` CLI entry point with strict read-only verification and exit codes `0/1/2/3`.
3. **Schemas & Real Population (`Stages Two–Six, Nine, Ten`):** Populate `research/archive/{schema,datasets,experiments,artifacts,provenance,validation,reproducibility}/` strictly from directly observed files, hashes, and historical reports — including all negative findings, Day 7 `SEC-01`..`SEC-14`, and priority B-02 PHRI + OSGF records.
4. **Central Documentation (`Stage Seven`):** Author `docs/project/*`, `docs/research/{DATASET_CATALOGUE,EXPERIMENT_CATALOGUE,VALIDATION_REGISTER,LIMITATIONS_REGISTER,PUBLICATION_EVIDENCE_MAP}.md`, and `docs/operations/*` directly grounded in the machine-readable archive.
5. **Testing, Verification & Handover (`Stages Eleven–Twelve`):** Write comprehensive unit, CLI, and safety tests; verify against live `/home/excellence/nlgcp-data`; run full `make check`; write `10-b00-archive-completeness-report.md` and `final-b00-handover.md`; stop before any commit or push.

---

## 9. Files and Directories Preserved Untouched

All existing `docs/technical-baseline/v1.0/`, `docs/research/*`, `docs/sprints/14-day-beta-sprint/*`, `research/*` packages and `PILOT_EVIDENCE.*`, `services/*`, `apps/*`, `tools/*`, and **every single file** under `/home/excellence/nlgcp-data` (`incoming/`, `00-deliveries/`, `raw/`, `external-products/`, `processed/`, `working/`, `validation/`) remain in place and untouched.
