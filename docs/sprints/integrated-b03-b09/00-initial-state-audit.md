# Integrated Sprint (B-03 to B-09) — Stage 0 Initial State Audit

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Sprint Scope:** B-04 → B-05 → B-03 → B-06 → B-07 → B-08 → B-09
**Date:** 2026-11-26
**Audit Mode:** Read-only code, data, Git, and toolchain audit prior to B-04 execution

---

## 1. Repository & Git State (Directly Verified)

- **Primary workspace (`/home/excellence/NLGCP`):**
  - Active branch: `research/nlgcp-14-day-beta-sprint`
  - HEAD commit: `5b5217a0033191134effebe0027d4ee16f70de5f` (`Complete Day 7 audit, Phase 6/7 VRS sprint, and B-02 rover positioning benchmark`)
  - Remote `origin/main`: Pushed cleanly via Option 2 (`4b81f84..5b5217a`) from isolated worktree `/home/excellence/NLGCP-main`; `origin/main` and `origin/research/nlgcp-14-day-beta-sprint` both sit at `5b5217a`.
  - **Pre-existing uncommitted changes preserved untouched (Milestone B-00):**
    - Modified tracked files (`4`): `CURRENT_WORK.md`, `EVIDENCE_INDEX.md`, `PROJECT_STATUS.md`, `pyproject.toml`.
    - Untracked B-00 files: `docs/architecture/`, `docs/operations/`, `docs/project/`, `docs/research/{DATASET_CATALOGUE,EXPERIMENT_CATALOGUE,LIMITATIONS_REGISTER,PUBLICATION_EVIDENCE_MAP,VALIDATION_REGISTER}.md`, `docs/sprints/b00-research-archive/`, `research/archive/`, `research/research_archive/`, `scripts/run_research_archive.py`.
    - Safety backup verified intact at `/home/excellence/NLGCP-safety-backups/b00-before-main-consolidation/`.
  - **Preservation rule:** Do not overwrite, stage, commit, reset, or disturb any pre-existing B-00 work; all B-04..B-09 sprint work is written to non-conflicting files/directories unless explicitly reconciled later.

---

## 2. Implementation, Testing & Validation Audit by Component

| Component / Milestone | Implementation | Testing | Scientific / Independent Validation | Operational Status | Verified Source & Notes |
|---|---|---|---|---|---|
| **Phase 2 / Southern Recovery** | `IMPLEMENTED` | `UNIT_TESTED` (`research/southern_network_audit/tests/`) | `INTEGRATION_TESTED` (66/66 BKG 2011 nav; 220/220 2024 BRDC) | `NOT_APPROVED` | 2011 station coords remain `PROVISIONAL_OSGOF_2011_01_01`; 132 CDDIS attempts `AUTHENTICATION_REQUIRED`. |
| **Phase 3 Single-Base RTK** | `IMPLEMENTED` | `UNIT_TESTED` (`50` tests in `research/single_base_rtk/tests/`) | `INDEPENDENTLY_VALIDATED` (`rnx2rtkp v2.4.2-p13`, DOY 2024/026) | `NOT_APPROVED` | All baselines `FLOAT_ONLY` (`0.0%` FIX); `EKAK→PHRI` `105.553 km` `0.968/0.584/1.130 m` reproduced to 4 decimals in B-02. |
| **Phase 4 GNSS QC** | `IMPLEMENTED` | `UNIT_TESTED` (`43` tests) | `INTEGRATION_TESTED` (`3,870` 2024 profile evals) | `NOT_APPROVED` | Thresholds remain `PROVISIONAL`; only DOY `2024/026` admits 4 verified stations. |
| **Phase 5 Offline NRTK** | `IMPLEMENTED` | `UNIT_TESTED` (`44` tests) | `INDEPENDENTLY_VALIDATED` (DOY 026 pilot) | `NOT_APPROVED` | Nearest single reference beat multi-baseline mean (`0.968` vs `1.288 m`). |
| **Phase 6 Atmospheric & Spatial** | `IMPLEMENTED` | `UNIT_TESTED` (`research/atmospheric_spatial_model/tests/`) | `INDEPENDENTLY_VALIDATED` (UNB3m vs PRIDE ZTD `1.85 mm` ZHD; stratified LOOCV) | `BEST = ZERO` | Offline non-causal arc leveling; zero DCB/IONEX on disk; interior 2011 hull `+26.1%`–`+30.0%` (provisional coords); perimeter extrapolation `ZERO`-dominated. |
| **Phase 7 Experimental VRS** | `IMPLEMENTED` | `UNIT_TESTED` (`research/vrs_generator/tests/`) | `INDEPENDENTLY_VALIDATED` (RTKLIB + gLAB `1005` decode; B-02 positioning) | `VRS_GEOMETRY_ONLY` / `FORBIDDEN` | `ANCHOR_RELATIVE_FLOAT` (no network IAR); GPS `1005`+`1074` only; `experimental_vrs.py:517` ZWD bug fixed in B-02. |
| **Phase 8 Hybrid Decision** | `IMPLEMENTED` | `UNIT_TESTED` (`59` tests) | `INTEGRATION_TESTED` (reviewed DOY 026 pilot) | `NOT_APPROVED` | Blocks automatic VRS; falls back to single-base `EKAK00NGA`; Phase 8→11 runtime adapter absent (`BE-01`). |
| **Phase 9–10 Replay & Ingestion** | `IMPLEMENTED` | `UNIT_TESTED` (`74` Ph9 + `94` Ph10 Py + `30` Go tests) | `BLOCKED` (real streams) / `SYNTHETIC` (loopback) | `BLOCKED` | Zero authorized live/recorded Nigerian CORS RTCM streams on disk; Go ingestor runtime stream→NATS loop unwired (`BE-02`); HTTP server timeouts absent (`SEC-05`). |
| **Phase 11–12 RTCM & NTRIP** | `IMPLEMENTED` | `UNIT_TESTED` + `INTEGRATION_TESTED` (`127` Ph11 + `55` Ph12 tests) | `INDEPENDENTLY_VALIDATED` (synthetic `1005/1074/1084` via RTKLIB; gLAB `1005` only) | `SYNTHETICALLY_VALIDATED` / `FORBIDDEN` | Strictly `127.0.0.1` loopback; `NLGCP_TEST` synthetic + isolated `NLGCP_VRS_EXP`; standalone `1084` lacks GLONASS FCN; no non-RTKLIB MSM4 decoder (`pyrtcm` & `bnc` not installed). |
| **B-02 Rover Benchmark** | `IMPLEMENTED` | `UNIT_TESTED` (`13` tests; `12/12` Phase H) | `INDEPENDENTLY_VALIDATED` (`2024` verified IGS20 FLOAT); `TECHNICALLY_VALIDATED` (`2011` provisional) | `OPERATIONAL_APPROVED = FORBIDDEN` | `52/52` full-24h runs (`311` hashed artifacts under `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/`). `0.0%` genuine FIX (`7` false `Q=1` on 2011 non-iono). |
| **B-00 Research Archive** | `IMPLEMENTED` (uncommitted) | `UNIT_TESTED` (`9` tests) | Live SHA-256 verified (`18/18` datasets, `24/24` + `311/311` B-02 artifacts) | Governance / Provenance | Preserved uncommitted in `/home/excellence/NLGCP` for separate review/commit. |
| **Control Plane & Runtime Infra** | `SCAFFOLDED` | Basic health/CTest (`1/1`) | `NOT_PERFORMED` | `BLOCKED` | `apps/api/src/nlgcp_api/main.py` exposes only `GET /health` (13 lines); `services/nrtk-engine` is a C health executable; `services/station-monitor` is a README placeholder; `compose.yml` has `POSTGRES_PASSWORD=CHANGE_ME` and unauthenticated NATS/Redis (`SEC-06`). |

---

## 3. Installed GNSS Toolchains, Python Environment & External Data Inventory

- **RTKLIB `v2.4.2-p13`** (`/home/excellence/RTKLIB`, commit `71db0ffa…`): `rnx2rtkp` (`b4a96cd0…`), `convbin` (`b575f81e…`) installed in `/home/excellence/.local/bin/`.
- **PRIDE PPP-AR `3.2.8`** (`/home/excellence/PRIDE-PPPAR`, commit `4907bfe5…`): Full binary suite installed in `/home/excellence/.PRIDE_PPPAR_BIN/` (`pdp3`, `lsq`, `arsig`, `tedit`, `sp3orb`, `spp`, `redig`, `otl`, `pbopos`, `xyz2enu`, `config_template`), with local geodetic tables in `/home/excellence/PRIDE-PPPAR/table/` **including `igsR3_2135.atx`, `igs20.atx`, `igs20_2425.atx`, `igs14_2247.atx`, `igs08_1731.atx`, `gpt3_1.grd`, `FES2004S1.dat`, `Love_load_cm.dat`, `oceanload`, `leap.sec`, `sat_parameters`**.
  - Inspected `pdp3.sh` (lines 2283–2866, 3223, 3296): Built-in support for historical **2011 IGS Repro3 Final (`IGS2R03FIN` SP3/CLK/OBX/OSB + `COD0R03FIN` ERP)** from `ftp://igs.gnsswhu.cn/pub/whu/phasebias/2011/...` and **CODE IONEX (`CODG*.11I.Z`)** from `ftp://ftp.aiub.unibe.ch/CODE/2011/...`.
- **ESA/gAGE-UPC gLAB `6.0.0`** (`/opt/gLAB/gLAB_linux` `ca530155…`): Supports RTCM `1005` & CRC-24Q; MSM4 (`1074`/`1084`) unsupported.
- **Independent non-RTKLIB MSM4 Decoders:** Neither `pyrtcm` nor `bnc` (BKG BNC) is currently installed (`which bnc pyrtcm` empty; `.venv` has 51 packages, no `pyrtcm`, no `scipy`).
- **2011 NIGNET Archive (`/home/excellence/nlgcp-data/incoming/southern-nignet/NIGNET2011.zip`, SHA-256 `8ccb0045…`):**
  - All `9` priority stations (`ABUZ`, `BKFP`, `CGGT`, `FUTY`, `MDGR`, `OSGF`, `RUST`, `ULAG`, `UNEC`) verified `OK` across all `6` target windows (`2011-03-20` DOY `079`, `2011-03-21` DOY `080`, `2011-12-05` DOY `339`, `2011-12-06` DOY `340`, `2011-12-07` DOY `341`, `2011-12-08` DOY `342` — `54/54` files).
  - Receivers: `TRIMBLE NETR8` (v4.19/4.22) and `TRIMBLE NETR9` (v4.22, `MDGR` & `OSGF`).
  - Antennas: Uniform `TRM59800.00` (blank radome → `NONE`), `DELTA H/E/N = 0.1710 / 0.0000 / 0.0000 m`.
  - Known data defect from Phase 6 audit: `RUST` loses `L2`/`P2` in December 2011 (`DOY 339–342`); `P1=0%` across 2011 (uses `C1`/`P2`/`L1`/`L2`).
- **Local Precise & Ionospheric Products (`/home/excellence/nlgcp-data/external-products/`):**
  - `brdc/2024/`: `220` validated BKG/IGS BRDC files.
  - `igs/2024/`: Empty (`0` files — no external DCB/IONEX).
  - `igs/2011/`: Does not exist yet (target of Milestone **B-04**).

---

## 4. Known Defects, Blockers & Milestone Dependency Chain

1. **B-04 (FIRST — Coordinate Verification):** Must acquire legitimate public 2011 precise `SP3`/`CLK`/`ERP`/`OBX`/`OSB`/`ANTEX` products, run `PRIDE PPP-AR 3.2.8` across the 9 stations × 6 windows (`54` station-days), quantify multi-day repeatability & discrepancies vs. provisional OSGoF 2011-01-01 coordinates, and re-evaluate B-02 `2011-03-20 OSGF` truth in a new versioned output directory (preserving original B-02 untouched).
2. **B-05 (Atmospheric Model Enhancement):** Depends on B-04 verified coordinates + CODE DCB/IONEX availability; must deliver causal epoch-by-epoch atmospheric estimator vs. offline baseline, tropospheric comparisons, and stratified spatial validation retaining `ZERO`.
3. **B-03 (Network Integer Ambiguity Resolution):** Depends on B-04/B-05; must address `0.0%` genuine FIX and B-02's `7` false `Q=1` cases using conservative MW wide-lane + LAMBDA narrow-lane + independent validation (`FLOAT_ONLY` fail-closed if unreliable).
4. **B-06 (Multi-GNSS & RTCM Expansion):** Must audit authentic multi-GNSS signals, GLONASS FCN/`1020`/`1230`, antenna descriptors (`1006`/`1007`/`1008`/`1033`), and Galileo/BeiDou only where authentic observations/ephemerides exist.
5. **B-07 (Independent Protocol & Receiver Validation):** Must evaluate installing/integrating an independent non-RTKLIB MSM4 decoder (`pyrtcm` / BKG BNC / independent spec decoder) for semantic cross-decoding; hardware validation classified `BLOCKED_HARDWARE_ACCESS` without real receivers.
6. **B-08 (Backend Runtime Integration):** Must connect versioned event contracts, bounded NATS JetStream consumers, PostgreSQL/PostGIS schema migrations, expanded FastAPI `/api/v1` endpoints, and Phase 8→11 adapter while preserving all Day 7 `SEC-01`–`SEC-14` loopback boundaries.
7. **B-09 (Live CORS Integration):** Must assess Nigerian CORS providers including `https://www.sacredioncors.com/` (SOGPOS), implement Stage A credential-free recorded/client ingestion wired to B-08 contracts, and record `BLOCKED_EXTERNAL_ACCESS` for Stage B unless authorized credentials exist.
