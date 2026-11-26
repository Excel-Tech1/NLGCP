# NLGCP Field Validation Status

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Phase 16 Status:** **`NOT STARTED`** (`BLOCKED` pending `B-01`, `B-03`, `B-06`–`B-09`)
**Hardware Validation Level:** **`NOT PERFORMED`**
**Last Updated:** 2026-11-26

---

## 1. Current Field & Hardware Validation State

| Validation Dimension | Current Status | Directly Observed Evidence |
|---|---|---|
| **Commercial GNSS Rover Receiver Testing** | `NOT_STARTED` | Zero commercial receivers (e.g., u-blox, Septentrio, Trimble, Leica, South, ComNav) have been tested against NLGCP RTCM streams. |
| **Hardware-in-the-Loop (HIL) Zero/Short Baseline Test** | `NOT_STARTED` | Not performed (`FV-01`, `FV-02`). |
| **Surveyed Nigerian Control-Point Field Campaign** | `NOT_STARTED` | No field campaign, antenna calibration inventory, or surveyed Nigerian benchmark campaign has been executed. |
| **Real-Time Over-the-Air NTRIP Streaming** | `BLOCKED` | Network boundary remains strictly `127.0.0.1` loopback (`SEC-01`–`SEC-10`); no authorized live Nigerian CORS source is admitted (`GN-01`). |
| **Offline Authentic Rover Positioning (`B-02`)** | `COMPLETED (FLOAT/DGPS ONLY)` | Offline `RTKLIB v2.4.2-p13` benchmark on authentic 2024 `PHRI` and 2011 `OSGF` RINEX files demonstrated FLOAT/DGPS improvements but **`0.0%` genuine RTK FIX**. Offline post-processing is **not** field validation. |

---

## 2. Mandatory Prerequisites Before Phase 16 Field Validation

Per [`14-day7-beta-readiness-assessment.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/14-day7-beta-readiness-assessment.md) and [`b02_rover_benchmark_limitations.md`](file:///home/excellence/NLGCP/docs/research/b02_rover_benchmark_limitations.md), field validation cannot begin until:

1. **Authorized Live CORS & Verified Coordinates (`GN-01` / `B-01` / `B-05`):** Multi-station Nigerian CORS streams with verified IGS20/ITRF monument coordinates and antenna calibrations.
2. **Causal Real-Time Atmospheric & Network IAR VRS (`B-03` / `B-08`):** Network double-difference integer ambiguity resolution achieving genuine centimetre RTK FIX and causal real-time epoch estimation.
3. **Multi-Decoder & Multi-GNSS RTCM Interoperability (`B-06` / `B-07`):** Independent non-RTKLIB MSM4 verification plus `1006`/`1007`/`1008`/`1033`, GLONASS FCN/`1230`, and multi-GNSS support.
4. **Controlled-Network Security Hardening (`B-09`):** Remediation of Day 7 `SEC-01`–`SEC-10` with TLS and managed authentication.
5. **Documented Field Protocol (`FV-01`):** Calibrated receiver/antenna inventory, independent surveyed control monuments, and pre-registered acceptance thresholds.
