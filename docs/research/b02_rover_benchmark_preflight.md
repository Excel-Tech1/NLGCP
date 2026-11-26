# B-02 Offline Rover Positioning Benchmark — Preflight Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-02 — Offline Rover Positioning Benchmark for Experimental VRS Corrections
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint` (HEAD `0cea5ba`, parent `459143e`, grandparent `8d10f30`)
**Status:** `TECHNICALLY_VALIDATED` (preflight inventory verified directly on disk; no raw files modified)

---

## 1. Repository & Git Preflight State

- **Active directory:** `/home/excellence/NLGCP`
- **Active branch:** `research/nlgcp-14-day-beta-sprint`
- **Commit history preserved:** `0cea5ba` (`Complete Day 6 synthetic integration assurance`) → `459143e` (`Complete Phase 12 local synthetic NTRIP service`) → `8d10f30` (`Secure NLGCP Day 1-3 RTCM engineering checkpoint`; `origin/research/nlgcp-14-day-beta-sprint` remains at `8d10f30`).
- **Uncommitted working-tree state preserved intact:**
  - Day 7 uncommitted audit reports (`docs/sprints/14-day-beta-sprint/{12,13,14}-day7-*.md`).
  - Phase 6 & 7 sprint modules, tests, scripts, and 7 research reports (`docs/research/phase6_7_*.md`, `phase6_*.md`, `phase7_*.md`).
  - Zero prior reports, generated `.rtcm3` files, or raw datasets were modified or removed.

---

## 2. Installed RTKLIB & GNSS Tool Inventory (Verified Directly)

| Executable / Source | Path | Verified Provenance / SHA-256 | Empirical Capability Finding |
|---|---|---|---|
| `rnx2rtkp` (RTKLIB v2.4.2-p13) | `/home/excellence/.local/bin/rnx2rtkp` | `b4a96cd0d5ffc00b44dab3a4fda214318c9f69cccee52128aec8bc26ad4f7d21` (matches Phase 1 pinned binary) | Supports `single`, `dgps`, `kinematic`, `static`, `l1+l2`, `pos1-ionoopt` (`off`/`brdc`/`dual-freq`), `pos1-tropopt` (`off`/`saas`), `pos2-armode` (`off`/`continuous`/`instantaneous`/`fix-and-hold`). **Empirically verified NOT to consume raw `.rtcm3` directly** (`error : station pos computation`); requires `convbin` RINEX conversion. |
| `convbin` (RTKLIB v2.4.2-p13) | `/home/excellence/.local/bin/convbin` | `b575f81ead50bd94184364d7b5d828874878737dc527c849ff751137ac08e278` | Decodes NLGCP RTCM `1005 + 1074` streams into RINEX 3.02 (`C1C, L1C, S1C, C2P, L2P, S2P`) preserving RTCM 1005 `APPROX POSITION XYZ` and GPS epochs cleanly. |
| RTKLIB source tree | `/home/excellence/RTKLIB` | Git commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807` (`v2.4.2-p13`) | Verified option enums in `src/options.c`. |
| PRIDE PPP-AR 3.2.8 | `/home/excellence/.PRIDE_PPPAR_BIN/` | Prior 2024 DOY 026 solutions on disk (`pos_2024026_*`, `ztd_2024026*`) | Verified 2024 IGS20 coordinates with formal cofactors and ambiguity-fix counts exist for all 4 admitted 2024 stations. |

---

## 3. Existing Input Data & Artifact Audit

### 3.1 Existing Phase 7 Experimental VRS RTCM Streams (Preserved Untouched)

| File (outside Git) | Size | Content | Preflight Probe Result |
|---|---:|---|---|
| `/home/excellence/nlgcp-data/processed/vrs/sprint-phase67/vrs_2024_01_26_phri_exp.rtcm3` | `3,914 B` | 31 frames (`1×1005 + 30×1074`), `stride=4` (120 s), 00:00–00:58 UTC | `convbin` → `30` epochs; `rnx2rtkp` produced real `Q=2` (FLOAT) positions, **but** 120 s VRS spacing exceeded RTKLIB default `pos2-maxage = 30 s`, causing alternating drops to `Q=5` (SINGLE) at 00:01:00 / 00:01:30. |
| `/home/excellence/nlgcp-data/processed/vrs/sprint-phase67/vrs_2011_03_20_osgf_exp.rtcm3` | `4,045 B` | 31 frames (`1×1005 + 30×1074`), `stride=4` (120 s), 00:00–00:58 UTC | Same 120 s cadence limitation for kinematic RTK Kalman filtering. |

**Key Preflight Engineering Decision:** Preserve the existing `sprint-phase67/*.rtcm3` files completely untouched, and generate dedicated **full-24-hour 30-second (`stride=1`, `2,880` epochs)** authentic RTCM `1005 + 1074` streams under `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/` for every benchmark variant so that `age = 0.0 s` at every rover epoch and the comparison with the `30.0 s` physical anchor RINEX is 100% fair.

### 3.2 Authentic GNSS Observations, Navigation & Coordinate Truth Availability

| Dataset | Rover Candidate | References (Withheld Rover Excluded) | Nav Product on Disk | Coordinate Truth Status | Missing Dependencies |
|---|---|---|---|---|---|
| **Dataset B: `2024-01-26` (DOY 026)** | `PHRI00NGA` (`PHRI0260.24O`, 2,880 ep, 30 s) | `ABFC00NGA`, `EKAK00NGA` (`105.553 km` anchor), `MGBO00NGA` (extrapolated: outside 3-ref hull) | `external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz` (`a6418387…`) | **`VERIFIED_IGS20_PRIDE_PPP_AR`** (`pos_2024026_phri`, 45 fixed GPS amb, formal `σ_X/Y/Z = 0.55 / 0.16 / 0.13 mm`, IGS20 epoch `2024-01-26T11:59:42Z`, ARP-referred, `TRM59900.00 NONE`, `H=0.1710 m`) | Only 3 references (`PHRI` is outside convex hull); `EKAK` (`SEPCHOKE_B3E6 SPKE`) vs. `PHRI` (`TRM59900.00 NONE`) has a `~1.4–1.7 cm` L1/L2 Up PCO difference (identical across all variants). |
| **Dataset A: `2011-03-20` (DOY 079)** | `OSGF` (`OSGF0790.11O` inside immutable `NIGNET2011.zip`, 2,880 ep, 30 s) | 8 refs: `ABUZ, BKFP, CGGT (216.32 km anchor), FUTY, MDGR, RUST, ULAG, UNEC` (**inside convex hull!**) | `brdc0790.11n.Z` (`52cc6c9b…`, validated BKG GPS nav) | **`PROVISIONAL_OSGOF_2011_01_01` (`LIMITED_PROVISIONAL_TRUTH`)** — undocumented frame/ARP/uncertainty; RINEX header differs by `0.77 m`. Zero 2011 SP3/CLK precise products on disk. | No 2011 IGS/WUM precise orbits, clocks, or ERP files exist locally (`find /home/excellence/nlgcp-data` confirmed zero 2011 SP3/CLK files), so independent 2011 PPP cannot be run offline without external product acquisition. |

---

## 4. Recommended Experimental Design

1. **Primary Verified-Truth Positioning Benchmark (`2024-01-26`, `PHRI00NGA`, `VERIFIED_IGS20`):**
   - Compare **Physical Anchor (`EKAK00NGA`, `105.553 km`)** vs. **Geometry-Only VRS (`zero_geom_only`)** vs. **Atmospheric VRS (`tropo_unb3m_only`, `tropo_pride_ztd_only`, `idw2_unb3m`, `idw2_pride_ztd`, `nighttime_idw2_pride_ztd`)** + **SPP** across identical `2,880` 30-second epochs (`00:00:00–23:59:30 GPST`), using identical RTKLIB settings (`pos1-navsys=1` GPS-only, `l1+l2`, `15°` mask, `continuous` AR) in **four processing modes**: `kinematic` (`brdc`/`saas`), `static` (`brdc`/`saas`, reproducing Phase 3 `EKAK-PHRI`), `kinematic_vrs_iono_off` (`iono=off`/`tropo=off` to prevent RTKLIB double-correction on VRS), and `dgps` (`iono=off`/`tropo=off` to isolate pure code-differential positioning).
2. **Secondary Interior-Hull Experimental Benchmark (`2011-03-20`, `OSGF`, `LIMITED_PROVISIONAL_TRUTH`):**
   - Compare **Physical Anchor (`CGGT`, `216.32 km`)** vs. **Geometry-Only VRS (`zero_geom_only`)** vs. **Atmospheric VRS (`tropo_unb3m_only`, `idw2_unb3m`, `ipp_idw2_unb3m`, `nighttime_ipp_idw2_unb3m`)** + **SPP** across the full 24-hour 30-second session (`2,880` epochs) inside the 8-reference convex hull (all 9 stations share identical `TRM59800.00` antennas and `H=0.1710 m`).
   - Report both **ENU residuals vs. provisional OSGoF coordinate** (explicitly labelled `LIMITED_PROVISIONAL_TRUTH`) and **truth-independent repeatability/precision** (ENU std around mean, FIX/FLOAT/SINGLE rates, ambiguity resets, satellite counts).
3. **Strict Non-Leakage & Statistical Discipline:**
   - Verify programmatically that the withheld rover ID and observation dataset never enter Phase 6 atmospheric estimation or Phase 7 VRS synthesis.
   - Compute both full-window availability/accuracy and strictly paired common-epoch differences with moving-block bootstrap 95% confidence intervals (20-minute blocks to respect GNSS temporal autocorrelation).
