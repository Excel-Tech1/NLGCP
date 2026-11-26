# B-02 Rover Dataset Selection and Independent Truth Assessment

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-02 — Offline Rover Positioning Benchmark
**Date:** 2026-11-25
**Machine-Readable Manifest Output:** `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/dataset_manifest.json`

---

## 1. Candidate Rover Screening Summary

| Candidate ID | Date / DOY | Withheld Rover | Reference Stations | Nearest Anchor & Baseline | Convex-Hull Class | Dual-Freq GPS Continuity (30 s) | Truth Classification | Admission Decision |
|---|---|---|---|---|---|---|---|---|
| **Dataset B (Primary Verified Truth)** | `2024-01-26` / DOY 026 | `PHRI00NGA` (`PHRI0260.24O`) | `ABFC00NGA`, `EKAK00NGA`, `MGBO00NGA` (3 refs; `BKFP00NGA` excluded QC invalid) | `EKAK00NGA` (`105.553 km`) | **OUTSIDE** (extrapolation; hull `181,177.5 km²`) | `2,880 / 2,880` epochs (100%), `C1, P1, P2, L1, L2, S1, S2` | **`VERIFIED_IGS20_PRIDE_PPP_AR`** | **ADMITTED — PRIMARY VERIFIED ACCURACY BENCHMARK** |
| **Dataset A (Secondary Interior Hull)** | `2011-03-20` / DOY 079 | `OSGF` (`OSGF0790.11O` in `NIGNET2011.zip`) | `ABUZ, BKFP, CGGT, FUTY, MDGR, RUST, ULAG, UNEC` (8 refs; partial `CLBR` excluded) | `CGGT` (`216.320 km`) | **INSIDE** (true interpolation; hull `607,707.15 km²`) | `2,880 / 2,880` epochs (100%), `C1, P2, L1, L2, S1, S2` (`P1=0%`) | **`PROVISIONAL_OSGOF_2011_01_01` (`LIMITED_PROVISIONAL_TRUTH`)** | **ADMITTED — EXPLORATORY INTERIOR-HULL BENCHMARK (PROVISIONAL TRUTH ONLY)** |

---

## 2. Independent Positioning Truth Records (Phase C)

### 2.1 Dataset B — `PHRI00NGA` (`VERIFIED_IGS20_PRIDE_PPP_AR`)

| Field | Verified Value |
|---|---|
| Station ID / Marker | `PHRI00NGA` (`PHRI`, Port Harcourt) |
| Truth Tier | **`VERIFIED_IGS20_PRIDE_PPP_AR`** (defensible independent static PPP-AR reference truth) |
| Source File & SHA-256 | `/home/excellence/nlgcp-data/working/pride/run-PHRI00NGA/2024/026/pos_2024026_phri` (`7f62d2466fe9cf2df8acff390a97f4d85a8e456b27ba2b7b3bc9c6dafdc5965f`) |
| ECEF Coordinates (m) | `X = 6308877.98392`, `Y = 772269.10256`, `Z = 530087.60603` |
| Geodetic WGS84 | `Lat = 4.799413510°`, `Lon = 6.978851194°`, `h = 46.7218 m` |
| Reference Frame & Epoch | `IGS20` at observation epoch `2024-01-26T11:59:42Z` (`MJD 60335.4998`) |
| Formal Standard Deviations (`Sig0 * sqrt(S_ii)`) | `σ_X = 0.55 mm`, `σ_Y = 0.16 mm`, `σ_Z = 0.13 mm` (`Sig0 = 2.1837 m`, `Nobs = 26,065`, **45 fixed GPS ambiguities**; realistic external daily PPP-AR accuracy ~5–15 mm) |
| Precise Products Used | `WUM0MGXRAP_20240260000_01D_05M_ORB.SP3`, `30S_CLK.CLK`, `30S_ATT.OBX`, `01D_OSB.BIA`, `01D_ERP.ERP`, `IGS20_2290` ANTEX |
| Receiver / Antenna / ARP Offset | `TRIMBLE NETR9 5.03` / `TRM59900.00 NONE` / `DELTA H/E/N = 0.1710 / 0.0000 / 0.0000 m` (L1 PCO `[-0.40, 0.95, 113.50] mm`, L2 PCO `[0.45, 0.41, 124.54] mm`) |
| RINEX Header Approx XYZ Discrepancy | Header `6308877.8699, 772267.5163, 530082.6335` differs from verified PRIDE truth by **`5.22 m`** — header coordinates are strictly rejected as truth. |

### 2.2 Dataset A — `OSGF` (`PROVISIONAL_OSGOF_2011_01_01` — `LIMITED_PROVISIONAL_TRUTH`)

| Field | Recorded Value |
|---|---|
| Station ID / Marker | `OSGF` (Abuja, OSGoF Headquarters) |
| Truth Tier | **`PROVISIONAL_OSGOF_2011_01_01` (`LIMITED_PROVISIONAL_TRUTH`)** — **NOT** independently verified survey truth |
| Source File | `/home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery/run-20261030T132927Z/coordinate_provenance.csv` |
| Published Provisional ECEF (m) | `X = 6246471.2000`, `Y = 820848.7400`, `Z = 994267.9300` |
| Geodetic WGS84 | `Lat = 9.02766454°`, `Lon = 7.48633050°`, `h = 532.517 m` |
| Reference Frame & Epoch | Published epoch `2011-01-01`; exact ITRF realization, ARP continuity, and formal uncertainty are **undocumented** (`UNKNOWN`). |
| Cross-Check Note (Non-Authoritative) | Compared with 2024 verified `ABFC00NGA` at Abuja (`6246471.1713, 820849.0206, 994268.1665`), the 13.07-year vector `(-0.029, +0.281, +0.236) m` (`0.368 m` ≈ `2.8 cm/yr` NE) is consistent with Nubian plate motion, but monument/ARP identity is unproven so `OSGF` cannot be promoted to verified truth. |
| Receiver / Antenna / ARP Offset | `TRIMBLE NETR9 4.22` / `TRM59800.00` / `DELTA H/E/N = 0.1710 / 0.0000 / 0.0000 m` (identical antenna type and `0.1710 m` height across all 9 stations on `2011-03-20`!). |
| RINEX Header Approx XYZ Discrepancy | Header `6246471.0529, 820848.7374, 994268.6823` differs by **`0.77 m`** from OSGoF 2011-01-01 — header coordinates are never used as truth. |
| Independent 2011 PPP Availability | **BLOCKED offline:** zero 2011 SP3/CLK/ERP/OSB products exist in `/home/excellence/nlgcp-data`. |

---

## 3. Target Leakage & Separation Controls

For both datasets, the benchmark runner enforces programmatically (`assert_no_rover_leakage()`):
1. `rover_station_id not in reference_stations`
2. `rover_station_id not in reference_datasets`
3. `rover_station_id not in iono_field_stations`
4. `rover_station_id not in reference_ztd_stations`
5. Physical-anchor baseline uses a physically distinct station (`EKAK00NGA` at `105.553 km` for `PHRI00NGA`; `CGGT` at `216.320 km` for `OSGF`) and never uses the rover's observations as base input.
