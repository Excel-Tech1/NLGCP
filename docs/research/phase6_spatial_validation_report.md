# Phase 6 Spatial Interpolation and Stratified LOOCV Validation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Phase:** Phase 6 — Spatial Modelling & Network Comparison (Experiment 4)
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Validation Status:** `TECHNICALLY_VALIDATED` (reproducible multi-day LOOCV across 165,000+ identical real-data observations; operational promotion remains `BLOCKED` pending verified 2011 coordinates)

---

## 1. Scientific Question Resolved

In the earlier 2024 DOY 026 Phase 6 pilot (`4` stations, `n = 15,948`), the `zero` control (`3.076 m` RMSE) beat every spatial interpolator (`idw 3.352 m`, `nearest 3.757 m`, `planar 14.373 m`). This sprint tested two concrete hypotheses on real multi-day Nigerian data using `scripts/run_phase6_atmospheric_sprint.py --stride 4` (derived results in `/home/excellence/nlgcp-data/processed/atmospheric-model/sprint-phase67/phase6_sprint_summary.json`):

1. **Observable-Bias Hypothesis:** Did independent per-station arc detrending inflate residuals with mismatched-arc median offsets?
2. **Geometry-Extrapolation Hypothesis:** Did `zero` win in 2024 because all 4 folds were **extrapolation** outside the 3-reference triangle, whereas **true interior convex-hull interpolation** on a 9-station Nigerian network yields substantial spatial-modelling gain?

**Both hypotheses were decisively confirmed.**

---

## 2. Multi-Day Stratified LOOCV Results (2011 9-Station Networks — 4 Interior vs. 5 Perimeter Stations)

Every comparison below evaluates all six models (`zero`, `nearest`, `idw`, `idw2`, `planar`, `ipp_idw2`) on **strictly identical `(epoch, satellite, target)` sample sets**, with per-fold re-anchoring to the fold's nearest available reference (eliminating fixed-datum artifacts and zero-target degeneracy).

### 2.1 Common-Overlap Pair-Arc Differential L1 Ionosphere (`common_arc_sd_l1_iono`)

| Date (Season) | Stratum | Identical Samples (`n`) | `zero` RMSE (m) | `idw` RMSE (m) | `idw2` RMSE (m) | `ipp_idw2` RMSE (m) | `planar` RMSE (m) | Best Model | Best Gain vs. `zero` | Best P95 `|err|` (m) vs. `zero` |
|---|---|---|---|---|---|---|---|---|---|---|
| `2011-03-20` (Equinox) | **Interior (4 sts)** | `23,086` | `0.3587` | `0.2983` (`+16.84%`) | **`0.2595`** | `0.2605` (`+27.36%`) | `0.3231` (`+9.91%`) | **`idw2`** | **`+27.66%`** | `0.5381` vs. `0.7824` |
| `2011-03-20` (Equinox) | Perimeter (5 sts) | `27,897` | `0.5458` | `0.5934` (`-8.73%`) | `0.5443` | `0.5453` (`+0.09%`) | `0.6248` (`-14.48%`) | `idw2` | `+0.27%` | `1.1570` vs. `1.1513` |
| `2011-03-21` (Equinox) | **Interior (4 sts)** | `22,772` | `0.4290` | `0.3158` (`+26.38%`) | `0.3034` (`+29.29%`) | **`0.3008`** | `0.3132` (`+27.00%`) | **`ipp_idw2`** | **`+29.89%`** | `0.5497` vs. `0.8032` |
| `2011-03-21` (Equinox) | Perimeter (5 sts) | `27,466` | `0.4670` | `0.4901` (`-4.96%`) | `0.4479` (`+4.09%`) | **`0.4466`** | `0.4642` (`+0.59%`) | `ipp_idw2` | `+4.37%` | `0.9745` vs. `1.0368` |
| `2011-12-05` (Solstice) | **Interior (4 sts)** | `19,854` | `0.4546` | `0.3718` (`+18.22%`) | **`0.3233`** | `0.3266` (`+28.16%`) | `0.3781` (`+16.84%`) | **`idw2`** | **`+28.89%`** | `0.6760` vs. `0.9330` |
| `2011-12-05` (Solstice) | Perimeter (5 sts) | `24,175` | `0.7338` | `0.8786` (`-19.74%`) | `0.7884` (`-7.44%`) | `0.7879` (`-7.37%`) | **`0.6152`** | `planar` | `+16.16%` | `1.2099` vs. `1.6025` |

### 2.2 Nighttime Receiver-DCB-Aligned STEC Differential L1 Ionosphere (`nighttime_leveled_sd_l1_iono`)

Preserving full diurnal spatial ionospheric gradients without removing per-arc daytime means:

| Date (Season) | Stratum | Identical Samples (`n`) | `zero` RMSE (m) | `idw` RMSE (m) | `idw2` RMSE (m) | `ipp_idw2` RMSE (m) | `planar` RMSE (m) | Best Model | Best Gain vs. `zero` | Best P95 `|err|` (m) vs. `zero` |
|---|---|---|---|---|---|---|---|---|---|---|
| `2011-03-20` (Equinox) | **Interior (4 sts)** | `23,113` | `0.5088` | `0.4073` (`+19.96%`) | `0.3624` (`+28.78%`) | **`0.3594`** | `0.4168` (`+18.09%`) | **`ipp_idw2`** | **`+29.37%`** | `0.7168` vs. `1.0543` |
| `2011-03-20` (Equinox) | Perimeter (5 sts) | `27,916` | **`0.6671`** | `0.7563` (`-13.38%`) | `0.6805` (`-2.02%`) | `0.6808` (`-2.06%`) | `0.7535` (`-12.95%`) | **`zero`** | `0.00%` | `1.3857` |
| `2011-03-21` (Equinox) | **Interior (4 sts)** | `22,814` | `0.5321` | `0.4039` (`+24.10%`) | `0.3754` (`+29.46%`) | **`0.3726`** | `0.5416` (`-1.78%`) | **`ipp_idw2`** | **`+29.98%`** | `0.6912` vs. `1.0136` |
| `2011-12-05` (Solstice) | **Interior (4 sts)** | `19,885` | `0.5486` | `0.4754` (`+13.34%`) | **`0.4052`** | `0.4071` (`+25.79%`) | `0.4258` (`+22.38%`) | **`idw2`** | **`+26.14%`** | `0.7907` vs. `1.0673` |
| `2011-12-05` (Solstice) | Perimeter (5 sts) | `24,207` | `0.8403` | `1.0618` (`-26.35%`) | `0.9384` (`-11.67%`) | `0.9375` (`-11.56%`) | **`0.6473`** | `planar` | `+22.97%` | `1.2952` vs. `1.7769` |

### 2.3 Per-Station Fold Breakdown on `2011-03-20` (`nighttime_leveled_stec_l1`)

| Target Station | Geometry Class | Nearest Ref (km) | `n` | `zero` RMSE (m) | `idw2` RMSE (m) | `ipp_idw2` RMSE (m) | `planar` RMSE (m) | `ipp_idw2` Gain vs. `zero` |
|---|---|---|---|---|---|---|---|---|
| `OSGF` (Abuja) | **INTERIOR** | `CGGT` (`216.3`) | `5,876` | `0.6068` | `0.3265` | **`0.3176`** | `0.3785` | **`+47.66%`** |
| `UNEC` (Enugu) | **INTERIOR** | `RUST` (`188.7`) | `5,732` | `0.4260` | `0.2659` | **`0.2645`** | `0.3255` | **`+37.91%`** |
| `ABUZ` (Zaria) | **INTERIOR** | `CGGT` (`197.0`) | `5,759` | `0.4918` | **`0.3256`** | `0.3273` | `0.4235` | **`+33.46%`** |
| `CGGT` (Toro) | **INTERIOR** | `ABUZ` (`197.0`) | `5,746` | `0.4913` | `0.4925` | **`0.4891`** | `0.5166` | `+0.45%` |
| `ULAG` (Lagos) | PERIMETER | `RUST` (`439.6`) | `5,711` | `0.8565` | `0.7250` | **`0.7230`** | `1.0013` | `+15.59%` |
| `FUTY` (Yola) | PERIMETER | `MDGR` (`283.8`) | `5,364` | `0.5809` | **`0.5725`** | `0.5725` | `0.6606` | `+1.43%` |
| `BKFP` (Birnin Kebbi) | PERIMETER | `ABUZ` (`400.1`) | `5,641` | **`0.7509`** | `0.7770` | `0.7788` | `0.7804` | `-3.71%` |
| `MDGR` (Maiduguri) | PERIMETER | `FUTY` (`283.8`) | `5,556` | **`0.6290`** | `0.7562` | `0.7572` | `0.7222` | `-20.38%` |
| `RUST` (Port Harcourt) | PERIMETER | `UNEC` (`188.7`) | `5,644` | **`0.4300`** | `0.5301` | `0.5306` | `0.5068` | `-23.41%` |

*(On `2011-12-05` `common_pair_arc_l1`, `OSGF` achieved `+43.67%`, `UNEC` `+30.29%`, `CGGT` `+27.16%`, and `ABUZ` `+17.31%` — all four interior stations showing strong positive interpolation gains!)*

---

## 3. Comparison Against Legacy Detrending and 2024 Verified Benchmark

1. **4.7× Reduction in Baseline Noise from Fixing Mismatched-Arc Detrending:** On `2011-03-20`, legacy independent arc detrending (`pair_sd_proxies`) had `zero` RMSE = `2.2084 m` overall (`2.0612 m` interior), whereas `common_arc_sd_l1_iono` reduced `zero` RMSE to `0.4704 m` overall (`0.3587 m` interior, `0.2595 m` with `idw2`). On `2024-01-26` (verified IGS20), `common_arc_sd_l1_iono` reduced the `zero` baseline from legacy `3.076 m` to `0.7089 m` (`4.3×` cleaner).
2. **2024 DOY 026 Verified-IGS20 Benchmark (`0` Interior Stations — Pure Extrapolation):**
   - `iono_2024d026_common_arc` (`n = 20,020`, 100% perimeter extrapolation): **`zero` wins** (`0.7089 m` vs. `idw2 0.7141 m [-0.73%]`, `ipp_idw2 0.7158 m [-0.98%]`, `idw 0.7243 m [-2.18%]`, `planar 1.6345 m [-130.57%]`).
   - `iono_2024d026_nighttime` (`n = 20,064`, 100% perimeter extrapolation): **`zero` wins** (`idw2 -1.29%`, `planar -112.29%`).
   - `pride_zwd_loocv_2024d026` (`n = 2,880`, 100% perimeter extrapolation): **`zero` wins** (`0.0528 m` vs. `idw 0.0603 m [-14.08%]`, `planar 0.1793 m [-239.18%]`) due to the nonlinear coastal-vs-Harmattan moisture gradient across 105–1,029 km.
   - `pride_slant_tropo_loocv_2024d026` (`n = 20,668`): **`planar` wins (`+57.70%`, `0.5040 m → 0.2132 m`)** because slant tropospheric delay varies smoothly with elevation geometry and station height across the network.

---

## 4. Scientific Conclusions & Governance Impact

1. **Spatial interpolation genuinely works inside Nigeria's CORS convex hull:** Across **all three 9-station days** spanning both March equinox (`2011-03-20..21`) and December solstice (`2011-12-05`) and both ionospheric estimators, **`idw2` and `ipp_idw2` consistently deliver `+26.1%` to `+30.0%` interior RMSE reduction over `zero`** (and up to **`+47.7%`** at centrally enclosed Abuja `OSGF`).
2. **Convex-hull gating is scientifically mandatory:** Outside the reference convex hull (`BKFP`, `MDGR`, `RUST`, and all 4 stations in 2024), inverse-distance and planar models frequently **degrade** accuracy relative to nearest-station `zero` (by `-2%` to `-131%`). NLGCP's VRS and hybrid decision engines must enforce interior convex-hull gating before enabling atmospheric interpolation, falling back safely to `ZERO` / single-base outside the hull.
3. **Operational Promotion Remains Blocked:** Because 2011 station coordinates remain `PROVISIONAL_OSGOF_2011_01_01` and downstream RTK positioning validation is not yet performed, Phase 6 operational policy remains `ZERO_DEFAULT` (`OPERATIONAL_APPROVED = FORBIDDEN`) while `idw2` / `ipp_idw2` are elevated to **`TECHNICALLY_VALIDATED` experimental research candidates**.
