# B-02 Offline Rover Positioning Benchmark — Limitations, Leakage Audit, and Experimental Bias Control

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-02 — Offline Rover Positioning Benchmark
**Date:** 2026-11-26
**Companion Report:** [b02_offline_rover_positioning_benchmark.md](file:///home/excellence/NLGCP/docs/research/b02_offline_rover_positioning_benchmark.md)
**Operational Gate:** `OPERATIONAL_APPROVED = FORBIDDEN` (unchanged)

---

## 1. Purpose

This document provides an exhaustive audit of **experimental bias, target leakage controls, RTKLIB engine subtleties, ambiguity-resolution failure mechanisms, and scientific limitations** observed during B-02 so that positioning results are never overstated beyond what the authentic evidence supports.

---

## 2. Leakage and Experimental Fairness Audit (Phase G)

| Potential Bias / Leakage Vector | Dataset B (`2024-01-26` `PHRI00NGA`) | Dataset A (`2011-03-20` `OSGF`) | Assessment & Mitigation |
|---|---|---|---|
| **Rover observations leaking into VRS synthesis or atmospheric fitting** | **ZERO LEAKAGE** (`assert_no_rover_leakage()` PASS: `PHRI00NGA` excluded from `ref_coords`, `ref_datasets`, `iono_common`, `iono_night`, and 3-ref `PRIDE ZTD`). | **ZERO LEAKAGE** (`assert_no_rover_leakage()` PASS: `OSGF` excluded from all 8-ref coords, datasets, and iono fields). | **PASS** — enforced fail-closed in code and unit-tested. |
| **Rover ground-truth coordinate leaking into VRS virtual ARP** | **ZERO LEAKAGE** — VRS placed at autonomous epoch-0 SPP GGA coordinate **`4.5641 m`** away from verified PRIDE truth. | **ZERO LEAKAGE** — VRS placed at autonomous epoch-0 SPP GGA coordinate **`0.8395 m`** away from provisional OSGoF coordinate. | **PASS** — replicates authentic NTRIP GGA workflow without truth access. |
| **Reference station reused as validation target** | `PHRI00NGA` strictly withheld; physical anchor is distinct `EKAK00NGA` (`105.553 km`). | `OSGF` strictly withheld; physical anchor is distinct `CGGT` (`216.320 km`). | **PASS**. |
| **Observation time-window & sampling parity** | Identical `2024-01-26T00:00:00Z–23:59:30Z` (`30.0 s`, `2,880/2,880` valid epochs across all 7 variants × 4 profiles). | Identical `2011-03-20T00:00:00Z–23:59:30Z` (`30.0 s`, `2,880/2,880` valid epochs across all 6 variants × 4 profiles). | **PASS** — `100.0%` paired common-epoch coverage (`n = 2,880`). |
| **Satellite visibility parity between configurations** | **ASYMMETRY OBSERVED (`-0.53` sats/epoch):** `physical_anchor_ekak` (`8.06` mean sats), `zero/tropo` VRS (`8.05`), iono VRS (`7.53`). Caused by `1,485` `iono_spatial_prediction_unavailable` exclusions when sparse 3-ref network lacked a second reference observing an edge satellite. | **NEAR-IDENTICAL PARITY (`-0.01` sats/epoch):** `physical_anchor_cggt` (`8.02` mean sats), `zero/tropo` VRS (`8.01`, `23,083` obs), iono VRS (`8.01`, `23,072` obs = `99.95%` parity). | **DOCUMENTED LIMITATION (2024)** — accounts for the `-5%` vertical RMSE trade-off in 2024 `dgps_code_diff` due to higher VDOP; eliminated in 8-ref 2011 network. |
| **Observable code-type parity (`C1/P1/P2/S1/S2`)** | `PHRI0260.24O` has `L1 L2 C1 P1 P2 S1 S2`; `EKAK0260.24O` has `C1 L1 L2 P2 P1 ...` (no `S1/S2`); `convbin` VRS RINEX 3.02 has `C1C L1C C2P L2P` (no `P1`, no `S1C/S2P`). `pos1-elmask=15` applies without SNR masking. | Both `OSGF0790.11O` and `CGGT0790.11O` have `P1 = 0%` (blank `P1` field); `convbin` VRS RINEX 3.02 has `C1C L1C S1C C2P L2P S2P`. Full `C1/P2/L1/L2` parity. | **MINOR CONFOUND (2024 only)** — `PHRI` vs `EKAK` physical baseline can pair `P1-P1` while `PHRI` vs VRS pairs `P1/C1-C1C` (sub-decimetre `P1-C1` DCB contribution on code, zero effect on `L1/L2` carrier). |
| **Antenna phase-center offset (PCO) & ARP height** | `PHRI` (`TRM59900.00 NONE`, `H=0.171 m`) vs `EKAK` (`SEPCHOKE_B3E6 SPKE`, `H=0.171 m`): `~1.4–1.7 cm` Up PCO difference (`ant1`/`ant2` ANTEX not loaded in `rnx2rtkp`, consistent with Phase 3). Identical across all variants because VRS inherits `EKAK` phase observations. | All 9 stations share identical `TRM59800.00` antennas and `DELTA H = 0.1710 m`; PCO cancels identically in double differences. | **FAIR ACROSS VARIANTS** — constant `~1.5 cm` Up offset in 2024 is orders of magnitude smaller than `0.54–2.18 m` FLOAT vertical RMSE. |
| **Coordinate frame & monument/ARP alignment** | Verified `IGS20` at observation epoch `2024-01-26T11:59:42Z`, ARP-referred, `σ < 1 mm` formal (`~5–15 mm` external). | **`PROVISIONAL_OSGOF_2011_01_01`** — undocumented ITRF realization, ARP continuity, and uncertainty. | **CRITICAL LIMITATION (2011)** — blocks `SCIENTIFICALLY_VALIDATED` accuracy claims on 2011; mitigated by reporting truth-independent centered repeatability (`-57.2%` kinematic H scatter). |
| **RTCM-to-RINEX conversion fidelity** | `2,881 / 2,881` frames (`1×1005 + 2,880×1074`), `0` CRC errors, `0` excluded cells, `2,880 / 2,880` epochs decoded, RTCM `1005` ARP exact to `0.0000 m`. | Same: `2,881 / 2,881` frames, `0` CRC errors, `0` excluded cells, `2,880 / 2,880` epochs decoded, `0.0000 m` ARP error. | **PASS** — zero conversion loss; MSM4 quantization (`±8.9 mm` PR, `±0.28 mm` phase) is negligible vs decimetre/metre FLOAT errors. |
| **RTKLIB `v2.4.2-p13` atmospheric double-correction check** | Verified directly in `/home/excellence/RTKLIB/src/rtkpos.c:883–1110`: `zdres()` unconditionally applies hydrostatic Saastamoinen at base & rover; `relpos()` ignores `ionoopt=brdc` and `tropopt=saas`. Confirmed empirically: `kinematic_brdc_saas` and `kinematic_vrs_iono_off` matched to `0.0000 m`. | Same empirical bit-for-bit identity across all 6 variants. | **VERIFIED** — explains why geometry-only VRS loses RTKLIB's automatic baseline ZHD cancellation until `UNB3m` or `network_ztd` is enabled in the VRS. |
| **Ambiguity initialization compatibility** | `rtcm_bridge.py` applies one exact integer offset `ΔN ∈ Z` per continuous `(sat, freq)` arc (`89–90` arc offsets/day), preserving fractional carrier phase and integer double-difference structure; however, underlying VRS phases remain `ANCHOR_RELATIVE_FLOAT`. | `86–89` exact integer arc offsets/day; underlying VRS phases remain `ANCHOR_RELATIVE_FLOAT`. | **CRITICAL SCIENTIFIC LIMITATION** — prevents network-resolved integer fixing (`0.0%` genuine FIX). |

---

## 3. Critical Scientific and Engineering Limitations

### L-01: Zero Genuine RTK Integer Ambiguity Resolution (`FIX = 0.0%`, Blocker B-03)
- **Observation:** Across `52` full-24-hour relative RTKLIB runs (`149,760` total epochs), **zero epochs achieved genuine centimetre RTK FIX**. The only `7` epochs flagged `Q=1` (`2` on 2011 `vrs_zero_geom_only`, `5` on 2011 `vrs_tropo_unb3m_only`) were proven to be **wrong-integer false fixes** with `1.30–2.43 m` horizontal errors (`1.30–3.89 m` 3D).
- **Consequence:** NLGCP experimental VRS currently improves **FLOAT** and **DGPS** positioning only. No centimetre-level RTK accuracy or operational RTK FIX capability can be claimed until network-level double-difference integer ambiguity resolution (IAR) and denser (`<70–100 km`) verified CORS geometry are implemented and validated.

### L-02: Provisional 2011 Coordinate Provenance (Blocker B-01)
- **Observation:** The strongest positioning gains (`+56.65%` kinematic H, `+57.06%` static H, `+45.38%` DGPS H) occurred on `2011-03-20` `OSGF`, which is inside an 8-reference convex hull — but whose station coordinates (`PROVISIONAL_OSGOF_2011_01_01`) lack documented ITRF realization, ARP continuity, and formal uncertainties.
- **Offline PPP Block:** Searching `/home/excellence/nlgcp-data` confirmed zero 2011 `SP3`, `CLK`, `ERP`, or `OSB` precise products exist locally, so PRIDE PPP-AR 3.2.8 could not be executed offline to upgrade 2011 coordinates during B-02.
- **Mitigation:** Truth-independent centered scatter (`horiz_centered_rms_m`) dropped **`-57.2%`** (`1.452 → 0.622 m`) in kinematic mode and **`-55.4%`** (`0.812 → 0.362 m`) in static mode, independently confirming real error reduction without relying on OSGoF coordinate truth. Nevertheless, 2011 results remain classified `TECHNICALLY_VALIDATED` / exploratory until B-01 closes.

### L-03: Sparse 3-Station Extrapolation on Verified 2024 Data (Blocker B-05)
- **Observation:** On verified-IGS20 `2024-01-26` (`PHRI00NGA`), only 3 reference stations (`ABFC00NGA`, `EKAK00NGA`, `MGBO00NGA`, `105–1,029 km` spacing) are admitted, placing `PHRI00NGA` **outside** the reference convex hull.
- **Consequence:** Kinematic horizontal RMSE gain (`+5.70%`, 95% CI `[-0.085, +0.240] m`) is statistically inconclusive across the full 24-hour window, and 3-reference edge-satellite dropouts (`8.06 → 7.53` mean sats) degraded `dgps_code_diff` vertical RMSE by `~5%`. Static FLOAT (`+8.23%` H, CI `[+0.047, +0.121] m`) and kinematic 3D (`+14.14%`) still improved measurably, but verified **interior-hull** evidence requires either B-01 (upgrading 2011 9-station coordinates) or acquiring denser verified 2024+ Nigerian CORS observations.

### L-04: Offline Non-Causal Atmospheric Arc Leveling (Blocker B-08)
- **Observation:** Both `common_arc_sd_l1_iono` and `nighttime_leveled_sd_l1_iono` level carrier-phase geometry-free ionospheric arcs using full-24-hour arc medians or nighttime windows (incorporating observations from later epochs in the same day).
- **Consequence:** B-02 demonstrates the **offline scientific potential** of spatially interpolated atmospheric VRS corrections, not real-time causal streaming performance. Live deployment requires replacing offline arc leveling with a causal epoch-by-epoch Kalman filter (no future-epoch look-ahead) and benchmarking real-time correction latency.

### L-05: Single-Day Seasonal Scope, Equatorial Scintillation, and Single-Constellation Scope
- **Observation:** B-02 evaluated one dry-season Harmattan day (`2024-01-26`) and one equinox day (`2011-03-20`). Post-sunset equatorial irregularities (`18–24 UTC`) still produced `1.03–1.33 m` kinematic horizontal RMSE even with the best atmospheric VRS.
- **Constellations & Engines:** All VRS streams are **GPS-only** (`1005 + 1074`; GLONASS FCN transport in `1084` remains open under **B-07**), evaluated exclusively with **RTKLIB `v2.4.2-p13`** via `convbin` RINEX conversion (no second positioning engine, no non-RTKLIB MSM4 decoder **B-06**, and no commercial GNSS rover receiver test **B-10**).

### L-06: Preserved Operational Safety Controls
No operational approval or production deployment readiness is established by B-02:
- `OPERATIONAL_APPROVED = FORBIDDEN`
- Operational Phase 6 default: `BEST = ZERO`
- Operational Phase 7 default: `VRS_GEOMETRY_ONLY`
- `NLGCP_VRS_EXP` remains isolated loopback-only research validation; `NLGCP_TEST` remains strictly synthetic-only; non-loopback security controls (**B-09**) and field validation (**B-10**) remain blocked.
