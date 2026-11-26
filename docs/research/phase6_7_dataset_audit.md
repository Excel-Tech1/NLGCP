# Phase 6 & 7 Dataset Audit and Experimental Window Selection

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Sprint:** Atmospheric Modelling & VRS Generation Sprint (Phases 6 & 7)
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Validation Status:** `TECHNICALLY_VALIDATED` (content-level audit reproducible; coordinate provenance limitations explicit)

---

## 1. Executive Summary

Before modifying atmospheric or VRS algorithms, a content-level audit was executed across all **3,018** historical RINEX 2.11 observation files inside the immutable 2011 Nigerian GNSS Reference Network (NIGNET) archive (`/home/excellence/nlgcp-data/incoming/southern-nignet/NIGNET2011.zip`, SHA-256 `8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf`), all **35** validated 2011 BKG/IGS navigation-covered dates, and the authoritative **2024 DOY 026** verified-IGS20 benchmark with independent **PRIDE PPP-AR 3.2.8** zenith total delay (ZTD) files on disk.

Three critical discoveries directly shaped the experimental design:

1. **Silent L2/P2 receiver outage hidden by RINEX headers:** Header-only screening declares `C1, C2, L1, L2, P1, P2, S1, S2` for `RUST`, yet body-level parsing revealed **0.0% GPS L2 and 0.0% P2** across December 2011 (`2011-12-05..31`), while `CGGT` also lacked GLONASS L2/P2 on `2011-12-05`. Content-level dual-frequency gating (`audit_rinex2_signal_completeness()` in `research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/dataset_audit.py`) automatically excludes single-frequency sessions.
2. **GPS `P1` is 0% populated across all 2011 stations:** Every 2011 Trimble NetR8/NetR9 observation file records GPS pseudorange on `C1` and `P2` (never `P1`). Dual-frequency GPS code combinations therefore use `C1` + `P2`, explicitly retaining uncalibrated `C1-P1` + `P1-P2` hardware differential code biases (DCBs) because no external IGS/CODE DCB or regional IONEX product is stored locally (`/home/excellence/nlgcp-data/external-products/igs` is empty).
3. **True interior convex-hull network geometry exists in 2011:** Unlike the 4-station 2024 DOY 026 network (where all 4 held-out LOOCV rotations are pure extrapolation), six full-day 2011 windows provide **9 simultaneous full-day dual-frequency stations** spanning `607,707–623,401 km²` with **4 stations strictly inside the 8-reference 2D ENU convex hull** (`ABUZ`, `CGGT`, `OSGF`, `UNEC`) and validated 2011 BKG GPS+GLONASS broadcast navigation on disk.

---

## 2. Archive Inventory and Immutability

| Archive / External Source | Scope | SHA-256 / Provenance | Raw Data Mutated? |
|---|---|---|---|
| `incoming/southern-nignet/NIGNET2011.zip` | 3,018 RINEX 2.11 files, 11 stations (`ABUZ, BKFP, CGGT, CLBR, FUTY, GEMB, MDGR, OSGF, RUST, ULAG, UNEC`), 30.0 s GPS time, `MIXED` GPS+GLONASS | `8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf` | **No** (read-only `zipfile` stream parsing) |
| `validation/southern-nignet/coordinate-navigation-recovery/run-20261030T132927Z/coordinate_provenance.csv` | 11 OSGoF 2011-01-01 station coordinates | `PROVISIONAL_OSGOF_2011_01_01` (frame/ARP/uncertainty undocumented) | **No** |
| `validation/southern-nignet/coordinate-navigation-recovery/run-20261123T163056Z/` | 66/66 validated BKG/IGS 2011 GPS+GLONASS `.Z` nav products across 33 primary dates (+ 2 earlier recovery dates = 35 dates total) | `navigation_product_inventory.csv` (`VALIDATED`) | **No** |
| `processed/single-base/derived-coordinates.json` + 2024 DOY 026 RINEX | 4 verified IGS20 stations (`ABFC00NGA`, `EKAK00NGA`, `MGBO00NGA`, `PHRI00NGA`); `BKFP00NGA` excluded (`scientifically_valid=False`) | `VERIFIED_IGS20_PRIDE_PPP_AR`, BRDC `a6418387…` | **No** |
| `working/pride*/**/ztd_2024026*` | Independent PRIDE PPP-AR 3.2.8 ZTD (`ZDD + ZWDini + ZWDcor`, 2,880 epochs/station) on all 4 verified 2024 stations | PRIDE PPP-AR 3.2.8 (`4907bfe5…`) | **No** |

Derived selection manifest written outside Git:
`/home/excellence/nlgcp-data/processed/atmospheric-model/sprint-phase67/dataset_selection_manifest.json` (generated reproducibly by `scripts/run_phase6_atmospheric_sprint.py`).

---

## 3. Selected Multi-Station Experimental Windows

### 3.1 Primary Experimental Windows (March 2011 Equinox — High Ionosphere, True Interior Hull)

| Date | DOY | Usable Dual-Freq Stations (9) | Excluded Station & Reason | Interior Hull Stations (4) | Perimeter Stations (5) | Hull Area (km²) | Baselines (km) | GPS Nav File |
|---|---|---|---|---|---|---|---|---|
| `2011-03-20` | 079 | `ABUZ, BKFP, CGGT, FUTY, MDGR, OSGF, RUST, ULAG, UNEC` | `CLBR` (`partial session: 1376 < 2400 epochs`) | `ABUZ, CGGT, OSGF, UNEC` | `BKFP, FUTY, MDGR, RUST, ULAG` | `607,707.15` | `188.71–1,218.71` | `brdc0790.11n.Z` (`52cc6c9b…`) |
| `2011-03-21` | 080 | `ABUZ, BKFP, CGGT, FUTY, MDGR, OSGF, RUST, ULAG, UNEC` | `CLBR` (`partial session: 1560 < 2400 epochs`) | `ABUZ, CGGT, OSGF, UNEC` | `BKFP, FUTY, MDGR, RUST, ULAG` | `607,707.15` | `188.71–1,218.71` | `brdc0800.11n.Z` |

### 3.2 Secondary Experimental Windows (December 2011 Solstice — Seasonal Contrast, True Interior Hull)

| Date | DOY | Usable Dual-Freq Stations (9) | Excluded Station & Reason | Interior Hull Stations (4) | Perimeter Stations (5) | Hull Area (km²) | Baselines (km) |
|---|---|---|---|---|---|---|---|
| `2011-12-05` | 339 | `ABUZ, BKFP, CGGT, CLBR, FUTY, MDGR, OSGF, ULAG, UNEC` | `RUST` (`L1=1.00, L2=0.00, P2=0.00`) | `ABUZ, CGGT, OSGF, UNEC` | `BKFP, CLBR, FUTY, MDGR, ULAG` | `623,401.49` | `188.10–1,218.71` |
| `2011-12-06` | 340 | `ABUZ, BKFP, CGGT, CLBR, FUTY, MDGR, OSGF, ULAG, UNEC` | `RUST` (`L1=1.00, L2=0.00, P2=0.00`) | `ABUZ, CGGT, OSGF, UNEC` | `BKFP, CLBR, FUTY, MDGR, ULAG` | `623,401.49` | `188.10–1,218.71` |
| `2011-12-07` | 341 | `ABUZ, BKFP, CGGT, CLBR, FUTY, MDGR, OSGF, ULAG, UNEC` | `RUST` (`L1=1.00, L2=0.00, P2=0.00`) | `ABUZ, CGGT, OSGF, UNEC` | `BKFP, CLBR, FUTY, MDGR, ULAG` | `623,401.49` | `188.10–1,218.71` |
| `2011-12-08` | 342 | `ABUZ, BKFP, CGGT, CLBR, FUTY, MDGR, OSGF, ULAG, UNEC` | `RUST` (`L1=1.00, L2=0.00, P2=0.00`) | `ABUZ, CGGT, OSGF, UNEC` | `BKFP, CLBR, FUTY, MDGR, ULAG` | `623,401.49` | `188.10–1,218.71` |

### 3.3 Verified-Coordinate and Independent PRIDE ZTD Reference Window (2024)

| Date | DOY | Admitted Verified Stations (4) | Excluded Station | Interior Hull Stations (0) | Hull Area (km²) | Baselines (km) | Independent Truth |
|---|---|---|---|---|---|---|---|
| `2024-01-26` | 026 | `ABFC00NGA, EKAK00NGA, MGBO00NGA, PHRI00NGA` | `BKFP00NGA` (`scientifically_valid=False`) | None (all 4 LOOCV folds extrapolate) | `181,177.50` | `105.55–1,029.03` | IGS20 PRIDE PPP-AR coords + 2,880-epoch PRIDE ZTD per station |

---

## 4. Network Geometry and Receiver/Antenna Metadata Findings

- **Receiver/Antenna Consistency (2011):** All 11 NIGNET stations operated Trimble NetR8/NetR9 dual-frequency receivers with `TRM59800.00` choke-ring antennas and consistent `HEN = [0.171, 0.000, 0.000] m` offsets, simplifying inter-station receiver-type consistency while still retaining individual receiver hardware DCBs.
- **Interior vs. Perimeter Stratification:** On `2011-03-20`, `OSGF` (Abuja) lies strictly inside the 8-station convex hull surrounded by `CGGT` (216 km), `ABUZ` (236 km), `UNEC` (288 km), `RUST` (485 km), `ULAG` (528 km), `BKFP` (556 km), `FUTY` (562 km), and `MDGR` (716 km). This resolves the geometric limitation of the 2024 4-station pilot while introducing a **provisional coordinate provenance caveat** (`PROVISIONAL_OSGOF_2011_01_01`).
- **Dual-Track Experimental Strategy:** Running all Phase 6 and Phase 7 experiments across **both** (a) the 9-station 2011 interior-hull networks (March equinox + December solstice) and (b) the 4-station verified-IGS20 2024 DOY 026 + PRIDE ZTD benchmark isolates geometric extrapolation from coordinate provenance effects without fabricating either verified 2011 coordinates or synthetic 2024 interior stations.

---

## 5. Explicit Data Limitations and Unresolved Dependencies

1. **Provisional 2011 coordinates:** All 11 OSGoF 2011-01-01 coordinates lack documented ITRF frame realization, ARP continuity, and formal uncertainties. Results using 2011 coordinates remain strictly `EXPERIMENTAL` and cannot support operational promotion until 2011 PPP-AR re-estimation with verified IGS precise orbits/clocks is performed.
2. **No external DCB or IONEX products:** Local storage contains no CODE/IGS DCB or regional IONEX maps. Uncalibrated STEC/VTEC estimates explicitly set `bias_corrected_stec_tecu = None` and `dcb_status = UNAVAILABLE_EXTERNAL_DCB_NOT_FOUND`.
3. **No local station meteorology:** Surface pressure, temperature, and relative humidity sensors are absent from both archives. Tropospheric priors use UNB3m climatology explicitly labelled `MODELLED CLIMATOLOGY — NOT MEASURED STATION METEOROLOGY`, independently benchmarked against PRIDE PPP-AR ZTD on 2024 DOY 026.
4. **GLONASS FDMA channel numbers:** RINEX 2.11 observation headers omit GLONASS frequency channel numbers (FCNs); dual-frequency geometry-free atmospheric modelling and experimental VRS observation synthesis remain restricted to GPS L1/L2 (`G01–G32`) with explicit non-GPS exclusion accounting.
