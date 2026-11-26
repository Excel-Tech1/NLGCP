# Phase 7 Experimental VRS Generation Implementation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Phase:** Phase 7 — Virtual Reference Station (VRS) Generation
**Date:** 2026-11-25
**Branch:** `research/nlgcp-14-day-beta-sprint`
**Validation Status:** `TECHNICALLY_VALIDATED` (experimental observation-based VRS + RTCM 1005/1074 bridge implemented and verified; operational VRS remains `BLOCKED` / `FORBIDDEN`)

---

## 1. Objective and Separation from Operational Gates

Prior to this sprint, Phase 7 (`research/vrs_generator/src/nlgcp_vrs/`) supported only geometry-only virtual coordinate translation (`VRS_GEOMETRY_ONLY` with `spatial_correction = ZERO`), with no observation-level atmospheric synthesis and no connection to Phase 11 RTCM generation or Phase 12 NTRIP distribution.

This sprint advances Phase 7 to an **observation-based experimental VRS engine** and **RTCM 3.x bridge** while strictly preserving every pre-existing operational safety gate:

- `research/vrs_generator/src/nlgcp_vrs/models.py` (`correction_gate()`) was **not modified**; operational promotion continues to fail closed to `mode = "VRS_GEOMETRY_ONLY"`, `spatial_correction = "ZERO"`, `automatic_correction_approved = False`.
- All new experimental VRS APIs reside in dedicated modules (`experimental_vrs.py` and `rtcm_bridge.py`), emit explicit maturity enums (`VrsMaturity.GEOMETRY_ONLY_VRS` vs. `VrsMaturity.EXPERIMENTAL_OBSERVATION_VRS`), hard-code `operational_approved = False`, reject `VrsMaturity.OPERATIONALLY_APPROVED_VRS` fail-closed, and stamp every result with `EXPERIMENTAL OBSERVATION-BASED VRS RESEARCH OUTPUT — NOT OPERATIONALLY APPROVED`.

---

## 2. Implemented Architecture

### 2.1 Experimental VRS Synthesis Engine (`research/vrs_generator/src/nlgcp_vrs/experimental_vrs.py`)

| Component | Implementation Details |
|---|---|
| **Maturity & Outcome Enums** | `VrsMaturity` (`GEOMETRY_ONLY_VRS`, `EXPERIMENTAL_OBSERVATION_VRS`, `EXPERIMENTALLY_VALIDATED_VRS`, `OPERATIONALLY_APPROVED_VRS` [forbidden]) and 7 fail-closed `VrsOutcome` states (`EXPERIMENTAL_VRS_GENERATED`, `VRS_GENERATION_BLOCKED`, `INSUFFICIENT_NETWORK_GEOMETRY`, `INSUFFICIENT_OBSERVATION_COVERAGE`, `ATMOSPHERIC_MODEL_UNAVAILABLE`, `INVALID_STATION_COORDINATES`, `VALIDATION_FAILED`). |
| **Coordinate Validation (`validate_vrs_coordinate`)** | Verifies non-empty provenance metadata (`reference_frame`, `coordinate_epoch`, `provenance_status`), finite ECEF components, terrestrial radius `[6300, 6450] km`, ellipsoidal height `[-500, 10000] m`, and WGS84 ECEF↔geodetic round-trip consistency `< 0.1 mm`. |
| **Exact Geometric & Sagnac Range Shift (`_sat_pos_and_range_at_rx`)** | Iteratively solves light-time transmission epoch `t_tx = tow_rx - tau` and Earth-rotation Sagnac transformation from broadcast GPS ephemerides (`BroadcastEphemeris`) for both the nearest reference anchor `A` and virtual target `V`, computing `delta_rho = rho_V - rho_A` and `delta_sv_clk = -(clk_V - clk_A)` plus topocentric elevation/azimuth (`>= 15°` mask). |
| **Separated Tropospheric Differential Delay** | Supports three explicit modes: `zero` (`delta_tropo = 0`), `unb3m` (UNB3m latitude/DOY ZHD+ZWD mapped via Niell 1996 hydrostatic & wet mapping functions for `V` and `A`), and `network_ztd` (spatially interpolated reference-network ZWD + UNB3m ZHD at `V` vs. anchor ZHD/ZWD at `A`, strictly excluding target ZTD). |
| **Separated Ionospheric Differential L1 Delay** | Interpolates anchor-referenced differential L1 slant ionosphere (`zero`, `nearest`, `idw`, `idw2`, `planar`, or `ipp_idw2` using Ionospheric Pierce Point great-circle weights) strictly from reference stations (zero held-out target leakage). |
| **Physically Signed Observation Synthesis** | Applies opposite ionospheric dispersion signs to code (`+I`) vs. carrier phase (`-I`) and frequency scaling `gamma = (f1/f2)^2`: `C1_vrs = C1_A + G + delta_I1`, `P2_vrs = P2_A + G + gamma * delta_I1`, `L1_vrs = L1_A + (G - delta_I1) / lambda_1`, `L2_vrs = L2_A + (G - gamma * delta_I1) / lambda_2`, where `G = delta_rho + delta_sv_clk + delta_tropo`. |
| **Ambiguity Policy Transparency** | Every `ExperimentalVrsObs` explicitly records `ambiguity_policy = "ANCHOR_RELATIVE_FLOAT"`. No network integer ambiguity resolution (IAR) or RTK FIX is claimed. |
| **Fail-Closed Quality Control (12 Gates)** | Blocks operational promotion, unsupported GNSS message families, invalid target/reference coordinates, held-out target leakage into references, `< 3` references, convex-hull extrapolation (when `require_interior_hull=True`), missing simultaneous epochs, single-frequency anchor (missing L1/L2/P2/C1), missing ionospheric or ZTD model when non-zero mode requested, half-cycle LLI (`bit 1`), below-mask satellites, excessive atmospheric correction (`> 50 m`), and zero surviving observations. |
| **Held-Out Target Residual Validator** | `validate_experimental_vrs_against_target()` evaluates synthesized `C1`, `P2`, `L1`, `L2`, and geometry-free `GF` observables against withheld real target observations using epoch-mean-removed single differences (eliminating receiver clock bias for `C1`/`P2`) and consecutive-epoch double differences / time differences (eliminating constant integer ambiguities for `L1`/`L2`/`GF`). |

### 2.2 Phase 7 → Phase 11/12 RTCM Bridge (`research/vrs_generator/src/nlgcp_vrs/rtcm_bridge.py`)

| Feature | Design Choice |
|---|---|
| **Zero Duplicate RTCM Encoders** | Directly reuses Phase 11 `ReferenceStation1005`, `Msm4Message`, `Msm4Cell`, and Phase 9 `encode_payload_frame()` (`crc24q`). |
| **RTCM 1005 Non-Physical VRS Flag** | Encodes `reference_station_indicator = True` (RTCM DF024 = `1`), explicitly signalling to any compliant GNSS decoder that the station is a computed virtual reference station rather than a physical monument. |
| **RTCM 1074 GPS MSM4 Dual-Frequency Signals** | Maps `C1/L1/S1` to GPS MSM Signal ID `2` (`1C`) and `P2/L2/S2` to GPS MSM Signal ID `9` (`2P`), matching RINEX 2.11 observable semantics. |
| **Exact Integer-Cycle Per-Arc Phase Alignment** | RTCM MSM4 fine phase range is bounded by `±1171.0 m` relative to the satellite rough range (`FINE_PHASE_LIMIT_M`). Real RINEX carrier phases contain arbitrary initial integer cycle offsets (~`10^7–10^8` cycles). For each continuous slip-free `(satellite, signal)` arc, the bridge applies one constant exact integer offset `delta_n = round((P_init - L_init * lambda) / lambda) ∈ ℤ`. Fractional phase, epoch-to-epoch phase differences, and double-difference integer ambiguity structure remain mathematically invariant, and every applied offset is recorded in `bundle.integer_arc_offsets`. |
| **Classification & Handoff Contract** | Tags every `GeneratedCorrectionFrame` with `OutputClassification.RESEARCH_VALIDATION` (never `OPERATIONAL_APPROVED` and never `SYNTHETIC_TEST_ONLY`) and emits a signed `CorrectionStreamArtifact` with `mode = "VRS_EXPERIMENTAL"`, `virtual_station_id`, `message_families = ("REFERENCE_STATION_1005", "MSM4_GPS_1074")`, and SHA-256 `provenance_fingerprint`. |

---

## 3. Verification and Code Quality

- **Static Checks:** `ruff check` (`All checks passed!`) and strict `mypy` (`0` errors across all `249` repository source files including `experimental_vrs.py`, `rtcm_bridge.py`, and `scripts/run_phase7_vrs_sprint.py`).
- **Unit & Integration Tests (`research/vrs_generator/tests/test_experimental_vrs_and_integration.py`):** Verified existing operational `correction_gate()` immutability, WGS84 coordinate round-trip `< 0.1 mm`, exact opposite code (`+I`) vs. carrier-phase (`-I`) ionospheric dispersion signs on `C1/P2/L1/L2`, fail-closed blocking on operational promotion / extrapolation / missing atmospheric field, RTCM `1005 + 1074` encoding with integer-cycle arc alignment, isolated `NLGCP_VRS_EXP` loopback NTRIP streaming, `NLGCP_TEST` cross-publication blocking, and independent decoding via RTKLIB `convbin`, RTKLIB native `input_rtcm3`, and ESA/gAGE-UPC gLAB v6.0.0.
