# NLGCP Experiment Catalogue

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Machine-Readable Manifests:** [`research/archive/experiments/`](file:///home/excellence/NLGCP/research/archive/experiments/) (`17` registered experiments)
**Last Updated:** 2026-11-26

---

## 1. Registered Experiments (`NLGCP-EXP-2026-001` – `NLGCP-EXP-2026-017`)

| Experiment ID | Milestone | Title | Status | Data Tier | Validation Level | Repro Level / Status | Provenance Completeness |
|---|---|---|---|---|---|---|---|
| `NLGCP-EXP-2026-001` | Phase 2 / Recovery | 2024 Expansion + 2011 Southern Audit & Nav Recovery | `COMPLETED` | `AUTHENTIC` | `INTEGRATION_TESTED` | `L1` / `PARTIALLY_REPRODUCED` | Gaps recorded (early CLI/config not archived) |
| `NLGCP-EXP-2026-002` | Phase 3 | Offline Single-Base RTK & EKAK-PHRI Control | `COMPLETED` | `AUTHENTIC` | `INDEPENDENTLY_VALIDATED` | **`L3` / `REPRODUCED`** (in B-02) | Gaps recorded (early CLI/env not archived) |
| `NLGCP-EXP-2026-003` | Phase 4 | Full 2024 Canonical Dataset GNSS QC (`3,870` evals) | `COMPLETED` | `AUTHENTIC` | `INTEGRATION_TESTED` | `L1` / `NOT_ATTEMPTED` | Gaps recorded (config/env not archived) |
| `NLGCP-EXP-2026-004` | Phase 5 | Offline NRTK Pilot (`net-2024d026-phri-rover`) | `COMPLETED` | `AUTHENTIC` | `INDEPENDENTLY_VALIDATED` | `L1` / `NOT_ATTEMPTED` | Config hashed (`fd3d999e…`); env not archived |
| `NLGCP-EXP-2026-005` | Phase 6 (pre-review) | Pre-Review Atmospheric Pilot (`atm-2024d026-phri-target`) | **`SUPERSEDED`** | `AUTHENTIC` | `INTEGRATION_TESTED` | `L1` / `NOT_ATTEMPTED` | Superseded by `NLGCP-EXP-2026-006` |
| `NLGCP-EXP-2026-006` | Phase 6/7 Review | Reviewed Atmospheric LOOCV (`*-geometry-v3`) | `COMPLETED` | `AUTHENTIC` | `INDEPENDENTLY_VALIDATED` | `L1` / `PARTIALLY_REPRODUCED` | Config hashed (`f9828fec…`); shell cmd not recorded |
| `NLGCP-EXP-2026-007` | Phase 6/7 Sprint | Multi-Day Ionosphere, ROTI, UNB3m vs PRIDE ZTD & LOOCV | `COMPLETED` | `AUTHENTIC` | `INDEPENDENTLY_VALIDATED` | `L2` / `NOT_ATTEMPTED` | Runner + env recorded; no static config file |
| `NLGCP-EXP-2026-008` | Phase 7 / Review | Reviewed Geometry-Only VRS (`*-geometry-v3`, `78,060` obs) | `COMPLETED` | `AUTHENTIC` | `INTEGRATION_TESTED` | `L1` / `NOT_ATTEMPTED` | Early feature-branch CLI/config not archived |
| `NLGCP-EXP-2026-009` | Phase 6/7 Sprint | Experimental VRS + RTCM `1005/1074` + gLAB + `NLGCP_VRS_EXP` | `COMPLETED` | `AUTHENTIC` | `INDEPENDENTLY_VALIDATED` | **`L4` / `PARTIALLY_REPRODUCED`** | Runner + env recorded; gLAB `1005` only |
| `NLGCP-EXP-2026-010` | Phase 8 | Hybrid Decision Engine Reviewed DOY 026 Pilot | `COMPLETED` | `AUTHENTIC` | `INTEGRATION_TESTED` | `L1` / `NOT_ATTEMPTED` | Early feature-branch CLI/config not archived |
| `NLGCP-EXP-2026-011` | Phase 9 | Synthetic RTCM Replay Pilot + Real-Source Audit | `COMPLETED` | `SYNTHETIC` | `INTEGRATION_TESTED` | `L1` / `NOT_ATTEMPTED` | Real replay `BLOCKED`; synthetic pilot only |
| `NLGCP-EXP-2026-012` | Phase 10 | Synthetic Live CORS Loopback Pilot + Real-Endpoint Audit | `COMPLETED` | `SYNTHETIC` | `INTEGRATION_TESTED` | `L1` / `NOT_ATTEMPTED` | Real live ingestion `BLOCKED`; synthetic only |
| `NLGCP-EXP-2026-013` | Beta Sprint D2–3 | Phase 11 Synthetic RTCM `1005/1074/1084` + RTKLIB Decode | `COMPLETED` | `SYNTHETIC` | `INDEPENDENTLY_VALIDATED` | `L2` / `REPRODUCED` | Synthetic only; GLONASS FCN absent in `1084` |
| `NLGCP-EXP-2026-014` | Beta Sprint D4–6 | Phase 12 Loopback NTRIP `NLGCP_TEST` + Day 6 Assurance | `COMPLETED` | `SYNTHETIC` | `INTEGRATION_TESTED` | `L2` / `REPRODUCED` | Synthetic loopback (`127.0.0.1`) only |
| `NLGCP-EXP-2026-015` | Beta Sprint Day 7 | Backend Architecture, Security & Beta Readiness Audit | `COMPLETED` | `DOCUMENTATION_AUDIT` | `INTEGRATION_TESTED` | `L2` / `REPRODUCED` | Catalogues `SEC-01`..`SEC-14` (`OPEN`) |
| **`NLGCP-EXP-2026-016`** | **B-02 Benchmark** | **Rover Positioning Benchmark — `2024-01-26` `PHRI00NGA` (Verified IGS20)** | `COMPLETED` | `AUTHENTIC` | **`INDEPENDENTLY_VALIDATED`** | **`L3` / `REPRODUCED`** | **`COMPLETE` (0 gaps; 311 nested outputs)** |
| **`NLGCP-EXP-2026-017`** | **B-02 Benchmark** | **Rover Positioning Benchmark — `2011-03-20` `OSGF` (Interior 8-Ref Hull)** | `COMPLETED` | `AUTHENTIC` | `INTEGRATION_TESTED` | **`L3` / `REPRODUCED`** | **`COMPLETE` (0 gaps; provisional truth only)** |

---

## 2. Lineage Highlights

- **Supersession:** `NLGCP-EXP-2026-006` (`geometry-v3`) explicitly `SUPERSEDES` pre-review `NLGCP-EXP-2026-005` (`atm-2024d026-phri-target`).
- **Numerical Reproduction (`Level 3`):** `NLGCP-EXP-2026-016` (`B-02`) explicitly `REPRODUCES` `NLGCP-EXP-2026-002` (`Phase 3` `EKAK→PHRI` static control `0.9677/0.5838/1.1301 m` vs. `0.968/0.584/1.130 m`).
- **Partial Independent Cross-Verification (`Level 4`):** `NLGCP-EXP-2026-009` cross-decoded CRC-24Q and RTCM `1005` via both RTKLIB `v2.4.2-p13` and unmodified ESA/gAGE-UPC gLAB `v6.0.0` (`MSM4` remains unsupported by gLAB).

## 3. Verification Command

```bash
.venv/bin/nlgcp archive experiments list
.venv/bin/nlgcp archive experiments validate
```
