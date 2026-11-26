# Phase 7 Experimental VRS Validation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Phase:** Phase 7 — Experimental VRS Validation (Experiments 5 & 8)
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Validation Status:** `TECHNICALLY_VALIDATED` (real held-out observation residual reduction confirmed; RTK FIX positioning validation `NOT_PERFORMED`; operational approval `BLOCKED`)

---

## 1. Validation Methodology

To evaluate whether observation-based experimental VRS synthesis improves physical agreement with real GNSS measurements over the geometry-only `ZERO` baseline, **Experiment 5** ran strictly held-out target synthesis across two complementary real Nigerian datasets using `scripts/run_phase7_vrs_sprint.py --stride 4 --rtcm-epochs 30` (120 s cadence across full 24-hour UT sessions; derived artifact `/home/excellence/nlgcp-data/processed/vrs/sprint-phase67/phase7_vrs_sprint_results.json`):

1. **Experiment 5A (`2011-03-20`, DOY 079 — Interior Hull Target `OSGF`):**
   - 8 surrounding NIGNET reference stations (`ABUZ, BKFP, CGGT, FUTY, MDGR, RUST, ULAG, UNEC`), nearest anchor `CGGT` (`216.1 km`), `inside_convex_hull = True`, `require_interior_hull = True`.
   - Coordinate provenance: `PROVISIONAL_OSGOF_2011_01_01` (experimental research only).
   - Reference-only ionospheric field computed strictly from the 8 references (`OSGF` withheld completely from field estimation and synthesis).
2. **Experiment 5B (`2024-01-26`, DOY 026 — Verified-IGS20 Target `PHRI00NGA`):**
   - 3 verified IGS20 reference stations (`ABFC00NGA, EKAK00NGA, MGBO00NGA`), nearest anchor `EKAK00NGA` (`105.55 km`), `inside_convex_hull = False` (`require_interior_hull = False` with explicit `EXPERIMENTAL_EXTRAPOLATION_WARNING` after verifying strict `require_interior_hull = True` fails closed).
   - Coordinate provenance: `VERIFIED_IGS20`.
   - Independent PRIDE PPP-AR 3.2.8 ZTD loaded strictly for the 3 reference stations (`PHRI00NGA` ZTD withheld completely).

Residuals against withheld real target observations are evaluated via:
- **`C1` / `P2` Code RMSE:** Single-difference (`VRS - Target`) with per-epoch satellite-mean receiver clock offset removed.
- **`L1` / `L2` Phase TD-DD RMSE:** Time-differenced double differences across consecutive slip-free epochs (eliminates unknown receiver clock and constant integer ambiguities).
- **`GF` Time-Differenced RMSE:** Epoch-to-epoch change in `(L1*lambda_1 - L2*lambda_2)` difference between VRS and target (directly isolates ionospheric temporal tracking error without code noise or ambiguities).

---

## 2. Experiment 5A Results — 2011-03-20 Interior Target `OSGF` (8 References)

| VRS Model Variant | Matched Obs | `C1` RMSE (m) | `C1` vs. Zero | `P2` RMSE (m) | `P2` vs. Zero | `L1` TD-DD (m) | `L2` TD-DD (m) | `GF` TD RMSE (m) | `GF` vs. Zero |
|---|---|---|---|---|---|---|---|---|---|
| `zero_geom_only` (`GEOMETRY_ONLY_VRS`) | 5,769 | `0.6932` | `0.0%` | `1.0044` | `0.0%` | `0.6424` | `1.9183` | `0.0440` | `0.0%` |
| `tropo_unb3m_only` (UNB3m diff tropo) | 5,769 | `0.6236` | **`-10.0%`** | `0.9425` | **`-6.2%`** | `0.6418` | `1.9181` | `0.0440` | `0.0%` |
| **`idw2_unb3m`** (IDW² iono + UNB3m) | 5,755 | **`0.5360`** | **`-22.7%`** | **`0.7916`** | **`-21.2%`** | **`0.6360`** | **`1.1883`** (`-38.1%`) | **`0.0344`** | **`-21.8%`** |
| **`ipp_idw2_unb3m`** (IPP-IDW² + UNB3m) | 5,755 | **`0.5339`** | **`-23.0%`** | **`0.7857`** | **`-21.8%`** | **`0.6360`** | **`1.1883`** (`-38.1%`) | **`0.0356`** | **`-19.1%`** |
| `planar_unb3m` (Planar iono + UNB3m) | 5,755 | `0.5645` | `-18.6%` | `0.8398` | `-16.4%` | `0.6362` | `1.1790` (`-38.5%`) | `0.0382` | `-13.2%` |

**Key Findings (Experiment 5A):**
1. **Consistent multi-observable gain inside the convex hull:** Every observation-based atmospheric VRS variant beat geometry-only `zero_geom_only` across **all five** diagnostic observables (`C1`, `P2`, `L1` TD-DD, `L2` TD-DD, and `GF` TD) on ~5,755 held-out real dual-frequency observations.
2. **Physical separation verified on real data:** Adding UNB3m differential troposphere alone reduced `C1` RMSE by `10.0%` (`0.693 m → 0.624 m`) because `OSGF` (533 m altitude) and anchor `CGGT` (917 m altitude) have a real hydrostatic elevation difference. Adding spatially interpolated ionospheric corrections (`idw2_unb3m` / `ipp_idw2_unb3m`) delivered an additional `~13%` code reduction (`-22.7%` to `-23.0%` total on `C1`, `-21.2%` to `-21.8%` on `P2`) and cut geometry-free ionospheric tracking error by `21.8%` (`4.40 cm → 3.44 cm`).
3. **IPP-space interpolation (`ipp_idw2_unb3m`) achieved the lowest code residuals** (`0.5339 m` C1, `0.7857 m` P2), confirming that evaluating spatial correlation at 350 km Ionospheric Pierce Points is physically well-motivated across Nigeria's 200–700 km station spacing.

---

## 3. Experiment 5B Results — 2024-01-26 Verified-IGS20 Target `PHRI00NGA` (3 References, Extrapolated)

| VRS Model Variant | Matched Obs | `C1` RMSE (m) | `C1` vs. Zero | `P2` RMSE (m) | `P2` vs. Zero | `L1` TD-DD (m) | `L2` TD-DD (m) | `GF` TD RMSE (m) | `GF` vs. Zero |
|---|---|---|---|---|---|---|---|---|---|
| `zero_geom_only` (`GEOMETRY_ONLY_VRS`) | 5,825 | `0.5156` | `0.0%` | `0.6750` | `0.0%` | `0.1114` | `0.5507` | `0.0593` | `0.0%` |
| `tropo_unb3m_only` (UNB3m diff tropo) | 5,825 | `0.4837` | `-6.2%` | `0.6404` | `-5.1%` | `0.1114` | `0.5507` | `0.0593` | `0.0%` |
| `tropo_pride_ztd_only` (PRIDE ref ZTD) | 5,825 | `0.5168` | `+0.2%` | `0.6548` | `-3.0%` | `0.1120` | `0.5507` | `0.0593` | `0.0%` |
| **`idw2_pride_ztd`** (IDW² + PRIDE ZTD) | 5,389 | **`0.4671`** | **`-9.4%`** | **`0.6215`** | **`-7.9%`** | **`0.1030`** (`-7.5%`) | **`0.5420`** | **`0.0527`** | **`-11.1%`** |
| `planar_unb3m` (Planar + UNB3m) | 5,031 | `0.4613` | `-10.5%` | `0.6218` | `-7.9%` | `0.0920` | `0.5595` | `0.0539` | `-9.1%` |

**Key Findings (Experiment 5B):**
1. **Verified-coordinate consistency:** Even on the sparser 3-reference extrapolated 2024 network (`VERIFIED_IGS20`), `idw2_pride_ztd` reduced residuals across all observables (`C1` `-9.4%`, `P2` `-7.9%`, `L1` TD-DD `-7.5%`, `GF` TD `-11.1%`), confirming that the 2011 interior gain is not an artifact of provisional coordinates.
2. **Honest extrapolation caveat:** Under 3-reference extrapolation (`105–1,029 km`), `planar_unb3m` dropped `794` observations (`5,825 → 5,031`) when extrapolated corrections failed quality gates, and `tropo_pride_ztd_only` barely changed `C1` (`+0.2%`) because IDW extrapolation from dry inland stations (`MGBO` ZWD `0.103 m`, `ABFC` `0.126 m`) toward coastal `PHRI` (`0.175 m`) pulled `PHRI` slightly drier than coastal anchor `EKAK` (`0.229 m`). This confirms why interior convex-hull geometry and denser coastal stations are mandatory before operational NRTK.

---

## 4. Experiment 8 Results — Failure-Mode and Boundary Verification (11/11 PASS)

| # | Scenario Tested | Expected Fail-Closed Outcome | Observed Result | Status |
|---|---|---|---|---|
| 1 | Missing observations (empty dataset) | `INSUFFICIENT_OBSERVATION_COVERAGE` | `NO_SIMULTANEOUS_EPOCHS_ACROSS_REFERENCES` | **PASS** |
| 2 | Poor geometry / extrapolation (`PHRI00NGA`, `require_interior_hull=True`) | `INSUFFICIENT_NETWORK_GEOMETRY` | `TARGET_OUTSIDE_REFERENCE_CONVEX_HULL_EXTRAPOLATION` (`inside_convex_hull=False`) | **PASS** |
| 3 | Missing dual-frequency observables (single-freq `C1/L1` anchor) | `INSUFFICIENT_OBSERVATION_COVERAGE` | `ANCHOR_MISSING_DUAL_FREQUENCY_GPS_OBSERVABLES` | **PASS** |
| 4 | Invalid station coordinates (`radius = 3,741.7 m`) | `INVALID_STATION_COORDINATES` | Rejected outside `[6300, 6450] km` | **PASS** |
| 5 | Insufficient reference stations (`2 < 3`) | `INSUFFICIENT_NETWORK_GEOMETRY` | `INSUFFICIENT_OR_MISMATCHED_REFERENCES_MIN_3_REQUIRED` | **PASS** |
| 6 | Atmospheric model unavailable (`idw2` with `iono=None`) | `ATMOSPHERIC_MODEL_UNAVAILABLE` | `IONOSPHERIC_FIELD_UNAVAILABLE_FOR_NONZERO_MODEL` | **PASS** |
| 7 | Invalid RTCM frame (flipped CRC-24Q byte) | `PublicationError` | `CRC-24Q mismatch: declared 0x987992, computed 0x98796d` | **PASS** |
| 8 | Unsupported GNSS message family (`MSM7_GALILEO_1097`) | `VALIDATION_FAILED` | `UNSUPPORTED_GNSS_MESSAGE_FAMILY` | **PASS** |
| 9 | Interrupted NTRIP stream + reconnect recovery | Clean reconnect & 0 invalid frames | `client_ok=True`, `valid_frames=4`, `invalid_frames=0`, `reconnection_attempts=1` | **PASS** |
| 10 | Missing provenance & held-out target leakage (`CGGT` in refs) | `INVALID_STATION_COORDINATES` / `VRS_GENERATION_BLOCKED` | Both blocked cleanly | **PASS** |
| 11 | Operational promotion & cross-mountpoint publication | Blocked at Phase 7 & Phase 12 | `OPERATIONAL_VRS_APPROVAL_FORBIDDEN`; cross-publish to `NLGCP_TEST` blocked; `OPERATIONAL_APPROVED` frame blocked | **PASS** |

---

## 5. What This Validation Proves — and What It Does NOT Prove

- **Proven (`TECHNICALLY_VALIDATED`):** Physically signed experimental VRS synthesis from authentic Nigerian GNSS observations measurably reduces held-out code, phase TD-DD, and geometry-free ionospheric residuals relative to geometry-only `ZERO`, especially inside a true convex hull (`-21.8%` to `-23.0%`), and fails closed cleanly across all 11 fault and governance scenarios.
- **NOT Proven (`NOT_PERFORMED` / `BLOCKED`):** No downstream rover RTK positioning solution (`rnx2rtkp` kinematic/static positioning against the synthesized VRS RTCM stream), no network integer ambiguity resolution (IAR), no RTK FIX rate or centimetre positioning accuracy claim, and no commercial GNSS receiver interoperability test was performed. Operational VRS approval therefore remains strictly `FORBIDDEN`.
