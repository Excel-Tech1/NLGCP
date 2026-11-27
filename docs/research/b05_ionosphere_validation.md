# B-05 Ionospheric Modelling & External DCB/IONEX Validation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-05 — Ionospheric Modelling Validation  
**Date:** 2026-11-26  
**Classification:** `IMPLEMENTED` | `UNIT_TESTED` | `INDEPENDENTLY_VALIDATED` (vs. CODE IONEX GIM & CODE/CAS Biases) | Operational Status: `NOT_APPROVED`

---

## 1. Objective

Validate dual-frequency GPS ionospheric estimation across Nigerian equatorial latitudes while maintaining strict provenance separation between:
1. **Uncalibrated phase-levelled STEC/VTEC** (contains satellite + receiver hardware DCBs);
2. **Satellite-DCB-corrected STEC** (authentic CODE monthly `P1P2`/`P1C1` or SINEX `OSB`/`DSB` applied);
3. **Bias-calibrated causal VTEC** (satellite DCB removed + causal online receiver DCB estimated relative to CODE IONEX GIM);
4. **External gridded TEC** (CODE IONEX 1.0/1.1 GIM interpolated via Schaer et al. 1998 sun-fixed longitude rotation).

---

## 2. External Products & Provenance

| Date | Satellite Bias Products | Satellites Parsed | IONEX GIM Product | IONEX SHA-256 Prefix |
|---|---|---:|---|---|
| `2011-03-20` (DOY 079) | CODE `P1P21103.DCB.Z` + `P1C11103.DCB.Z` (`C1-P2 = P1P2 - P1C1`) | 31 GPS | `CODG0790.11I.Z` (`2 h` maps, `450 km` shell) | `0ebab70e3eaf0049` |
| `2011-03-21` (DOY 080) | CODE `P1P21103.DCB.Z` + `P1C11103.DCB.Z` | 31 GPS | `CODG0800.11I.Z` | `25d8d366be888eb2` |
| `2011-12-05` (DOY 339) | CODE `P1P21112.DCB.Z` + `P1C11112.DCB.Z` | 31 GPS | `CODG3390.11I.Z` | `7e75a006…` |
| `2024-01-26` (DOY 026) | CODE `COD0OPSFIN_2024026...OSB.BIA.gz` (`C1C-C2W`) & CAS `CAS0OPSRAP...DCB.BIA.gz` (`C1W-C2W`) | 31 GPS | `COD0OPSFIN_2024026...GIM.INX.gz` (`1 h` maps) | `6a9e8af1a38b877f` |

Missing products recorded honestly: legacy 2011 IGS/CODE archives do not distribute SINEX phase-OSB files; 2011 code DCBs are monthly averages (not daily), and 2024 coverage remains limited to DOY 026 verified coordinates.

---

## 3. Uncalibrated vs. Bias-Calibrated VTEC Against CODE IONEX GIM

### 3.1 March 2011 Equinox (`2011-03-20`, 9 B-04 Verified `IGS05` Stations)

| Station | Uncalibrated VTEC vs. GIM RMSE (TECU) | Calibrated Causal VTEC vs. GIM RMSE (TECU) | Calibrated Bias (TECU) | Converged Causal Rx DCB (TECU) | Cycle Slips (`GF / LLI+Gap / MW`) |
|---|---:|---:|---:|---:|---|
| `ABUZ` | `29.69` | **`3.25`** (`-89.1%`) | `-1.39` | `+42.39` | `8 / 12 / 2` |
| `BKFP` | `29.67` | **`3.69`** (`-87.6%`) | `-1.73` | `+41.48` | `5 / 20 / 4` |
| `CGGT` | `23.73` | **`3.38`** (`-85.8%`) | `-1.40` | `+33.74` | `12 / 13 / 3` |
| `FUTY` | `25.29` | **`3.32`** (`-86.9%`) | `-1.42` | `+37.54` | `7 / 16 / 10` |
| `MDGR` | `28.86` | **`3.56`** (`-87.7%`) | `-1.00` | `+42.45` | `4 / 19 / 11` |
| `OSGF` | `25.95` | **`3.45`** (`-86.7%`) | `-1.41` | `+37.36` | `8 / 15 / 14` |
| `RUST` | `20.01` | **`3.99`** (`-80.0%`) | `-1.49` | `+30.07` | `29 / 28 / 14` |
| `ULAG` | `22.85` | **`3.52`** (`-84.6%`) | `-1.44` | `+33.52` | `16 / 15 / 7` |
| `UNEC` | `27.19` | **`3.68`** (`-86.5%`) | `-1.37` | `+40.48` | `14 / 21 / 3` |

### 3.2 Multi-Day Consistency (`2011-03-21`, `2011-12-05`, `2024-01-26`)

| Dataset | Stations | Uncalibrated RMSE Range (TECU) | Calibrated Causal RMSE Range (TECU) | Key Physical Observation |
|---|---:|---|---|---|
| `2011-03-21` (`IGS05`) | 9 | `20.27 – 29.79` | **`3.65 – 4.56`** | `RUST` GF slips surged (`69`) under post-sunset equatorial scintillation; Rx DCBs repeatable within `0.1–2.0 TECU` of `2011-03-20`. |
| `2011-12-05` (`IGS08`) | 8 | `22.81 – 31.35` | **`3.45 – 4.72`** | `RUST` excluded (`L2/P2=0%`); high GF slip counts at southern stations (`ULAG 81`, `UNEC 69`) due to EIA crest gradients. |
| `2024-01-26` (`IGS20`) | 4 | `12.48 – 23.43` | **`4.27 – 5.10`** | Solar-cycle-25 high-TEC epoch; `PHRI00NGA` (`TRM59900.00`, `+34.4 TECU`) differs sharply from Septentrio/Trimble Rx DCBs (`-10.5` to `-16.3 TECU`). |

---

## 4. Equatorial Ionospheric Variability & Disturbance Behaviour

1. **Quiet (`06–12 UTC`) vs. Post-Sunset Disturbed (`18–24 UTC`) Differential Variability:**
   - On `2011-03-20`, interior `zero`-model differential L1 RMSE jumped **3.75×** from `0.1600 m` (`06–12 UTC`) to `0.6001 m` (`18–24 UTC`); on `2011-03-21` it jumped **4.19×** (`0.1899 m → 0.7957 m`).
   - On `2024-01-26` (high solar activity), perimeter differential L1 RMSE jumped from `0.5346 m` (`06–12 UTC`) to `0.9572 m` (`18–24 UTC`).
2. **ROTI Cadence Note:** In the `stride=4` (`120 s`) B-05 sweep, `roti_window_s=300 s` holds at most 3 points (below the 5-sample Pi et al. minimum), so ROTI remained `None` by design rather than fabricating sparse estimates. Full `30 s` causal ROTI (`10` samples / `5 min` window) is supported directly by `CausalIonoFilter(nominal_step_s=30.0)` and confirmed in Phase 6 (`roti_30s_2011-03-20.json`: `19.71%` of `ULAG` and `15.73%` of `RUST` post-sunset epochs `> 0.5 TECU/min`, peak `3.07 TECU/min`).

---

## 5. Limitations & Next Steps

- CODE IONEX GIM (`2.5° × 5.0°`, `1–2 h` cadence) is itself a global smooth model (`~2–5 TECU` formal RMS over sparse African regions), so the residual `3.25–5.10 TECU` reflects both GIM smoothing of equatorial ionization anomaly (EIA) gradients and causal receiver-DCB drift.
- Hardware code biases cancel in inter-station single/double differences ONLY for satellites; differential receiver DCBs must still be tracked causally or removed via ambiguity-fixed network IAR (**Milestone B-03**).
