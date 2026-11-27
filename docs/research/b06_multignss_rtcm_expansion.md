# B-06 Multi-GNSS Signal Audit & RTCM 3.x Expansion Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-06 — Multi-GNSS & RTCM Expansion  
**Date:** 2026-11-27  
**Status Classification:**  
- **Authentic Multi-GNSS Audit:** `OBSERVED` (`AUTHENTIC_OBSERVATION` on 2011 & 2024 Nigerian NIGNET RINEX + BKG/IGS BRDC archives)  
- **RTCM Encoders (`1006`, `1007`, `1008`, `1020`, `1033`, `1094`, `1230`):** `IMPLEMENTED` | `UNIT_TESTED` | `SYNTHETICALLY_VALIDATED` (`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`)  
- **BeiDou (`1124`):** `DECLARED` only (`0` authentic Nigerian BeiDou observations in inspected archives; not fabricated)  
- **Operational Approval:** `NOT_APPROVED` (`OPERATIONAL_APPROVED = FORBIDDEN`)

---

## 1. Authentic Nigerian Multi-GNSS & Equipment Audit

Content-level inspection of the verified 2011 (`DOY 079`) and 2024 (`DOY 026`) Nigerian NIGNET RINEX 2.11 observation files and broadcast navigation products reveals heterogeneous constellation coverage and uniform non-zero antenna heights (`DELTA H = 0.1710 m`):

| Dataset / Station | Receiver & Firmware | Antenna & Radome | `DELTA H/E/N` (m) | Observed Systems (Epoch-Sat Counts) | Broadcast Nav Available |
|---|---|---|---|---|---|
| **2011 DOY 079** (`ABUZ`, `BKFP`, `CGGT`, `FUTY`, `MDGR`, `OSGF`, `RUST`, `ULAG`, `UNEC`) | `TRIMBLE NETR8` (v4.19/4.22) & `TRIMBLE NETR9` (v4.22) | `TRM59800.00` (`NONE`) | `0.1710 / 0.0 / 0.0` | **GPS (`G`: 20,742–29,644)** + **GLONASS (`R`: 4,916–13,818)**; `0` Galileo, `0` BeiDou | `brdc*0.11n.Z` (`G`) + `brdc*0.11g.Z` (`R` with FCNs) |
| **2024 DOY 026 `ABFC00NGA`** | `SEPT POLARX5S 5.5.0` | `TRM59800.00 NONE` | `0.1710 / 0.0 / 0.0` | **`G`: 17,944**, **`E`: 8,909**, **`R`: 2,525**, `S`: 5,182 (`0` BeiDou) | `BRDC00IGS_R_20240260000_01D_MN.rnx` (`G`: 440, `R`: 1,222, `E`: 11,165, `C`: 1,080, `J`: 100, `I`: 145, `S`: 11,746) |
| **2024 DOY 026 `EKAK00NGA`** | `SEPT POLARX5 5.5.0` | `SEPCHOKE_B3E6 SPKE` | `0.1710 / 0.0 / 0.0` | **`G`: 20,366**, **`E`: 14,178**, `S`: 16 (`0` GLONASS, `0` BeiDou) | Same 2024 merged BRDC |
| **2024 DOY 026 `MGBO00NGA`** | `SEPT POLARX5 5.5.0` | `SEPCHOKE_B3E6 SPKE` | `0.1710 / 0.0 / 0.0` | **`G`: 16,882**, **`E`: 12,549**, `S`: 5,129 (`0` GLONASS, `0` BeiDou) | Same 2024 merged BRDC |
| **2024 DOY 026 `PHRI00NGA`** | `TRIMBLE NETR9 5.03` | `TRM59900.00 NONE` | `0.1710 / 0.0 / 0.0` | **`G`: 21,389**, **`R`: 13,171** (`0` Galileo, `0` BeiDou) | Same 2024 merged BRDC |

### Key Scientific Implications
1. **GPS (`G`)** is universal across all stations (`2011` & `2024`).
2. **GLONASS (`R`)** is present on all 9 stations in 2011 (with authentic `brdc*0.11g.Z` FCN ephemerides) and on the `470.870 km` `ABFC00NGA–PHRI00NGA` baseline in 2024, but absent on `EKAK00NGA`/`MGBO00NGA`.
3. **Galileo (`E`)** is authentically present across **3 of 4 stations in 2024** (`ABFC00NGA`, `EKAK00NGA`, `MGBO00NGA` with E1/E5a/E5b/E5ab/E6 observables + 11,165 authentic Galileo BRDC records), motivating **RTCM `1094` (Galileo MSM4)**, while `PHRI00NGA` (Trimble NetR9 v5.03) has `0` Galileo observations.
4. **BeiDou (`C`)** has **`0` observations** in all inspected 2011 & 2024 RINEX 2.11 files despite 1,080 records in 2024 merged BRDC; therefore **`MSM4_BEIDOU_1124` remains strictly `DECLARED`** (no encoder or fabricated observations).
5. **Non-Zero Antenna Heights & Mixed Hardware:** Every inspected Nigerian station has `DELTA H = 0.1710 m` and mixed Trimble/Septentrio antennas & receivers, directly motivating **RTCM `1006`, `1007`, `1008`, and `1033`**.

---

## 2. Implemented RTCM 3.x Expansion (`research/rtcm_generation`)

Preserving existing Phase 11 `1005`, `1074`, `1084`, and `4095` encoders untouched:

| RTCM Msg | Family ID | Purpose & Nigerian Motivation | Registry Status | Independent Verification |
|---|---|---|---|---|
| **`1006`** | `REFERENCE_STATION_1006` | ARP ECEF + 16-bit `0.0001 m` antenna height (`0.1710 m`) | `SYNTHETICALLY_VALIDATED` | RTKLIB `convbin` + native `input_rtcm3` (`hgt_m=0.1710`) + **ESA gLAB v6.0.0 `readMSG1006`** + B-07 clean-room spec decoder |
| **`1007`** | `ANTENNA_DESCRIPTOR_1007` | Antenna descriptor (`TRM59800.00     NONE`) + setup ID | `SYNTHETICALLY_VALIDATED` | RTKLIB native `input_rtcm3` + B-07 spec decoder |
| **`1008`** | `ANTENNA_DESCRIPTOR_SERIAL_1008` | Antenna descriptor + setup ID + serial number | `SYNTHETICALLY_VALIDATED` | RTKLIB native `input_rtcm3` + ESA gLAB v6.0.0 `readMSG1008` (descriptor/setup) + B-07 spec decoder |
| **`1033`** | `RECEIVER_ANTENNA_DESCRIPTOR_1033` | Receiver type/firmware/serial + antenna descriptor/serial (`SEPT POLARX5 5.5.0` / `SEPCHOKE_B3E6 SPKE`) | `SYNTHETICALLY_VALIDATED` | RTKLIB native `input_rtcm3` (`rectype`, `recver`, `antdes`) + B-07 spec decoder |
| **`1020`** | `GLONASS_EPHEMERIS_1020` | 360-bit GLONASS ephemeris transporting **FCN (`-7..+6`)** in sign-magnitude RTCM layout | `SYNTHETICALLY_VALIDATED` | **Resolves Day 3 standalone `1084` GLONASS carrier-phase FCN blocker:** streaming `1020 + 1084` recovers exact `L1C/L2C` cycles (`±0.28 mm`) in unmodified RTKLIB `convbin` & `input_rtcm3` with zero `--glo-fcn` injection! |
| **`1230`** | `GLONASS_CODE_PHASE_BIAS_1230` | GLONASS FDMA L1/L2 C/A & P code-phase biases (`0.02 m` LSB) | `SYNTHETICALLY_VALIDATED` | CRC-verified by RTKLIB (`nmsg3_1230=1`, RTKLIB v2.4.2-p13 explicitly logs `1230: not supported message`); semantically verified by B-07 clean-room spec decoder |
| **`1094`** | `MSM4_GALILEO_1094` | Galileo MSM4 (all 18 RTKLIB 1-based Galileo signal IDs, PRN `1..36`) | `SYNTHETICALLY_VALIDATED` | RTKLIB `convbin` (`E04` `C1C/L1C/C5Q/L5Q`) + native `input_rtcm3` + B-07 spec decoder |
| **`1124`** | `MSM4_BEIDOU_1124` | BeiDou MSM4 placeholder | **`DECLARED`** (`encoder_key=None`) | Honestly deferred pending authentic Nigerian BeiDou observations |

---

## 3. Defects Caught During B-06 Verification

1. **Physical Luni-Solar Acceleration Bounds Check (`GlonassEphemeris1020`):** Initial synthetic fixture acceleration (`1e-4 m/s²`) exceeded the 5-bit sign-magnitude RTCM 1020 domain (`±15 × 2^-30 km/s² ≈ ±1.4×10^-5 m/s²`). Caught immediately by `BitWriter.write_sign_magnitude()` and hardened in `GlonassEphemeris1020.validate()`.
2. **Station-ID Stream Consistency (`test_staid`):** Unmodified RTKLIB `input_rtcm3()` enforces single-station consistency across `1006` and `1033` in the same stream (`staid=2011`), confirming fail-closed station-ID validation across multi-message streams.

---

## 4. Limitations & Reproducibility

- All B-06 encoders remain **`SYNTHETICALLY_VALIDATED`** (zero `REAL_INPUT_VALIDATED` or `OPERATIONALLY_APPROVED` entries); multi-GNSS GLONASS/Galileo VRS synthesis and positioning remain documented research follow-ons.
- Reproducible verification:
  ```bash
  RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest research/rtcm_generation/tests -v
  ```
