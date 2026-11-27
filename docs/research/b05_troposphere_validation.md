# B-05 Tropospheric Modelling Validation Report (`54` Authentic Station-Days)

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-05 — Tropospheric Modelling Validation  
**Date:** 2026-11-26  
**Classification:** `IMPLEMENTED` | `UNIT_TESTED` | `INDEPENDENTLY_VALIDATED` (vs. `54` PRIDE PPP-AR 3.2.8 ZTD station-days) | Operational Status: `NOT_APPROVED`

---

## 1. Objective

Validate hydrostatic (`ZHD`), wet (`ZWD`), and total (`ZTD`) tropospheric modelling across Nigeria's coastal-humid and inland-Harmattan regimes by benchmarking `UNB3m` climatology (Leandro et al. 2006, explicitly classified as **`MODELLED` climatology**, never observed meteorology), legacy `0.12 m` ZWD prior, `CausalTropoZwdFilter`, and spatial ZWD LOOCV against **`54` authentic PRIDE PPP-AR 3.2.8 ZTD station-days** (`50` from B-04 2011 + `4` from 2024 DOY 026).

---

## 2. Multi-Season Evaluation Against PRIDE PPP-AR 3.2.8 ZTD (`54` Station-Days)

| Date | Season / Window | Stations | UNB3m ZHD RMSE (mm) | UNB3m ZWD RMSE (m) | UNB3m ZTD RMSE (m) | Legacy `0.12 m` ZTD RMSE (m) | Causal 1-Step ZWD RMSE (mm) |
|---|---|---:|---:|---:|---:|---:|---:|
| `2011-03-20` | Equinox (`2011_MAR`) | 9 | `5.41` | `0.1232` | `0.1275` | `0.1095` | **`2.87`** |
| `2011-03-21` | Equinox (`2011_MAR`) | 9 | `5.47` | `0.1170` | `0.1211` | `0.1079` | **`2.79`** |
| `2011-12-05` | Harmattan (`2011_DEC`) | 8 | `1.72` | `0.1499` | `0.1500` | `0.0461` | **`3.88`** |
| `2011-12-06` | Harmattan (`2011_DEC`) | 8 | `1.72` | `0.1383` | `0.1384` | `0.0391` | **`3.63`** |
| `2011-12-07` | Harmattan (`2011_DEC`) | 8 | `1.72` | `0.1328` | `0.1330` | `0.0405` | **`3.48`** |
| `2011-12-08` | Harmattan (`2011_DEC`) | 8 | `1.72` | `0.1529` | `0.1530` | `0.0474` | **`4.07`** |
| `2024-01-26` | Dry Harmattan (`2024_JAN`) | 4 | `1.85` | `0.0986` | `0.0996` | `0.0703` | **`2.52`** |
| **Aggregate (`54` station-days)** | **All Windows** | **54** | **`1.7–5.5`** | **`0.1333`** | — | — | **`3.63`** |

### Coastal vs. Inland Wet-Delay Gradient Discovery
- **Coastal stations (`ULAG, RUST, PHRI00NGA, EKAK00NGA`):** UNB3m ZWD RMSE = **`0.0584 m` (`58.4 mm`)**.
- **Inland/Northern stations (`ABUZ, BKFP, CGGT, FUTY, MDGR, OSGF, UNEC, ABFC, MGBO`):** UNB3m ZWD RMSE = **`0.1450 m` (`145.0 mm`)** — **2.48× worse**!
- **Physical Explanation:** UNB3m's latitude-band annual climatology assumes persistent tropical humidity at `6°–14° N` year-round and cannot resolve Nigeria's sharp dry-season **Harmattan** continental airmass (`ZWD` drops to `~0.04–0.11 m` inland in Dec/Jan while remaining `~0.23–0.28 m` along the Niger Delta / Lagos coast). Consequently, during Harmattan, the static `0.12 m` prior actually outperformed UNB3m on absolute ZTD (`4–7 cm` vs. `10–15 cm`), whereas UNB3m's hydrostatic ZHD remained excellent (`1.7–5.5 mm`).

---

## 3. Spatial ZWD Interpolation LOOCV (PRIDE ZTD)

| Date | Regime | Overall Best (`RMSE`, `gain%`) | Interior Best (`RMSE`, `gain%`) | Perimeter Best (`RMSE`, `gain%`) | Coastal vs. Inland |
|---|---|---|---|---|---|
| `2011-03-20` | Equinox moist gradient (9 st) | **`planar`** (`34.2 mm`, **`+35.28%`**) | **`planar`** (`32.3 mm`, **`+44.62%`**) | **`planar`** (`35.7 mm`, `+25.75%`) | Both benefit from `planar` (`+20.6%` coast, `+37.5%` inland) |
| `2011-12-05` | Dry Harmattan (8 st) | `planar` (`36.9 mm`, `+2.01%`) | **`zero`** (`15.4 mm`; `planar` `-91.21%`) | `planar` (`40.8 mm`, `+11.63%`) | Coastal `zero` (`35.9 mm`, `planar` `-47.4%`); Inland `planar` (`+10.3%`) |
| `2024-01-26` | Sparse 4-station Harmattan | **`zero`** (`52.8 mm`; `planar` `-239.31%`) | N/A (`0` interior) | **`zero`** (`52.8 mm`) | Coastal `planar` (`+11.2%`); Inland `zero` (`44.6 mm`, `planar` `-455.8%`) |

**Key takeaway:** Planar spatial interpolation of ZWD works strongly (`+35–45%`) ONLY when a smooth synoptic north–south moisture gradient spans a dense 8–9 station network (`2011-03-20`), but degrades sharply under dry inland Harmattan flatness (`-91%`) or sparse 4-station extrapolation (`-239%`). Therefore, **nearest-station / `ZERO` differential ZWD or height-scaled UNB3m + per-station causal ZWD estimation** is safer than unguarded planar ZWD extrapolation.

---

## 4. Limitations & Reproducibility

- **No Observed Surface Meteorology:** No co-located pressure/temperature/humidity (`RINEX MET`) sensors exist in the 2011 or 2024 NIGNET archives. UNB3m must never be presented as observed meteorology.
- **Upstream Real-Time ZWD Dependency:** `CausalTropoZwdFilter` (`3.63 mm` 1-step RMSE) validates the causal temporal filter, gap-decay, and health-gating layer; operational real-time deployment requires coupling it to a live RT-PPP or network RTK ZWD estimator (e.g., B-03 joint `delta_ZWD` estimation).
- **Reproducibility:**
  ```bash
  NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b05_atmospheric_sprint.py --stride 4
  ```
