# B-03 Network Integer Ambiguity Resolution & Controlled Rover Validation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-03 — Network Integer Ambiguity Resolution & False-Fix Prevention  
**Date:** 2026-11-27  
**Status Classification:**  
- **Implementation:** `IMPLEMENTED` ([network_iar.py](file:///home/excellence/NLGCP/research/vrs_generator/src/nlgcp_vrs/network_iar.py), [run_b03_network_iar_sprint.py](file:///home/excellence/NLGCP/scripts/run_b03_network_iar_sprint.py))  
- **Testing:** `UNIT_TESTED` (`7/7` LAMBDA/PAR, WL, triangle closure, and `FalseFixGuard` unit tests passing in [test_network_iar.py](file:///home/excellence/NLGCP/research/vrs_generator/tests/test_network_iar.py))  
- **Validation:** `INDEPENDENTLY_VALIDATED` (`RTKLIB v2.4.2-p13` pinned `rnx2rtkp` `b4a96cd0…` / `convbin` `b575f81e…`; B-04 verified `IGS05`/`IGS08` + verified `IGS20` truth)  
- **Operational Approval:** `NOT_APPROVED` (`OPERATIONAL_APPROVED = FORBIDDEN`; current `ANCHOR_RELATIVE_FLOAT` VRS remains `FLOAT_ONLY`)  
- **Archive Output:** `/home/excellence/nlgcp-data/processed/rover-benchmark/b03-iar-validation/b03_iar_validation_summary.json`

---

## 1. Executive Summary & Scientific Breakthroughs

Milestone **B-03** investigated why B-02 and B-02 v2 achieved `0.0%` genuine RTK FIX (with `7` confirmed wrong-integer false `Q=1` epochs), implemented a conservative network-level double-difference IAR + LAMBDA/PAR + `FalseFixGuard` engine, and executed three authentic full-day experiments:

1. **First Validated Network-Level Integer Narrow-Lane Ambiguity Resolution with Exact Triangle Loop Closure (Part 1):**
   - On Harmattan `2011-12-05` (B-04 verified `IGS08`, 4-day repeatability `1.35–2.98 mm`), the 197–236 km Nigerian triangle **`OSGF–CGGT–ABUZ`** achieved **`91.95%–100.0%`** Melbourne-Wübbena wide-lane fixing (`79/79` satellites = **`100.0%`** exact integer WL loop closures across `12/12` windows) and **`58.3%–100.0%`** ionosphere-free narrow-lane LAMBDA/PAR fixing (`10/12`, `12/12`, `7/12` windows) with **`6/6` (`100.0%`) exact zero integer N1 triangle closures (`N_AB + N_BC - N_AC == 0`)**.
   - On equinox `2011-03-20` (`IGS05`), WL closure was `204/204` (`100.0%`) across both triangles, with `10/12` (`83.3%`) NL LAMBDA fixes on `CGGT→ABUZ` (`197.003 km`), while solar-maximum `2024-01-26` (`IGS20`) achieved `19/19` WL closures and stayed fail-closed **`FLOAT_ONLY`** (`0/13` NL windows) under broadcast orbits.
2. **100% Blind Catch Rate on B-02 v2 False Fixes (Part 2):**
   - Running the conservative `FalseFixGuard` (`min_ratio=5.0`, `min_persistence=3`, float-to-fix jump check) blindly on B-02 v2's preserved `.pos` files rejected **`7/7` (`100.0%`)** of the wrong-integer `Q=1` epochs (`2/2` on `vrs_zero_geom_only` via `low_ratio`; `5/5` on `vrs_tropo_unb3m_only` via `low_ratio` + `pos_jump_from_float`) with **`0` false-fix escapes**.
3. **First Genuine Centimetre RTK FIX on Authentic Long-Baseline Nigerian NIGNET Data (Part 3 — Physical Anchor + `est-stec` + `est-ztd`):**
   - Enabling RTKLIB `v2.4.2-p13` long-baseline ionosphere + ZTD estimation (`est-stec` + `est-ztd`, `arthres=5.0`) on verified physical-anchor baselines transformed positioning accuracy with **zero false-fix escapes across all 20 full-day runs**:
     - **`2024-01-26` `PHRI00NGA` (`105.553 km` `EKAK→PHRI`, `IGS20`):** Kinematic H RMSE dropped **`-93.63%`** (`1.3075 → 0.0833 m`, 95% block-bootstrap CI `[+0.9584, +1.4578] m`, `891` guard-validated FIX epochs, `0` escapes); **Static H RMSE reached `0.0259 m` (`2.59 cm`), V `0.0307 m` (`3.07 cm`), 3D `0.0401 m` (`1,062` guard-validated FIX epochs, `0` escapes)**.
     - **`2011-03-20` `OSGF` (`216.320 km` `CGGT→OSGF`, B-04 `IGS05`):** Kinematic H RMSE dropped **`-94.74%`** (`1.4591 → 0.0767 m`, 95% CI `[+1.0583, +1.6663] m`, `1,041` guard-validated FIX epochs, `0` escapes).
4. **Critical Honest Negative Finding — Why Current `ANCHOR_RELATIVE_FLOAT` VRS Stays `FLOAT_ONLY` Even Under `est-stec`:**
   - Under `brdc+saas` (FLOAT), strictly causal B-05 VRS improves over physical anchor (`2011 OSGF` kinematic `+13.19%`, 95% CI `[+0.0269, +0.3276] m`; `2024 PHRI` static `0.8859 m`, matching offline `0.8881 m`), and survives a 5-minute outage (`12:00–12:05 UTC`) with only `+2.0 mm` full-day impact (`1.2667 → 1.2687 m`).
   - However, under `est-stec + est-ztd`, **both offline and causal `ANCHOR_RELATIVE_FLOAT` VRS yielded `0` FIX epochs** (`2011` offline `0.6484 m` vs physical anchor `0.0767 m`, `-745.09%`; `2024` offline `1.2629 m` vs physical anchor `0.0833 m`).
   - **Root Cause:** Phase 7's experimental VRS injects real-valued, float-leveled ionospheric corrections into `L1`/`L2` carrier phases without resolving network double-difference integer ambiguities first, destroying exact double-difference integer wavelength preservation required by rover LAMBDA AR. Achieving fixed-ambiguity VRS requires reconstructing atmospheric corrections directly from Part 1's **network-IAR-fixed** double-difference observables.

---

## 2. Part 1 — Network-Level Double-Difference IAR & Loop-Closure Results

| Date / Frame | Baseline (km) | WL Fixed / Tested (%) | NL Full Fixed | NL PAR Fixed | NL Rejected False | Triangle Exact Zero Closures |
|---|---:|---:|---:|---:|---:|---|
| `2011-03-20` (`IGS05`) | `OSGF→CGGT` (216.291) | 106 / 110 (`96.36%`) | 0 | 0 / 12 | 2 | `OSGF-CGGT-ABUZ`: WL **`103/103`** (`12/12` wins), NL `0/0` |
| `2011-03-20` (`IGS05`) | `CGGT→ABUZ` (197.003) | 108 / 111 (`97.30%`) | **2** | **8** / 12 | 0 | (part of above) |
| `2011-03-20` (`IGS05`) | `OSGF→ABUZ` (235.623) | 108 / 112 (`96.43%`) | 0 | 0 / 12 | 1 | `OSGF-ABUZ-UNEC`: WL **`101/101`** (`12/12` wins), NL `0/0` |
| `2011-03-20` (`IGS05`) | `ABUZ→UNEC` (522.933) | 105 / 110 (`95.45%`) | 0 | 0 / 12 | 6 | (part of above) |
| `2011-03-20` (`IGS05`) | `OSGF→UNEC` (287.863) | 107 / 111 (`96.40%`) | 0 | 1 / 12 | 2 | (part of above) |
| `2011-12-05` (`IGS08`) | `OSGF→CGGT` (216.291) | 80 / 87 (`91.95%`) | **1** | **9** / 12 | 0 | **`OSGF-CGGT-ABUZ`: WL `79/79` (`12/12`), NL `6/6` (`100.0%`)** |
| `2011-12-05` (`IGS08`) | `CGGT→ABUZ` (197.003) | 97 / 97 (`100.0%`) | **3** | **9** / 12 | 0 | (part of above) |
| `2011-12-05` (`IGS08`) | `OSGF→ABUZ` (235.623) | 93 / 97 (`95.88%`) | **1** | **6** / 12 | 1 | (part of above) |
| `2024-01-26` (`IGS20`) | `EKAK→PHRI` (105.553) | 47 / 96 (`48.96%`) | 0 | 0 / 6 | 3 | `ABFC-EKAK-PHRI`: WL **`19/19`** (`9/9` wins), NL `0/0` |
| `2024-01-26` (`IGS20`) | `ABFC→EKAK` (487.636) | 48 / 52 (`92.31%`) | 0 | 0 / 6 | 1 | (part of above) |
| `2024-01-26` (`IGS20`) | `ABFC→PHRI` (470.870) | 24 / 45 (`53.33%`) | 0 | 0 / 1 | 0 | (part of above) |

---

## 3. Part 3 — Controlled 24-Hour Rover Positioning Validation (`20/20` Runs, `2,880` Epochs)

### 3.1 Verified `IGS20` `2024-01-26` `PHRI00NGA` (`105.553 km` Anchor `EKAK00NGA`)

| Run ID | Mode / Iono / Tropo / `arthres` | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Raw `Q=1` | Guard Validated FIX | False-Fix Escapes |
|---|---|---:|---:|---:|---:|---:|---:|
| `anchor_kin_brdc_t3` | kin / `brdc` / `saas` / 3.0 | 1.3075 | 2.1834 | 2.5449 | 20 | 0 | 0 |
| **`anchor_kin_est_stec_t3`** | kin / `est-stec` / `est-ztd` / 3.0 | **0.0832** | **0.2609** | **0.2739** | 1,413 | **905** | **0** |
| **`anchor_kin_est_stec_t5`** | kin / `est-stec` / `est-ztd` / 5.0 | **0.0833** | **0.2613** | **0.2743** | 899 | **891** | **0** |
| **`anchor_sta_est_stec_t5`** | sta / `est-stec` / `est-ztd` / 5.0 | **0.0259** | **0.0307** | **0.0401** | 1,076 | **1,062** | **0** |
| `vrs_off_idw2_kin_brdc_t3` | kin / `brdc` / `saas` / 3.0 | 1.2329 | 1.8041 | 2.1851 | 0 | 0 | 0 |
| `vrs_off_idw2_kin_est_stec_t5` | kin / `est-stec` / `est-ztd` / 5.0 | 1.2629 | 2.5982 | 2.8889 | 0 | 0 | 0 |
| `vrs_causal_idw2_kin_brdc_t3` | kin / `brdc` / `saas` / 3.0 | 1.2457 | 2.1845 | 2.5147 | 0 | 0 | 0 |
| `vrs_causal_idw2_kin_est_stec_t5` | kin / `est-stec` / `est-ztd` / 5.0 | 1.2605 | 2.4627 | 2.7666 | 0 | 0 | 0 |
| `vrs_causal_idw2_sta_brdc_t3` | sta / `brdc` / `saas` / 3.0 | 0.8859 | 0.5834 | 1.0607 | 0 | 0 | 0 |

### 3.2 B-04 Verified `IGS05` `2011-03-20` `OSGF` (`216.320 km` Anchor `CGGT`, Interior 8-Ref Hull)

| Run ID | Mode / Iono / Tropo / `arthres` | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Raw `Q=1` | Guard Validated FIX | False-Fix Escapes |
|---|---|---:|---:|---:|---:|---:|---:|
| `anchor_kin_brdc_t3` | kin / `brdc` / `saas` / 3.0 | 1.4591 | 1.4500 | 2.0570 | 0 | 0 | 0 |
| **`anchor_kin_est_stec_t3`** | kin / `est-stec` / `est-ztd` / 3.0 | **0.0757** | **0.2293** | **0.2414** | 1,594 | **1,047** | **0** |
| **`anchor_kin_est_stec_t5`** | kin / `est-stec` / `est-ztd` / 5.0 | **0.0767** | **0.2295** | **0.2420** | 1,048 | **1,041** | **0** |
| `vrs_off_ipp_kin_brdc_t3` | kin / `brdc` / `saas` / 3.0 | 0.6397 | 0.9619 | 1.1552 | 1 | 0 | 0 |
| `vrs_off_ipp_kin_est_stec_t3` | kin / `est-stec` / `est-ztd` / 3.0 | 0.6484 | 1.3910 | 1.5347 | 0 | 0 | 0 |
| `vrs_off_ipp_kin_est_stec_t5` | kin / `est-stec` / `est-ztd` / 5.0 | 0.6484 | 1.3910 | 1.5347 | 0 | 0 | 0 |
| `vrs_off_ipp_sta_est_stec_t5` | sta / `est-stec` / `est-ztd` / 5.0 | 0.5262 | 0.5543 | 0.7643 | 0 | 0 | 0 |
| `vrs_causal_ipp_kin_brdc_t3` | kin / `brdc` / `saas` / 3.0 | 1.2667 | 1.2955 | 1.8118 | 0 | 0 | 0 |
| `vrs_causal_ipp_kin_est_stec_t5` | kin / `est-stec` / `est-ztd` / 5.0 | 1.2111 | 1.9206 | 2.2705 | 0 | 0 | 0 |
| `vrs_causal_ipp_sta_brdc_t3` | sta / `brdc` / `saas` / 3.0 | 0.7506 | 0.3359 | 0.8223 | 0 | 0 | 0 |
| `vrs_causal_ipp_outage_5min` | kin / `brdc` / `saas` / 3.0 (5m gap) | 1.2687 | 1.2977 | 1.8149 | 0 | 0 | 0 |

### 3.3 Paired Moving-Block Bootstrap 95% Confidence Intervals (`40`-Epoch Blocks, `500` Iterations)

- `2024 anchor_kin_est_stec_t5` vs `anchor_kin_brdc_t3`: **`+93.63%`** H gain (`+1.2242 m`, 95% CI `[+0.9584, +1.4578] m`, win `99.65%`).
- `2011 anchor_kin_est_stec_t5` vs `anchor_kin_brdc_t3`: **`+94.74%`** H gain (`+1.3823 m`, 95% CI `[+1.0583, +1.6663] m`, win `99.79%`).
- `2011 vrs_causal_ipp_kin_brdc_t3` vs `anchor_kin_brdc_t3`: **`+13.19%`** H gain (`+0.1924 m`, 95% CI `[+0.0269, +0.3276] m`, win `81.87%`); vs offline `vrs_off_ipp_kin_brdc_t3`: **`-98.02%`** (`-0.6270 m`, 95% CI `[-0.7447, -0.4905] m`, reflecting causal arc-leveling transient loss vs offline median leveling).
- `2011 vrs_off_ipp_kin_est_stec_t5` vs `anchor_kin_est_stec_t5`: **`-745.09%`** (`-0.5717 m`, 95% CI `[-0.6878, -0.4469] m`) — decisive empirical proof that `ANCHOR_RELATIVE_FLOAT` VRS cannot outperform integer-fixed `est-stec` single-base until VRS synthesis becomes integer-ambiguity-preserving.

---

## 4. Limitations, Safety Verdict & Reproducibility

- **Operational Verdict:** Current `ANCHOR_RELATIVE_FLOAT` VRS remains **`NOT_APPROVED`** (`VRS_GEOMETRY_ONLY` / `OPERATIONAL_APPROVED = FORBIDDEN`). Conversely, verified physical-anchor long-baseline single-base RTK with `est-stec` + `est-ztd` + `FalseFixGuard` (`arthres=5.0`, persistence `>=3`) achieved genuine centimetre-level offline validation (`2.59 cm` static, `7.67–8.33 cm` kinematic, `0` escapes) on two authentic Nigerian baselines (`105.6 km` & `216.3 km`), though live real-time field validation remains `BLOCKED` pending real CORS streams (B-09) and hardware receiver trials (Phase 16).
- **Reproducibility:**
  ```bash
  NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b03_network_iar_sprint.py
  .venv/bin/python -m pytest research/vrs_generator/tests/test_network_iar.py -v
  ```
