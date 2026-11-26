# Phase 6 & 7 Remaining Blockers and Next Steps

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Scope:** Gap Register & Prioritized Roadmap Following the Atmospheric Modelling & VRS Generation Sprint
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Operational Readiness Verdict:** `NOT_APPROVED` / `BLOCKED` (local experimental research pipeline `TECHNICALLY_VALIDATED` only)

---

## 1. What Changed vs. What Remains Blocked

This sprint resolved several major Phase 6 and Phase 7 engineering and empirical research gaps:
- Content-level auditing of all 3,018 2011 NIGNET files (catching silent Dec 2011 `RUST` L2/P2 outages and GPS `P1=0%`) and selection of 6 nine-station interior-hull windows.
- Physically grounded Phase 6 ionospheric estimation (MW+GF+LLI cycle-slip detection, phase-leveled STEC/VTEC with SLM IPPs, common-pair-arc & nighttime-leveled differential L1 ionosphere), UNB3m climatology benchmarked against independent PRIDE PPP-AR 3.2.8 ZTD, and interior-vs-perimeter stratified LOOCV demonstrating `+27.7%` to `+29.4%` interior RMSE reduction while confirming `zero` still dominates perimeter extrapolation.
- Observation-based experimental VRS synthesis (`C1/P2/L1/L2` with separated troposphere & ionosphere and opposite code/phase dispersion signs), reducing held-out target residuals across all observables (`-23.0%` C1, `-21.8%` P2, `-21.8%` GF TD on 2011 interior `OSGF`; `-9.4%` C1, `-11.1%` GF TD on 2024 verified `PHRI00NGA`).
- End-to-end integration from experimental VRS → Phase 11 RTCM `1005/1074` (with exact integer-cycle arc alignment) → isolated Phase 12 loopback mountpoint `NLGCP_VRS_EXP` → verified decoding by RTKLIB `convbin`, RTKLIB native `input_rtcm3()`, and **non-RTKLIB ESA/gAGE-UPC gLAB v6.0.0** (`1005` + CRC-24Q).

Despite this progress, **operational VRS, operational NTRIP distribution, and centimetre RTK positioning claims remain strictly BLOCKED** by the explicit scientific, data, decoder, positioning, security, and field-validation prerequisites below.

---

## 2. Explicit Remaining Blockers

| ID | Blocker Category | Severity | Concrete Technical Description | Required Resolution Evidence |
|---|---|---|---|---|
| **B-01** | **2011 Coordinate Provenance** | **CRITICAL (Scientific)** | All 11 OSGoF 2011-01-01 station coordinates lack documented ITRF realization, ARP continuity, and formal uncertainties (`PROVISIONAL_OSGOF_2011_01_01`). | Re-estimate 2011 NIGNET station coordinates via PRIDE PPP-AR using verified IGS final/repro3 precise orbits & clocks (IGS20/ITRF2020), cross-checked against IGS/OSGoF monument records. |
| **B-02** | **No Downstream Rover RTK Positioning Validation** | **CRITICAL (Scientific)** | Experiment 5 validated held-out observation residuals (`C1/P2/L1/L2/GF`), NOT rover positioning (`rnx2rtkp` kinematic/static ENU RMSE, ambiguity FIX rate, or TTFF) using the generated VRS RTCM `1005+1074` stream. | Run controlled offline `rnx2rtkp` rover positioning comparing `Rover + Physical Anchor` vs. `Rover + Geometry-Only VRS` vs. `Rover + Atmospheric VRS` (after B-01 and B-03) and record ENU RMSE, FIX rate, and TTFF without fabrication. |
| **B-03** | **No Network Integer Ambiguity Resolution (IAR)** | **CRITICAL (Scientific)** | Experimental VRS carrier phases carry `ANCHOR_RELATIVE_FLOAT` ambiguities. Without network-level double-difference integer ambiguity fixing across reference baselines (MAC / FKP / VRS-IAR), residual float ambiguity biases prevent centimetre RTK FIX across 200–700 km baselines. | Implement and validate offline network baseline ambiguity resolution (wide-lane Melbourne-Wubbena + narrow-lane/iono-free LAMBDA) on verified multi-station networks with realistic sub-100 km Nigerian CORS spacing. |
| **B-04** | **External DCB & Regional IONEX Absence** | **HIGH (Scientific)** | Local storage contains no CODE/IGS DCB files (`C1-P1`, `P1-P2`) or regional GIM/IONEX products (`/home/excellence/nlgcp-data/external-products/igs` is empty). Raw STEC/VTEC therefore retains hardware biases (`bias_corrected_stec_tecu = None`). | Acquire immutable, checksummed IGS/CODE DCB and IONEX products (with documented provenance) to calibrate absolute STEC/VTEC and independently cross-validate nighttime-leveled receiver DCB estimates. |
| **B-05** | **Sparse Nigerian CORS Geometry & Coastal Tropospheric Gradient** | **HIGH (Geodetic)** | 2024 verified archive has only 4 stations (105–1,029 km, zero interior stations); even 2011 9-station baselines average 188–716 km. January Harmattan creates a `12.6 cm` coastal-vs-inland ZWD contrast (`EKAK 0.229 m` vs. `MGBO 0.103 m`) that static UNB3m climatology cannot capture. | Acquire denser verified multi-station Nigerian CORS observations (`< 70–100 km` inter-station spacing) and integrate real-time/NWP (ERA5/ECMWF) or PPP-estimated ZWD fields. |
| **B-06** | **No Non-RTKLIB MSM4 Cross-Decoder or Commercial Rover Test** | **HIGH (Protocol)** | ESA/gAGE-UPC gLAB v6.0.0 validated CRC-24Q across all 31 frames and RTCM `1005` ECEF to `0.0000 m`, but does not support MSM4 (`1074`/`1084`). Non-RTKLIB MSM4 decoding remains `NOT_SUPPORTED_BY_GLAB_V6`. | Validate emitted RTCM `1005/1074/1084` streams against a second independent MSM4 decoder (BKG BNC, `pyrtcm`, or commercial dual-frequency receiver firmware logs). |
| **B-07** | **GLONASS FCN & Multi-Constellation Extension** | **MEDIUM (Protocol/GNSS)** | RINEX 2.11 2011 headers omit GLONASS FDMA frequency channel numbers (FCNs), and Phase 11 RTCM `1084` does not transport FCNs; experimental VRS is currently GPS-only (`1005 + 1074`). | Parse GLONASS broadcast navigation (`brdc*.11g.Z` / RINEX 3 mixed nav) for verified FCN tables, extend experimental VRS to GPS+GLONASS (`1074 + 1084`) and Galileo (`1094`) when multi-GNSS RINEX 3 observations are admitted. |
| **B-08** | **Live CORS Ingestion & Real-Time Atmospheric Latency** | **HIGH (Operations)** | Phase 10 live CORS ingestion remains `BLOCKED` (zero authorized live NTRIP CORS endpoints). Historical offline runs do not measure real-time sliding-window filter latency, ephemeris rollover handling, or missing-station failover. | Acquire authorized live Nigerian CORS NTRIP feed(s), implement streaming/causal Kalman ionospheric & ZWD estimators (no future-epoch arc medians!), and benchmark end-to-end correction age (`< 1–2 s`). |
| **B-09** | **Non-Loopback Security & Production Caster Controls** | **CRITICAL (Security)** | Phase 12 caster remains strictly loopback-only (`127.0.0.1`). All 14 Day 7 security findings (TLS termination, RBAC/entitlements, credential hashing/vault, rate limiting, NMEA GGA routing bounds, audit trails) remain unresolved prerequisites before any non-loopback deployment. | Complete Phase 15 security hardening and Day 7 security remediation roadmap (`docs/sprints/14-day-beta-sprint/13-day7-backend-security-review.md`). |
| **B-10** | **Field Validation & Hardware Inventory** | **CRITICAL (Field)** | Phase 16 hardware inventory remains `UNKNOWN`; zero controlled rover field tests have been conducted. | Execute Phase 16 controlled hardware-in-loop and geodetic control-point field validation after B-01 through B-09 are resolved. |

---

## 3. Recommended Next Engineering & Scientific Sequence

1. **Immediate (Offline Scientific — Highest ROI):**
   - **Step 1 (B-01):** Run PRIDE PPP-AR 3.2.8 on the 9 stations of `2011-03-20..21` and `2011-12-05..08` (once matching 2011 IGS precise orbits/clocks are acquired) to upgrade 2011 coordinates from `PROVISIONAL_OSGOF_2011_01_01` to `VERIFIED_IGS20` and generate independent 2011 ZTD truth across all 9 stations!
   - **Step 2 (B-02):** Feed the `convbin`-decoded experimental VRS RINEX (or direct RTCM stream) + withheld real rover RINEX into `rnx2rtkp` (static & kinematic baselines) to measure true positioning ENU RMSE and compare `Anchor-Only` vs. `Geometry-Only VRS` vs. `Atmospheric VRS` quantitatively.
   - **Step 3 (B-04 & B-06):** Acquire checksummed CODE/IGS DCB + IONEX files for `2011-03-20` and `2024-01-26`, and install a second independent MSM4 decoder (`pyrtcm` or BKG `bnc`) to close the non-RTKLIB MSM4 verification gap.
2. **Near-Term (Causal Real-Time Filter & Network IAR):**
   - Replace batch arc-median ionospheric leveling with a causal epoch-by-epoch filter suitable for live streaming, and prototype double-difference baseline ambiguity resolution (`B-03`) once shorter (`< 100 km`) verified multi-station Nigerian baselines are available.
3. **Pre-Beta / Operational Track (Separate Governance Gate):**
   - Keep `OPERATIONAL_APPROVED = FORBIDDEN`, `NLGCP_TEST` synthetic-only, and `NLGCP_VRS_EXP` loopback research-only until Phase 15 security controls (`B-09`), live CORS admission (`B-08`), and Phase 16 field validation (`B-10`) pass explicit review.
