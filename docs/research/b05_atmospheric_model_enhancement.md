# B-05 Atmospheric Model Enhancement Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-05 — Atmospheric Model Enhancement  
**Date:** 2026-11-26  
**Status Classification:**  
- **Implementation:** `IMPLEMENTED` ([causal_iono.py](file:///home/excellence/NLGCP/research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/causal_iono.py), [causal_tropo.py](file:///home/excellence/NLGCP/research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/causal_tropo.py), [run_b05_atmospheric_sprint.py](file:///home/excellence/NLGCP/scripts/run_b05_atmospheric_sprint.py))  
- **Testing:** `UNIT_TESTED` (`6/6` strict causality, DCB/OSB, IONEX, and gap-decay tests passing)  
- **Validation:** `INDEPENDENTLY_VALIDATED` (against CODE IONEX GIM, CODE/CAS DCB/OSB, and `54` authentic PRIDE PPP-AR 3.2.8 ZTD station-days)  
- **Operational Approval:** `NOT_APPROVED` (operational spatial default remains **`ZERO`**; `OPERATIONAL_APPROVED = FORBIDDEN`)  
- **Result Classification:** `AUTHENTIC_OBSERVATION` (with `MODELLED` climatological UNB3m explicitly separated from `AUTHENTIC_OBSERVATION` / PRIDE-estimated ZTD)

---

## 1. Objective

Upgrade NLGCP's Phase 6 offline atmospheric modelling framework to support strictly causal epoch-by-epoch ionospheric and tropospheric estimation, authentic external DCB/OSB and IONEX GIM integration, multi-day/multi-season evaluation using **B-04 verified 2011 coordinates (`IGS05`/`IGS08`)** and **2024 verified `IGS20` coordinates**, and stratified spatial validation with paired block-bootstrap 95% confidence intervals—without conflating offline research reconstruction with operational real-time approval.

---

## 2. Methods & Architecture

1. **Causal Ionospheric Engine ([causal_iono.py](file:///home/excellence/NLGCP/research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/causal_iono.py)):**
   - Strictly causal `CausalIonoFilter`: epoch `k` depends exclusively on observations at epochs `<= k` (formally verified via bit-identical prefix-invariance tests).
   - Online Welford Melbourne-Wübbena (MW) + Geometry-Free (GF) + LLI/cadence cycle-slip detector with bounded per-satellite state and automatic arc reset.
   - Recursive `sin^2(el)` elevation-weighted carrier-to-code leveling with online formal leveling uncertainty (`leveling_sigma_tecu`).
   - External satellite bias parsers (`parse_code_monthly_dcb`, `combine_code_p1p2_p1c1_to_c1p2`, `parse_sinex_dsb`, `parse_sinex_osb_pair_diff`) and IONEX 1.0/1.1 sun-fixed rotated-longitude interpolator (`parse_ionex`, Schaer et al. 1998).
   - Strictly causal `CausalNetworkDiffIonoTracker` producing both causal pair-arc differential L1 ionosphere and causal DCB-aligned leveled differential L1 ionosphere.
2. **Causal Tropospheric Engine ([causal_tropo.py](file:///home/excellence/NLGCP/research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/causal_tropo.py)):**
   - Strictly causal scalar Kalman/damped-random-walk `CausalTropoZwdFilter` estimating `delta_ZWD(t)` around the UNB3m climatological prior (`Leandro et al. 2006`), relaxing smoothly back to UNB3m across outages (`tau = 7200 s`), inflating formal covariance when stale (`gap > 900 s`), and gating unhealthy stations fail-closed.
3. **Stratified Spatial Validation & Bootstrap CIs ([run_b05_atmospheric_sprint.py](file:///home/excellence/NLGCP/scripts/run_b05_atmospheric_sprint.py)):**
   - Evaluates `zero`, `nearest`, `idw`, `idw2`, `planar`, and `ipp_idw2` on identical comparison keys across interior, perimeter, coastal, inland, quiet (`06–12 UTC`), disturbed (`18–24 UTC`), and sparse 4-station strata with `400`-iteration `20`-epoch block-bootstrap 95% confidence intervals (`seed = 20261126`).

---

## 3. Input Datasets & Provenance

| Dataset / Product | Applicable Date(s) | Frame / Truth Tier | Provenance / SHA-256 Prefix |
|---|---|---|---|
| `NIGNET2011.zip` (9 / 8 stations) | `2011-03-20`, `2011-03-21`, `2011-12-05` | B-04 `VERIFIED_IGS05_PPP_FLOAT` (Mar) / `VERIFIED_IGS08_PPP_FLOAT` (Dec) | `8ccb0045…` (immutable archive); `RUST` excluded Dec (`L2=0%`) |
| `2024` NIGNET (`ABFC, EKAK, MGBO, PHRI`) | `2024-01-26` (DOY 026) | `VERIFIED_IGS20_PPP_AR` | Phase 4/5 admitted RINEX + `BRDC00IGS_R_20240260000_01D_MN.rnx` |
| 2011 GPS Broadcast Nav (`brdc{079,080,339}0.11n.Z`) | `2011-03-20..21`, `2011-12-05` | GPS Broadcast | BKG recovery run `run-20261030T132927Z` |
| CODE Monthly DCBs (`P1P2/P1C1` `1103`, `1112`) | Mar & Dec 2011 | `CODE_BIAS` | AIUB HTTPS; hashed in `precise_products_manifest.json` |
| CODE/CAS 2024 Biases (`COD0OPSFIN OSB`, `CAS0OPSRAP DCB`) | `2024-01-26` | `SINEX_OSB` / `SINEX_DSB` | AIUB / BKG HTTPS (`98ae580e…`, `d6299e7b…`) |
| CODE IONEX GIM (`CODG{079,080,339}0.11I.Z`, `COD0OPSFIN...GIM.INX.gz`) | 2011 & 2024 | `IONEX_GIM` | AIUB HTTPS (`0ebab70e…`, `25d8d366…`, `7e75a006…`, `6a9e8af1…`) |
| PRIDE PPP-AR 3.2.8 ZTD (`54` station-days) | 6×2011 days (`50`) + `2024-01-26` (`4`) | `IGS05` / `IGS08` / `IGS20` | B-04 `runs/igs/` + Phase 3/6 `working/pride*` |

- **Software:** Python `3.12.3`, `nlgcp_atmospheric_model` (`b05-causal-iono-v1.0`, `b05-causal-tropo-v1.0`), PRIDE PPP-AR `3.2.8` (`4907bfe5…`).
- **Machine-Readable Archive:** `/home/excellence/nlgcp-data/processed/atmospheric-model/b05/b05_validation_summary.json` (`stride = 4`, `120 s` sampling, `720` epochs/day).

---

## 4. Key Findings & Model Selection Decisions

1. **Causal vs. Offline Parity:** Strictly causal epoch-by-epoch pair-arc ionospheric interpolation matches offline full-arc LOOCV gains inside the 9-station convex hull (`+27.48%` vs. `+27.36%` on `2011-03-20`; `+30.35%` vs. `+29.89%` on `2011-03-21`; `+30.43%` vs. `+28.46%` on `2011-12-05`), while honestly quantifying early-arc convergence penalty (`0.66–1.19 m` for `<=15` epochs decaying to `0.32–0.72 m` steady-state).
2. **External DCB/IONEX Calibration Breakthrough:** Applying CODE/CAS satellite DCBs and causal receiver DCB tracking reduces station VTEC RMSE against CODE IONEX GIM by **`80–89%`** across 2011 (`20.0–31.3 TECU` uncalibrated → `3.25–4.72 TECU` calibrated) and **`62–78%`** in 2024 (`12.5–23.4 TECU` → `4.27–5.10 TECU`).
3. **Geometry- and Regime-Dependent Model Selection:**
   - **Interior convex hull (8–9 stations):** `ipp_idw2` / `idw2` beats `zero` reliably on all 3 verified 2011 days (`+27.5%` to `+30.4%`, 95% block-bootstrap CIs strictly above zero, `bootstrap_win_prob = 1.000`). During quiet daytime gradients (`06–12 UTC`), `planar` achieves `+50.5%` to `+54.1%` interior reduction, but **degrades severely (`-2.9%` to `-9.5%`) during post-sunset equatorial scintillation (`18–24 UTC`)**, where `ipp_idw2` remains robust (`+25.1%` to `+29.6%`).
   - **Perimeter extrapolation & sparse 4-station geometry (`2024-01-26`):** **`ZERO` remains best** (`0.6685 m`; `idw2` CI `[-3.63%, -0.15%]`; `planar` `-91.99%`). On the 4-station sparse 2011 subset (`ABUZ, CGGT, OSGF, ULAG`), `planar` catastrophically diverges (`-550%` to `-847%`).
4. **Troposphere (`54` PRIDE ZTD Station-Days):** UNB3m ZHD is accurate (`1.72–5.47 mm` RMSE), whereas UNB3m climatological ZWD incurs `0.1333 m` RMSE (`0.1450 m` inland Harmattan dry bias vs. `0.0584 m` coastal). Strictly causal 1-step `CausalTropoZwdFilter` achieves **`3.63 mm` (`0.00363 m`)** ZWD RMSE (`-97.3%`).
5. **Decision:** Retain **`ZERO`** as operational fallback; admit **`ipp_idw2`** (causal iono) + **`CausalTropoZwdFilter`** ONLY as `EXPERIMENTAL` / `RESEARCH_VALIDATION` inside verified interior convex hulls with >= 5 healthy references.

---

## 5. Companion Reports, Limitations & Reproducibility

- Companion B-05 reports:
  - [b05_causal_filter_validation.md](file:///home/excellence/NLGCP/docs/research/b05_causal_filter_validation.md)
  - [b05_ionosphere_validation.md](file:///home/excellence/NLGCP/docs/research/b05_ionosphere_validation.md)
  - [b05_troposphere_validation.md](file:///home/excellence/NLGCP/docs/research/b05_troposphere_validation.md)
  - [b05_spatial_validation.md](file:///home/excellence/NLGCP/docs/research/b05_spatial_validation.md)
- **Limitations:** No measured surface meteorology (UNB3m is modelled climatology); causal `CausalTropoZwdFilter` requires an upstream real-time ZWD estimator (e.g. RT-PPP/network filter) rather than post-processed PRIDE ZTD; `stride=4` (`120 s`) sampling had `<5` samples per `300 s` ROTI window (full `30 s` ROTI remains documented in Phase 6 `roti_30s_2011-03-20.json`); operational VRS/NRTK remains `NOT_APPROVED`.
- **Failed Tests:** `0` (`6/6` B-05 unit tests pass; Ruff & strict `mypy` clean).
- **Reproducibility:**
  ```bash
  NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b05_atmospheric_sprint.py --stride 4
  .venv/bin/python -m pytest research/atmospheric_spatial_model/tests/test_causal_iono.py research/atmospheric_spatial_model/tests/test_causal_tropo.py -v
  ```
- **Next Steps:** Evaluate causal B-05 VRS against offline VRS and physical anchors in rover positioning and network integer ambiguity resolution (**Milestone B-03**).
