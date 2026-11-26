# Phase 6 Atmospheric Modelling Implementation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Phase:** Phase 6 — Atmospheric and Spatial Error Modelling (Workstreams A–C)
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Validation Status:** `TECHNICALLY_VALIDATED` (algorithms unit-tested and empirically validated on 2011 NIGNET + 2024 DOY 026 + PRIDE PPP-AR ZTD; operational promotion remains `BLOCKED` pending verified 2011 coordinates and external DCBs)

---

## 1. Root-Cause Diagnosis of Pre-Sprint Phase 6 Limitations

Auditing the pre-sprint Phase 6 codebase (`research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/`) alongside the 2024 DOY 026 pilot revealed four technical and scientific bottlenecks that prevented meaningful ionospheric and tropospheric separation:

1. **Mismatched-arc median bias in `pair_sd_proxies()`:** Detrending each station's geometry-free (GF) carrier-phase arc *independently* before computing inter-station differences injected metre-scale bias whenever two stations had different arc start/end epochs or slip boundaries (explaining the legacy `2.21–3.08 m` zero-baseline RMSE).
2. **Missing ionospheric observables and cycle-slip screening:** Phase 6 previously computed only detrended GF differences — no Melbourne-Wubbena (MW) + GF cycle-slip detection, no phase-leveled STEC/VTEC, no Single-Layer Model (SLM) Ionospheric Pierce Point (IPP) coordinates, and no bias-free ROT / ROTI equatorial irregularity indices.
3. **Naive static tropospheric wet prior (`0.12 m * exp(-h/2000)`):** No tropical climatology (UNB3m) and no validation against the independent **PRIDE PPP-AR 3.2.8** ZTD files already stored on disk for 2024 DOY 026.
4. **3-station-only containment and missing spatial models:** `spatial.py` only checked triangle containment (3 references), lacked inverse-distance-squared (`idw2`), IPP-space (`ipp_idw2`), P95 residual metrics, and stratified interior-vs-perimeter LOOCV reporting.

---

## 2. Implemented Modules and Upgrades

All existing Phase 6 modules and operational default gates (`BEST = ZERO` operationally) were preserved intact. New capabilities were implemented in dedicated, strictly typed modules:

| Module | Key Capabilities Implemented |
|---|---|
| `atmospheric_schema.py` | Unified `AtmosphericEstimate` dataclass, `AtmosphericComponent` enum (strictly separating `RAW_STEC_UNBIASED_UNAVAILABLE`, `BIAS_CORRECTED_STEC`, `VTEC_UNBIASED_UNAVAILABLE`, `ROT_TECU_PER_MIN`, `ROTI_TECU_PER_MIN`, `SLANT_IONO_L1_DIFF`, `ZHD_MODEL`, `ZWD_MODEL`, `ZTD_PPP_PRIDE`, `SLANT_TROPO_TOTAL`), and honest `ValidationStatus` vocabulary. |
| `observations.py` + `satellite_geometry.py` | Added read-only ZIP-stream RINEX 2.11 parsing (`read_rinex2_from_zip`) without mutating raw archives, plus RINEX 2 GPS broadcast navigation parsing (`parse_rinex2_gps_nav` handling plain, `.gz`, and Unix `.Z` BKG files via `gzip -dc`) and `parse_gps_nav_auto`. |
| `dataset_audit.py` | Body-level dual-frequency signal completeness audit (`audit_rinex2_signal_completeness`), arbitrary-N Andrew monotone-chain 2D ENU convex hull (`convex_hull_2d`, `point_in_convex_hull_2d`, `classify_network_geometry`), and reproducible `build_2011_selection_manifest`. |
| `ionosphere_estimation.py` | Combined MW + GF + LLI bit-0 + effective-cadence gap cycle-slip detection (`estimate_station_ionosphere`), sin²(el)-weighted phase-to-code leveling producing uncalibrated STEC (`dcb_status = UNAVAILABLE_EXTERNAL_DCB_NOT_FOUND`, `bias_corrected_stec_tecu = None`), 350 km SLM mapping factor + IPP coordinates + uncalibrated VTEC, bias-free ROT & 5-minute Pi et al. (1997) ROTI, **`common_arc_sd_l1_iono`** (simultaneous pair-arc differential L1 ionosphere fixing the mismatched-arc bias), and **`nighttime_leveled_sd_l1_iono`** (single daily pre-dawn 02:00–05:00 UTC scalar receiver-DCB alignment preserving full daytime spatial gradients). |
| `troposphere_estimation.py` | Full **UNB3m** (Leandro et al. 2006) latitude/DOY Saastamoinen + Askne-Nordius ZHD/ZWD/ZTD model explicitly stamped `MODELLED CLIMATOLOGY — NOT MEASURED STATION METEOROLOGY`, PRIDE PPP-AR `ztd_*` parser (`parse_pride_ztd`), independent benchmark evaluator (`evaluate_tropo_against_pride`), Niell (1996) slant delay mapping (`slant_tropo_from_ztd`), and canonical `AtmosphericEstimate` export. |
| `spatial_estimation.py` | Arbitrary-N ENU convex hull containment (with deterministic subset caching), six identical-sample models (`zero`, `nearest`, `idw`, `idw2`, `planar`, `ipp_idw2`), extended distribution metrics (`bias`, `mae`, `rmse`, `std`, `p95_abs_m`, `p05/p50/p95`, `min/max`, `correlation`), and **`run_stratified_loocv`** separating `interior_interpolated` vs. `perimeter_extrapolated`. |
| `scripts/run_phase6_atmospheric_sprint.py` | Reproducible CLI runner executing Experiments 1–4 across 2011 (`2011-03-20`, `2011-03-21`, `2011-12-05`) and 2024 DOY 026, writing derived JSON artifacts outside Git under `${NLGCP_DATA_ROOT}/processed/atmospheric-model/sprint-phase67/`. |

---

## 3. Experiment 2 Results — Ionospheric Estimation & Nigerian Equatorial Irregularities

### 3.1 Full-Network Dual-Frequency Ionospheric Extraction (`stride=4`, 120 s)

Across the 9 full-day stations on `2011-03-20` (`52,709` single-station dual-frequency GPS estimates above 15° elevation, `48–75` continuous arcs/station), fixing the strided-cadence gap check (using median consecutive epoch spacing rather than raw header `INTERVAL`) eliminated false gap splits and retained `5,568–5,999` clean estimates per station (`4–29` GF slips, `2–14` MW slips, `1–14` LLI/gap slips per station).

### 3.2 Full 30-Second Equatorial ROTI Analysis (`2011-03-20`, Pi et al. 1997 5-Min Window)

Because standard 5-minute ROTI requires `>= 3` ROT increments inside 300 s (unsatisfied at `dt = 120 s`), a dedicated full 30-second (`stride=1`, 2,880 epochs) diagnostic was executed on four north-to-south NIGNET stations (`/home/excellence/nlgcp-data/processed/atmospheric-model/sprint-phase67/roti_30s_2011-03-20.json`):

| Station | Geodetic Lat (°N) | 30 s Estimates | ROTI Samples | Daily Mean ROTI (TECU/min) | Daily Max ROTI (TECU/min) | Pre-Dawn `02–06 UTC` Mean | Post-Sunset `19–23 UTC` Mean | Post-Sunset `ROTI > 0.5` (%) |
|---|---|---|---|---|---|---|---|---|
| `RUST` (Port Harcourt) | `4.80°N` | 23,939 | 23,526 | `0.0905` | **`3.0693`** | `0.0504` | `0.2790` | **`15.73%`** |
| `ULAG` (Lagos) | `6.52°N` | 24,037 | 23,733 | `0.1013` | **`2.0568`** | `0.0503` | **`0.3207`** | **`19.71%`** |
| `OSGF` (Abuja) | `9.03°N` | 23,577 | 23,228 | `0.0847` | `1.7856` | `0.0482` | `0.2501` | `10.41%` |
| `MDGR` (Maiduguri) | `11.83°N` | 23,263 | 22,886 | `0.0912` | `1.6257` | `0.0422` | `0.2635` | `11.99%` |

**Physical Validation:** Our bias-free and ambiguity-free ROTI estimator directly captures West African **post-sunset Equatorial Plasma Bubbles / Equatorial Ionization Anomaly (EIA)** irregularities: ROTI increases **5×–6×** between quiet pre-dawn (`0.042–0.050 TECU/min`) and post-sunset (`0.250–0.321 TECU/min`, 20:00–00:00 WAT), with southern near-equatorial stations (`ULAG 19.71%`, `RUST 15.73%`) experiencing markedly higher severe irregularity occurrence (`ROTI > 0.5 TECU/min`) than central/northern stations (`OSGF 10.41%`, `MDGR 11.99%`). This quantifies a core operational risk for future Nigerian NRTK ambiguity fixing during evening hours.

---

## 4. Experiment 3 Results — Tropospheric Validation Against PRIDE PPP-AR 3.2.8 ZTD (`2024-01-26`)

Comparing both the legacy `0.12 m` wet prior and UNB3m climatology against **11,520 epochs** (`4 stations × 2,880 epochs`) of independent **PRIDE PPP-AR 3.2.8** ZTD truth on `2024-01-26` (DOY 026):

| Station | Lat (°N) | Height (m) | PRIDE Mean ZTD (m) | PRIDE Mean ZWD (m) | Legacy `0.12 m` ZWD (m) | Legacy ZTD RMSE (m) | UNB3m ZWD (m) | UNB3m ZTD RMSE (m) |
|---|---|---|---|---|---|---|---|---|
| `EKAK00NGA` (Coastal) | `4.64°N` | `43.6` | `2.5280` | **`0.2288`** | `0.1174` | `0.1172` | `0.2672` | **`0.0585`** (`-50.1%` vs legacy) |
| `PHRI00NGA` (Coastal) | `4.80°N` | `46.7` | `2.4732` | `0.1751` | `0.1172` | `0.0663` | `0.2668` | `0.1010` |
| `ABFC00NGA` (Central) | `9.03°N` | `532.6` | `2.3016` | `0.1263` | `0.0919` | `0.0392` | `0.2185` | `0.0931` |
| `MGBO00NGA` (Northern) | `11.83°N` | `355.6` | `2.3237` | **`0.1031`** | `0.1005` | `0.0078` | `0.2350` | `0.1320` |

**Aggregate Tropospheric Metrics (n = 11,520 epochs):**
- **UNB3m Hydrostatic ZHD vs. PRIDE ZHD:** RMSE = **`0.00185 m` (1.85 mm!)**, bias `+1.48 mm`, `100.0%` within 5 cm tolerance — confirming near-exact hydrostatic modelling.
- **Wet Delay Climatology Finding (January Harmattan Dry Season):** Nigeria exhibits a sharp **`12.57 cm`** coastal-to-inland ZWD gradient on the exact same winter day (`EKAK00NGA 0.2288 m` moist Niger Delta vs. `MGBO00NGA 0.1031 m` dry Saharan Harmattan air). On humid coastal `EKAK00NGA`, UNB3m halves ZTD RMSE (`11.72 cm → 5.85 cm`), whereas inland during Harmattan, zonally-averaged tropical UNB3m (`0.219–0.235 m`) overpredicts dry-season ZWD by `9–13 cm` (overall aggregate ZWD RMSE `9.86 cm` UNB3m vs. `7.08 cm` legacy). Static zonal climatology is therefore **insufficient by itself** for operational Nigerian wet tropospheric modelling; real-time PPP-estimated ZWD or numerical weather prediction (ERA5/ECMWF) assimilation is required.
