# B-07 Independent RTCM Protocol & Multi-Decoder Validation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-07 — Independent Protocol & Receiver Validation  
**Date:** 2026-11-27  
**Status Classification:**  
- **Protocol Cross-Decoding (3 Independent Decoder Families):** `IMPLEMENTED` | `UNIT_TESTED` | `INDEPENDENTLY_VALIDATED` (RTKLIB v2.4.2-p13 + ESA/gAGE-UPC gLAB v6.0.0 + NLGCP Clean-Room RTCM 10403.3 Spec Decoder)  
- **Third-Party Python/C Decoders (`pyrtcm`, BKG BNC):** `NOT_INSTALLED` (honestly documented as optional external dependencies; not silently installed or fabricated)  
- **Physical Commercial GNSS Receiver Validation:** **`BLOCKED_HARDWARE_ACCESS`** (no Leica, Trimble, Topcon, Septentrio, Emlid, or u-blox rover hardware attached; zero hardware interoperability claimed)  
- **Operational Approval:** `NOT_APPROVED` (`OPERATIONAL_APPROVED = FORBIDDEN`)

---

## 1. Independent Decoder Matrix

| Decoder Family | Implementation / Provenance | Code Shared with Phase 11 Encoders / Phase 9 CRC? | Messages Verified Semantically | Limitations / Upstream Findings |
|---|---|---|---|---|
| **1. RTKLIB `v2.4.2-p13` (`convbin` + native `input_rtcm3`)** | Unmodified C source (`71db0ffa…`), `convbin` (`b575f81e…`), read-only adapter [rtklib_rtcm_decode.c](file:///home/excellence/NLGCP/research/rtcm_generation/native/rtklib_rtcm_decode.c) | **Zero** | `1005`, `1006` (`hgt_m=0.1710`), `1007`, `1008`, `1020` (`geph_fcns`), `1033` (`rectype`, `recver`, `antdes`), `1074`, `1084` (full `L1C/L2C` carrier phase via `1020` FCN!), `1094` (Galileo MSM4) | `1230` explicitly unsupported in RTKLIB v2.4.2-p13 (`nmsg3_1230=1`, CRC-verified only); RTKLIB was Day 2 layout reference |
| **2. ESA / gAGE-UPC `gLAB v6.0.0`** | Unmodified C source (`/opt/gLAB/source/core/input.c`), read-only adapter [glab_rtcm1005_decode.c](file:///home/excellence/NLGCP/research/rtcm_generation/native/glab_rtcm1005_decode.c) | **Zero** (completely non-RTKLIB third-party C codebase!) | CRC-24Q across all frames + `1005` ARP + **`1006` ARP & antenna height (`0.1710 m`)** + `1008` descriptor/setup ID | MSM4 (`1074`/`1084`/`1094`) unsupported by gLAB v6.0.0 (`CRC-24Q` verified only); **upstream gLAB v6.0.0 bug caught in `input.c:864`** (`readMSG1008` reads `msg[9+i]` instead of `msg[9+n+i]` for `serialNum` when `n>0`) |
| **3. NLGCP Clean-Room RTCM 10403.3 Spec Decoder** | Standalone Python parser [spec_decoder.py](file:///home/excellence/NLGCP/research/rtcm_generation/src/nlgcp_rtcm_generation/spec_decoder.py) with independent bit-by-bit CRC-24Q (`0x1864CFB`) | **Zero** (no shared `BitWriter`, `messages.py`, or Phase 9 lookup tables) | Full semantic decoding of `1005`, `1006`, `1007`, `1008`, `1020`, `1033`, **`1230`**, `1074`, `1084`, and `1094` | In-repo clean-room implementation; does not replace third-party commercial receiver firmware |
| **4. `pyrtcm` (BSD-3) / BKG BNC** | External third-party non-RTKLIB MSM4 decoders | N/A | **NOT INSTALLED** in offline `.venv` / host environment | Evaluated in B-07: `pyrtcm` (semuconsulting, BSD-3) supports `1005/1006/1007/1008/1020/1033/1074/1084/1094/1230` and is the recommended external non-RTKLIB MSM4 dependency for a future CI cross-check |
| **5. Commercial GNSS Receivers** | Physical hardware (Trimble, Leica, Septentrio, u-blox, Emlid, CHCNAV) | N/A | **`BLOCKED_HARDWARE_ACCESS`** | Deferred to Phase 16 field validation once authorized hardware & live corrections are available |

---

## 2. Cross-Decoding Verification Results (`15/15` Native + Spec Tests PASS)

### 2.1 Synthetic B-06 Multi-Message Stream (`1005/1006/1007/1008/1020/1033/1074/1084/1094/1230`)
- **RTKLIB `convbin` + native `input_rtcm3()`:** `0` CRC errors, `0` decode errors; `1006` ARP & `0.1710 m` height exact to `0.0001 m`; `1033` `SEPT POLARX5` / `SEPCHOKE_B3E6   SPKE` exact; **`1020 (fcn=-4) + 1084` recovered GLONASS `L1C = 109392141.512 cyc` and `L2C = 85082797.483 cyc` (`±0.28 mm`) natively without `--glo-fcn`**; `1094` Galileo `E04` `C1C`/`C5Q` exact within half-LSB.
- **Unmodified ESA gLAB v6.0.0:** `3/3` frames CRC-24Q OK (`1006`, `1008`, `1094`); `1006` decoded exact (`ecef_x_m = 6246471.2763`, `antenna_height_m = 0.1710`); `1008` decoded `antenna_descriptor = "TRM59800.00     NONE"`.
- **Clean-Room Spec Decoder (`spec_decoder.py`):** `8/8` messages (`1005`, `1006`, `1007`, `1008`, `1033`, `1020`, `1230`, `1094`) decoded with `0` CRC errors and exact field recovery (`1230` biases `L1_CA=+0.42 m`, `L2_CA=-0.18 m`, `L2_P=+0.06 m`); single-bit mutation caught independently by bit-by-bit CRC-24Q (`CRC24Q_FAILED`).

### 2.2 Preserved Authentic Phase 7 Experimental VRS RTCM Streams (Read-Only Cross-Decode)
Both preserved authentic experimental VRS streams were cross-decoded read-only by `spec_decoder.py` (confirming prior RTKLIB + gLAB results with full MSM4 `1074` independent parsing):

| Preserved Stream | Size (B) | Frames | CRC-24Q OK | Decoded | Message Histogram | Decoded `1005` ARP (m) |
|---|---:|---:|---:|---:|---|---|
| `vrs_2011_03_20_osgf_exp.rtcm3` | 4,045 | 31 | **31 / 31** | **31 / 31** | `1005`: 1, `1074`: 30 | `(6246471.2000, 820848.7400, 994267.9300)` |
| `vrs_2024_01_26_phri_exp.rtcm3` | 3,914 | 31 | **31 / 31** | **31 / 31** | `1005`: 1, `1074`: 30 | `(6308877.9839, 772269.1026, 530087.6060)` |

---

## 3. Verification & Reproducibility

```bash
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest \
  research/rtcm_generation/tests/test_b06_b07_multignss_and_decoders.py \
  research/rtcm_generation/tests/test_independent_decoder.py -v
```
