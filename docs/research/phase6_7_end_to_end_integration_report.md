# Phase 6 & 7 End-to-End Integration Report (VRS → RTCM 1005/1074 → Isolated NTRIP → Independent Decoders)

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Scope:** Experiments 6 & 7 — Phase 7 Experimental VRS → Phase 11 RTCM 3.x → Phase 12 Local Loopback NTRIP (`NLGCP_VRS_EXP`) → Multi-Decoder Validation
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Validation Status:** `TECHNICALLY_VALIDATED` (loopback research transport & multi-decoder conformance verified; operational NTRIP/VRS service remains `BLOCKED` / `NOT_APPROVED`)

---

## 1. End-to-End Pipeline Architecture

The experimental pipeline connects four repository layers without duplicating RTCM encoders, CRC logic, or NTRIP framing, and without disturbing the Phase 12 synthetic mountpoint (`NLGCP_TEST`) or operational approval gates:

```text
Authentic Historical RINEX (2011-03-20 / 2024-01-26)
  │
  ▼  Phase 6: ionosphere_estimation.py + troposphere_estimation.py + spatial_estimation.py
Reference-Only Ionospheric & Tropospheric Correction Fields (zero held-out target leakage)
  │
  ▼  Phase 7: experimental_vrs.py (12 fail-closed quality gates; operational_approved=False)
ExperimentalVrsResult (C1, P2, L1, L2; anchor-relative float; RESEARCH_VALIDATION)
  │
  ▼  Phase 7 -> Phase 11 Bridge: rtcm_bridge.py (reuses ReferenceStation1005 + Msm4Message + Phase 9 encode_payload_frame)
ExperimentalVrsRtcmBundle (1 x RTCM 1005 [ref_sta_ind=1] + 30 x RTCM 1074 GPS MSM4 [1C+2P]; exact integer arc alignment)
  │
  ▼  Phase 12 Isolated Mountpoint: LocalNtripCaster on 127.0.0.1 -> /NLGCP_VRS_EXP (experimental_vrs_only=True)
LocalNtripClient (NTRIP v2.0 + Basic auth + StreamingFramer)
  │
  ├──▶ Unmodified RTKLIB v2.4.2-p13 convbin (SHA-256 b575f81e…)  -> RINEX 3.02 + 1005 ARP + 1074 C1C/L1C/C2P/L2P
  ├──▶ Unmodified RTKLIB v2.4.2-p13 native input_rtcm3()          -> Per-frame CRC + 1005 ECEF + 1074 obs cells
  └──▶ Unmodified ESA/gAGE-UPC gLAB v6.0.0 input.c (NON-RTKLIB!)  -> Independent CRC-24Q (all frames) + 1005 ECEF
```

---

## 2. Strict Isolation Between Synthetic, Experimental Research, and Operational Channels

| Mountpoint / Policy | `synthetic_only` | `experimental_vrs_only` | Accepted `OutputClassification` | Rejected Classifications | Operational Status |
|---|---|---|---|---|---|
| `NLGCP_TEST` (existing Phase 12 default) | `True` | `False` | `SYNTHETIC_TEST_ONLY` only | `RESEARCH_VALIDATION`, `OPERATIONAL_APPROVED` | **FORBIDDEN** |
| `NLGCP_VRS_EXP` (new isolated research mountpoint) | `False` | `True` | `RESEARCH_VALIDATION` only (`mode="VRS_EXPERIMENTAL"`) | `SYNTHETIC_TEST_ONLY`, `OPERATIONAL_APPROVED` | **FORBIDDEN** |
| Any operational mountpoint (`synthetic_only=False, experimental_vrs_only=False`) | `False` | `False` | None — raises `MountpointError` at validation | All | **FORBIDDEN** |

Every `NLGCP_VRS_EXP` source-table `STR` record is enforced by `MountpointDefinition.validate()` to carry both `EXPERIMENTAL` and `NOT OPERATIONAL` in its label (`EXPERIMENTAL VRS RESEARCH STREAM — NOT OPERATIONAL — NOT VALID FOR NAVIGATION OR OPERATIONAL POSITIONING.`). Cross-publishing experimental VRS frames to `NLGCP_TEST` or operational frames to `NLGCP_VRS_EXP` raises `PublicationError` fail-closed.

---

## 3. Experiment 6 Results — Multi-Decoder RTCM 1005 + 1074 Validation

Two full 31-frame experimental VRS streams (`1 × RTCM 1005 + 30 × RTCM 1074`, representing 60 minutes of 120-second strided authentic dual-frequency GPS observations) were generated and persisted under `/home/excellence/nlgcp-data/processed/vrs/sprint-phase67/`:

| Metric | 2011-03-20 Interior `OSGF` (`idw2_unb3m`) | 2024-01-26 Verified `PHRI00NGA` (`idw2_pride_ztd`) |
|---|---|---|
| Binary File | `vrs_2011_03_20_osgf_exp.rtcm3` | `vrs_2024_01_26_phri_exp.rtcm3` |
| Stream Size / Frames | `4,045 B` / `31` frames (`1×1005`, `30×1074`) | `3,914 B` / `31` frames (`1×1005`, `30×1074`) |
| Stream SHA-256 | `e4f492655df9967080f372f4435193fc9f007c11b48a600e2f34965a3bb18246` | `d9eb20c31b3e740c5d5abd77e7c500cdb0050b709d23232ec556ed78b90cfba1` |
| Integer Arc Offsets Applied (`ΔN ∈ ℤ`) | `16` continuous satellite/signal arcs (`0` excluded cells) | `16` continuous satellite/signal arcs (`0` excluded cells) |
| **RTKLIB `convbin`** (`b575f81e…`) | **PASS** — `rc=0`, `station_id=2011`, ECEF err `0.000000 m`, `30/30` epochs, `220` GPS sat-epochs (`C1C,L1C,S1C,C2P,L2P,S2P`) | **PASS** — `rc=0`, `station_id=2024`, ECEF err `0.000054 m` (0.05 mm), `30/30` epochs, `211` GPS sat-epochs (`C1C,L1C,C2P,L2P`) |
| **RTKLIB Native `input_rtcm3()`** (`f21f89b5…`) | **PASS** — `31` events, `0` CRC errors, `0` decode errors, `1×1005` (`0.000000 m`), `30×1074`, `440` decoded signal cells | **PASS** — `31` events, `0` CRC errors, `0` decode errors, `1×1005` (`0.000054 m`), `30×1074`, `422` decoded signal cells |
| **Non-RTKLIB ESA/gAGE-UPC gLAB v6.0.0** (`56220413…`) | **PASS (1005 + CRC-24Q)** — `31/31` CRC-24Q PASS (`0` fails), `1005` decoded `staid=2011`, `ref_sta_ind=1`, ECEF err `0.000000 m`; MSM4 `1074` honestly marked `NOT_SUPPORTED_BY_GLAB_V6` | **PASS (1005 + CRC-24Q)** — `31/31` CRC-24Q PASS (`0` fails), `1005` decoded `staid=2024`, `ref_sta_ind=1`, ECEF err `0.000054 m`; MSM4 `1074` honestly marked `NOT_SUPPORTED_BY_GLAB_V6` |

### Significance of Non-RTKLIB Cross-Decoder Breakthrough

During Days 1–7, no non-RTKLIB decoder had been verified against NLGCP's RTCM output. By auditing `/opt/gLAB/source/core/input.c` (unmodified ESA/gAGE-UPC gLAB v6.0.0) and building the read-only native C harness `research/rtcm_generation/native/glab_rtcm1005_decode.c`, NLGCP now has **genuine second-implementation (non-RTKLIB) C cross-validation** for:
- RTCM 3.x framing and **CRC-24Q** across all emitted frames (`1005` and `1074`); and
- **RTCM 1005** station ID, constellation indicators, non-physical VRS flag (`reference_station_indicator=1`), and 38-bit 0.1 mm ECEF coordinates (`0.0000–0.000054 m` agreement).

Because gLAB v6.0.0 does not implement RTCM MSM4 (`1074`/`1084`), non-RTKLIB cross-decoding of MSM4 observation fields remains honestly reported as `NOT_SUPPORTED_BY_GLAB_V6` (awaiting BNC, `pyrtcm`, or commercial receiver testing).

---

## 4. Experiment 7 Results — Local Loopback NTRIP Distribution (`/NLGCP_VRS_EXP`)

| Verification Check | 2011-03-20 `OSGF` Stream | 2024-01-26 `PHRI00NGA` Stream |
|---|---|---|
| Bind Address / Exposure | `127.0.0.1` ephemeral port (loopback only) | `127.0.0.1` ephemeral port (loopback only) |
| Source Table (`GET /`) HTTP Status | `200 OK` | `200 OK` |
| Source Table Advertises `NLGCP_VRS_EXP` + `NOT OPERATIONAL` | `True` / `True` | `True` / `True` |
| Source Table Preserves `NLGCP_TEST` Intact | `True` | `True` |
| Frames Published / Received Valid / Invalid | `31` / `31` / `0` | `31` / `31` / `0` |
| End-to-End Byte-Exact SHA-256 Match | **`True`** (`4,045 / 4,045` B) | **`True`** (`3,914 / 3,914` B) |
| Over-the-Wire Received Stream → RTKLIB `convbin` | `30/30` epochs, ECEF err `0.000000 m` | `30/30` epochs, ECEF err `0.000054 m` |
| Over-the-Wire Received Stream → RTKLIB Native | `31/31` decoded events | `31/31` decoded events |
| Over-the-Wire Received Stream → gLAB v6.0.0 | `31/31` CRC OK, `1×1005` decoded | `31/31` CRC OK, `1×1005` decoded |
| Caster Diagnostics (`crc_failures` / `rejected_frames` / `queue_overflow_drops`) | `0` / `0` / `0` | `0` / `0` / `0` |
| Clean Client Disconnect & Caster Shutdown | Verified | Verified |

---

## 5. Operational Boundary Statement

Transport, CRC, NTRIP framing, and multi-decoder verification over loopback (`127.0.0.1`) proves **technical end-to-end integration** for experimental research only. It does **not** establish public-network NTRIP security (TLS, RBAC, rate limiting, external auth), commercial rover compatibility, or scientific/operational positioning readiness.
