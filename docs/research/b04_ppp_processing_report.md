# B-04 PRIDE PPP-AR 3.2.8 Processing Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-04 — Coordinate Verification  
**Date:** 2026-11-26  
**Classification:** `IMPLEMENTED` | `INDEPENDENTLY_VALIDATED` (`PRIDE PPP-AR 3.2.8`, IGS + CODE cross-AC) | Operational Status: `NOT_APPROVED`  
**Runner:** [scripts/run_b04_pride_ppp.py](file:///home/excellence/NLGCP/scripts/run_b04_pride_ppp.py)  
**Outputs:** `/home/excellence/nlgcp-data/processed/b04-coordinate-verification/{pride_ppp_igs_54,pride_ppp_code_crosscheck_18}.json`

---

## 1. Objective

Process the 9 priority Nigerian CORS stations (`ABUZ, BKFP, CGGT, FUTY, MDGR, OSGF, RUST, ULAG, UNEC`) across the 6 full-day 2011 observation windows (`2011-03-20..21` and `2011-12-05..08`) using PRIDE PPP-AR 3.2.8 in strictly frame-separated static GPS PPP mode, and cross-check IGS Final solutions against independent CODE Final solutions.

---

## 2. Software, Configuration & Input Verification

- **Software:** Installed **PRIDE PPP-AR 3.2.8** (`/home/excellence/PRIDE-PPPAR`, commit `4907bfe5ba1e9d9faf90414fcf7a2bed5ad44695`; binaries in `/home/excellence/.PRIDE_PPPAR_BIN/`).
- **Offline Isolation:** Generated a derived `pdp3_offline.sh` wrapper (`OFFLINE=YES`) in `processed/b04-coordinate-verification/bin/` without mutating the upstream PRIDE installation or `NIGNET2011.zip` (`8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf`).
- **Processing Mode & Options:**
  - Static GPS dual-frequency ionosphere-free PPP-float (`-m S -f -sys G -hion`, `amb_fixing = NO` due to absence of 2011 OSB phase biases).
  - Second-order ionospheric correction enabled (`Iono 2nd = YES`) using CODE `CODG*.11I` IONEX grids.
  - Ocean tide loading (`FES2004S1.dat`), GPT3 troposphere (`gpt3_1.grd`), leap seconds (`leap.sec`), and satellite parameters (`sat_parameters`).
  - **Strict Frame/ANTEX Isolation:**
    - March 2011 (`DOY 079–080`, `IGS05`): `tables_igs05/` symlinked to `igs05_1617.atx` (IGS Final) / `igs05_1627.atx` (CODE).
    - December 2011 (`DOY 339–342`, `IGS08`): `tables_igs08/` symlinked to `igs08_1648.atx` (IGS Final) / `igs08_1731.atx` (CODE).
- **RINEX Header Audit:**
  - All 54 files verified as `30.0 s` GPS-time RINEX 2.11 (`TRIMBLE NETR8` v4.19/4.22; `TRIMBLE NETR9` v4.22 at `MDGR` & `OSGF`).
  - Uniform antenna `TRM59800.00` (blank radome → `NONE`) with `ANTENNA: DELTA H/E/N = 0.1710 / 0.0000 / 0.0000 m`.
  - No silent RINEX edits were performed; extracted copies are strictly derived work files.

---

## 3. Execution Summary

| Batch | Products | Jobs Attempted | `OK` | `FAILED` | Failure Cause |
|---|---|---:|---:|---:|---|
| **Primary (IGS Final, 6 days × 9 stations)** | `igs*.sp3` + `igs*.clk_30s` + `igs*.erp` | 54 | **50** | **4** | `RUST` DOY `339–342` (`2011-12-05..08`): `L2=0%`, `P2=0%` (single-frequency outage; PRIDE wrote empty `pos_*`, fail-closed rejected). |
| **Cross-AC Check (CODE Final, DOY `079` & `339` × 9 stations)** | `COD*.EPH` + `COD*.CLK_05S` + `COD*.ERP` | 18 | **17** | **1** | `RUST` DOY `339` (`2011-12-05`): identical single-frequency L2/P2 outage. |

---

## 4. Per-Solution Quality Metrics (IGS Final `50/54 OK`)

- **March 2011 (`IGS05`, `18/18` OK):**
  - Dual-frequency observations per station-day: `27,011 – 27,908`.
  - Phase residual RMS: `12.0 – 21.0 mm` (higher due to March 2011 solar-cycle/equatorial ionospheric scintillation + 30 s clock interpolation + float solution).
  - Formal daily 1-sigma ENU: `E 0.38–0.53 mm`, `N 0.14–0.20 mm`, `U 0.67–0.94 mm` (formal LSQ covariance prior to empirical scaling).
- **December 2011 (`IGS08`, `32/36` OK; `RUST` `0/4`):**
  - Dual-frequency observations per station-day: `24,818 – 27,150`.
  - Phase residual RMS: `8.0 – 13.0 mm`.
  - Formal daily 1-sigma ENU: `E 0.29–0.35 mm`, `N 0.11–0.13 mm`, `U 0.51–0.63 mm`.
- **Independent Cross-AC Agreement (`IGS Final - CODE Final`):**
  - **DOY 079 (`IGS05`):** 3D difference `6.72 – 9.51 mm` across all 9 stations (`mean ~8.1 mm`).
  - **DOY 339 (`IGS08`):** 3D difference `4.04 – 4.51 mm` across all 8 healthy stations (`mean ~4.3 mm`).

---

## 5. Limitations & Unresolved Issues

1. **PPP-Float vs PPP-AR:** Without 2011 SINEX OSB phase biases, PRIDE ran in static GPS PPP-float (`amb_fixing = NO`). Daily repeatability (`1.35 – 2.98 mm` 3D in Dec; `2.64 – 13.08 mm` 3D in Mar) confirms centimetre-to-sub-centimetre accuracy, though formal covariance underestimates true external uncertainty by ~5–10× (standard for unscaled GNSS LSQ).
2. **`RUST` December 2011 L2/P2 Outage:** `RUST` cannot be verified in `IGS08` (`2011_DEC`) because L2 carrier phase and P2 pseudorange are missing across DOY `339–342`. `RUST` remains `VERIFIED_IGS05_PPP_FLOAT` (March) and `UNVERIFIED` (December).
3. **Radome Assumption:** NIGNET RINEX headers leave the antenna radome field blank (`TRM59800.00     `), mapped by IGS/PRIDE convention to `TRM59800.00     NONE`. Any undocumented physical radome would introduce an unmodeled vertical PCO offset (~few cm); no monument photos/site logs exist in the archive to rule this out independently.

---

## 6. Reproducibility

```bash
NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b04_pride_ppp.py --acs IGS
NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b04_pride_ppp.py --acs CODE --doys 079,339 --out-name pride_ppp_code_crosscheck_18.json
```
