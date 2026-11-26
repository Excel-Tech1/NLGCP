# B-04 Coordinate Verification & B-02 v2 Re-Evaluation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-04 — Coordinate Verification (Absorbs B-01)  
**Date:** 2026-11-26  
**Classification:** `IMPLEMENTED` | `INDEPENDENTLY_VALIDATED` (`PRIDE PPP-AR 3.2.8` + `RTKLIB v2.4.2-p13`) | Operational Status: `NOT_APPROVED`  
**Analysis Runner:** [scripts/run_b04_analyze_and_b02_v2.py](file:///home/excellence/NLGCP/scripts/run_b04_analyze_and_b02_v2.py)  
**Deliverables:**
- Coordinate Catalogue: [docs/research/b04_station_coordinate_catalogue.csv](file:///home/excellence/NLGCP/docs/research/b04_station_coordinate_catalogue.csv)
- Uncertainty & Repeatability Table: [docs/research/b04_coordinate_uncertainty.csv](file:///home/excellence/NLGCP/docs/research/b04_coordinate_uncertainty.csv)
- Analysis JSON: `/home/excellence/nlgcp-data/processed/b04-coordinate-verification/b04_analysis_summary.json`
- Versioned B-02 v2 Re-Evaluation: `/home/excellence/nlgcp-data/processed/rover-benchmark/b02-v2-b04-verified-truth/b02_v2_b04_summary.json`

---

## 1. Executive Summary & Verdict

Milestone **B-04** resolves the historical coordinate-provenance blocker for the 2011 NIGNET southern/national network:

1. **March 2011 (`IGS05`, epoch `2011.21642`, DOY `079–080`):** **`9 / 9` stations** (`ABUZ, BKFP, CGGT, FUTY, MDGR, OSGF, RUST, ULAG, UNEC`) passed all 8 Section 5.6 acceptance criteria and are classified **`VERIFIED_IGS05_PPP_FLOAT`** (`truth_ready = True`, multi-day 3D repeatability `2.64 – 13.08 mm`, IGS–CODE 3D agreement `6.72 – 9.51 mm`).
2. **December 2011 (`IGS08`, epoch `2011.93149`, DOY `339–342`):** **`8 / 9` stations** passed all 8 criteria and are classified **`VERIFIED_IGS08_PPP_FLOAT`** (`truth_ready = True`, 4-day 3D repeatability `1.35 – 2.98 mm`, IGS–CODE 3D agreement `4.04 – 4.51 mm`). **`RUST`** failed fail-closed (`UNVERIFIED`) due to its December L2/P2 receiver outage.
3. **12-Year Monument Continuity (`OSGF` 2011 → `ABFC00NGA` 2024):** Transforming B-04 `OSGF` (`IGS08`, `2011.93149`) to `ITRF2020` via official Altamimi et al. (2023) 14-parameter Helmert parameters and propagating `12.1382 yr` with the `ITRF2020-PMM` Nubian plate vector matches 2024 verified `ABFC00NGA` (`IGS20`) to **`6.44 mm` horizontal (`+6.28 mm` E, `+1.43 mm` N, `-7.44 mm` Up)** — proving `OSGF` and `ABFC00NGA` occupy the same stable Abuja monument.
4. **Provisional OSGoF 2011-01-01 Discrepancy:** The historical OSGoF table (`2011-01-01`) agrees with B-04 March `IGS05` within `1.13 – 7.64 cm` 3D (`OSGF` `7.64 cm`, mostly `+7.43 cm` Up; `CGGT` `2.21 cm`; `ULAG` `1.13 cm`). By contrast, raw RINEX header `APPROX POSITION XYZ` coordinates deviate by `0.77 – 3.5+ m` and remain strictly rejected.
5. **Versioned B-02 v2 Re-Evaluation (`2011-03-20 OSGF`):** Preserving the original B-02 outputs untouched under `processed/rover-benchmark/b02/`, re-running the full 2011 benchmark with **all 9 stations updated to B-04 verified `IGS05` coordinates** confirms that the ~52–58% horizontal FLOAT improvement of interior-hull atmospheric VRS is **physically genuine, not a coordinate artifact**:
   - Kinematic FLOAT `vrs_ipp_idw2_unb3m` vs anchor `CGGT`: `1.4591 → 0.6397 m` (**`+56.16%`**, 95% block-bootstrap CI `[+0.5940, +1.0041] m`; vs original provisional `1.4562 → 0.6313 m`, `+56.65%`).
   - Static FLOAT `vrs_ipp_idw2_unb3m` vs anchor `CGGT`: `0.9049 → 0.3822 m` (**`+57.76%`**, 95% CI `[+0.3838, +0.6606] m`; static vertical RMSE improved `~6–7 cm` purely from fixing OSGoF's `+7.43 cm` Up offset).
   - Genuine RTK FIX remains **`0.0%`** (`2` false `Q=1` on `vrs_zero_geom_only`, `5` false `Q=1` on `vrs_tropo_unb3m_only`, `0` on atmospheric VRS).

---

## 2. Station-by-Station Coordinate Verification Status

### 2.1 March 2011 (`IGS05`, Epoch `2011.21642`, `igs05_1617.atx`, 2 Days)

| Station | ECEF X (m) | ECEF Y (m) | ECEF Z (m) | Rep 3D (mm) | IGS–CODE 3D (mm) | Phase RMS Max (mm) | OSGoF Diff 3D (cm) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `ABUZ` | 6203493.83099 | 833088.70249 | 1225614.63209 | 4.79 | 7.77 | 16.0 | 4.47 | `VERIFIED_IGS05_PPP_FLOAT` |
| `BKFP` | 6211960.35786 | 459365.48364 | 1368115.04440 | 7.05 | 6.96 | 13.0 | 7.30 | `VERIFIED_IGS05_PPP_FLOAT` |
| `CGGT` | 6201032.29140 | 995277.25061 | 1113815.52037 | 2.95 | 8.82 | 15.0 | 2.21 | `VERIFIED_IGS05_PPP_FLOAT` |
| `FUTY` | 6145058.51384 | 1362078.87712 | 1029389.91385 | 7.61 | 7.60 | 19.0 | 3.01 | `VERIFIED_IGS05_PPP_FLOAT` |
| `MDGR` | 6080449.31169 | 1418433.49691 | 1299949.41672 | 2.64 | 9.28 | 12.0 | 2.06 | `VERIFIED_IGS05_PPP_FLOAT` |
| `OSGF` | 6246471.27631 | 820848.73629 | 994267.93005 | 2.85 | 8.00 | 21.0 | 7.64 | `VERIFIED_IGS05_PPP_FLOAT` |
| `RUST` | 6308859.06364 | 772229.93020 | 530354.45979 | 13.08 | 8.53 | 21.0 | 6.36 | `VERIFIED_IGS05_PPP_FLOAT` |
| `ULAG` | 6326097.31123 | 375576.10894 | 719131.69101 | 4.36 | 6.72 | 15.0 | 1.13 | `VERIFIED_IGS05_PPP_FLOAT` |
| `UNEC` | 6284298.32428 | 827900.52753 | 708988.58763 | 12.14 | 9.51 | 21.0 | 2.55 | `VERIFIED_IGS05_PPP_FLOAT` |

### 2.2 December 2011 (`IGS08`, Epoch `2011.93149`, `igs08_1648.atx`, 4 Days)

| Station | ECEF X (m) | ECEF Y (m) | ECEF Z (m) | Rep 3D (mm) | IGS–CODE 3D (mm) | Phase RMS Max (mm) | Mar→Dec PMM Res (H / U mm) | Status |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `ABUZ` | 6203493.81097 | 833088.72082 | 1225614.64397 | 1.35 | 4.34 | 8.0 | 5.37 / -8.64 | `VERIFIED_IGS08_PPP_FLOAT` |
| `BKFP` | 6211960.33686 | 459365.49965 | 1368115.05586 | 2.02 | 4.04 | 10.0 | 3.19 / -10.74 | `VERIFIED_IGS08_PPP_FLOAT` |
| `CGGT` | 6201032.26787 | 995277.26572 | 1113815.53117 | 2.44 | 4.37 | 9.0 | 4.54 / -12.41 | `VERIFIED_IGS08_PPP_FLOAT` |
| `FUTY` | 6145058.48776 | 1362078.89631 | 1029389.92476 | 1.38 | 4.39 | 10.0 | 8.43 / -13.05 | `VERIFIED_IGS08_PPP_FLOAT` |
| `MDGR` | 6080449.28970 | 1418433.51547 | 1299949.42667 | 2.09 | 4.51 | 11.0 | 7.94 / -8.81 | `VERIFIED_IGS08_PPP_FLOAT` |
| `OSGF` | 6246471.24804 | 820848.75467 | 994267.94146 | 2.98 | 4.48 | 8.0 | 5.99 / -17.20 | `VERIFIED_IGS08_PPP_FLOAT` |
| `RUST` | — | — | — | — | — | — | — | `UNVERIFIED` (L2/P2=0%) |
| `ULAG` | 6326097.28613 | 375576.12977 | 719131.70182 | 2.61 | 4.16 | 13.0 | 7.43 / -15.83 | `VERIFIED_IGS08_PPP_FLOAT` |
| `UNEC` | 6284298.29773 | 827900.53385 | 708988.59782 | 1.98 | 4.19 | 12.0 | 9.05 / -17.64 | `VERIFIED_IGS08_PPP_FLOAT` |

*(Note: The `-8.6` to `-17.6 mm` Up residual between March `IGS05` and December `IGS08` after pure ITRF Helmert transformation reflects the documented `igs05_1617.atx` → `igs08_1648.atx` TRM59800.00 and satellite PCO update.)*

---

## 3. Versioned B-02 v2 Re-Evaluation (`2011-03-20 OSGF`)

- **Truth Datum Shift (`B-04 IGS05 - OSGoF 2011-01-01`):** `ENU = [-0.01362, -0.01175, +0.07425] m` (`3D = 0.07640 m`); `CGGT` anchor shift `3D = 0.02212 m`.
- **Autonomous Epoch-0 SPP GGA Virtual ARP Offset:** `0.7829 m` from B-04 verified `OSGF` (`assert_no_rover_leakage()` `passed = True`).
- **Original B-02 Summary SHA-256 Preserved Untouched:** `47dc7457…` (`processed/rover-benchmark/b02/`).

| Profile | Variant | B-02 Old H (m) | B-02 v2 B-04 H (m) | B-02 Old V (m) | B-02 v2 B-04 V (m) | B-02 v2 3D (m) | Gain vs Anchor (95% CI) | FIX / Valid |
|---|---|---:|---:|---:|---:|---:|---|---|
| `spp_single` | `spp_standalone` | 1.2699 | **1.2678** | 3.3769 | **3.3602** | 3.5914 | — | 0 / 2,880 |
| `kinematic` | `physical_anchor_cggt` | 1.4562 | **1.4591** | 1.4676 | **1.4500** | 2.0570 | — | 0 / 2,880 |
| `kinematic` | `vrs_zero_geom_only` | 1.4854 | **1.4290** | 1.6180 | **1.6392** | 2.1747 | `+2.06%` `[-0.077, +0.140]` | 2* / 2,880 |
| `kinematic` | `vrs_tropo_unb3m_only` | 1.4531 | **1.4578** | 1.4560 | **1.4487** | 2.0552 | `+0.09%` `[-0.008, +0.009]` | 5* / 2,880 |
| `kinematic` | `vrs_idw2_unb3m` | 0.7018 | **0.6985** | 0.9539 | **0.9359** | 1.1678 | **`+52.12%`** `[+0.539, +0.947]` | 0 / 2,880 |
| `kinematic` | `vrs_ipp_idw2_unb3m` | 0.6313 | **0.6397** | 0.9333 | **0.9620** | 1.1552 | **`+56.16%`** `[+0.594, +1.004]` | 0 / 2,880 |
| `kinematic` | `vrs_nighttime_ipp_idw2_unb3m` | 0.7509 | **0.7402** | 1.0240 | **1.0289** | 1.2675 | **`+49.27%`** `[+0.486, +0.910]` | 0 / 2,880 |
| `static` | `physical_anchor_cggt` | 0.9166 | **0.9049** | 0.6088 | **0.5340** | 1.0507 | — | 0 / 2,880 |
| `static` | `vrs_zero_geom_only` | 1.1483 | **1.1316** | 0.8875 | **0.8110** | 1.3923 | `-25.06%` `[-0.284, -0.166]` | 0 / 2,880 |
| `static` | `vrs_tropo_unb3m_only` | 0.9049 | **0.8938** | 0.5284 | **0.4554** | 1.0031 | `+1.23%` `[+0.006, +0.016]` | 0 / 2,880 |
| `static` | `vrs_ipp_idw2_unb3m` | 0.3935 | **0.3822** | 0.4137 | **0.3406** | 0.5120 | **`+57.76%`** `[+0.384, +0.661]` | 0 / 2,880 |
| `dgps` | `physical_anchor_cggt` | 0.7891 | **0.7899** | 1.4149 | **1.3799** | 1.5900 | — | 0 / 2,880 |
| `dgps` | `vrs_nighttime_ipp_idw2_unb3m` | 0.4310 | **0.4402** | 1.0119 | **0.9783** | 1.0728 | **`+44.28%`** `[+0.240, +0.465]` | 0 / 2,880 |

*\*Confirmed wrong-integer false fixes (same 7 epochs as B-02; genuine RTK FIX = `0.0%`).*

---

## 4. Limitations, Unresolved Issues & Next Steps

- Coordinates in `2011` remain **PPP-float** (`VERIFIED_IGS05_PPP_FLOAT` / `VERIFIED_IGS08_PPP_FLOAT`) without 2011 OSB phase biases; genuine RTK FIX remains `0.0%` pending **B-03**.
- Next milestone: **B-05 — Atmospheric Model Enhancement** using these verified B-04 coordinates and the acquired 2011/2024 CODE/CAS DCB/OSB and IONEX products.
