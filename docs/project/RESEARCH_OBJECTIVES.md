# NLGCP Research Objectives

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Archive Reference:** [`research/archive/`](file:///home/excellence/NLGCP/research/archive/)
**Last Updated:** 2026-11-26

---

## 1. Overarching Research Question

Can locally modelled Nigerian atmospheric (equatorial ionospheric and tropical tropospheric) corrections delivered through observation-based Virtual Reference Station (VRS) RTCM 3.x streams measurably improve rover positioning accuracy, stability, and ambiguity resolution compared with sparse physical single-base RTK baselines?

---

## 2. Structured Research Objectives & Current Evidential Status

| Objective ID | Research Objective | Linked Experiments | Current Status (2026-11-26) | Key Evidence & Open Blockers |
|---|---|---|---|---|
| **RO-01** | Establish an immutable, hash-verified multi-year Nigerian GNSS observation and coordinate archive with strict reference-frame provenance. | `NLGCP-EXP-2026-001`, `NLGCP-EXP-2026-003` | **In Progress (Partially Met)** | 1,290 canonical 2024 station-days + 220 BKG BRDC; 3,018 2011 RINEX files + 66 BKG nav. Only DOY 2024/026 has verified IGS20 coordinates; 2011 coords remain `PROVISIONAL_OSGOF_2011_01_01` (`B-01`). |
| **RO-02** | Quantify single-base RTK and offline multi-baseline NRTK performance across Nigerian baselines using pinned `RTKLIB v2.4.2-p13`. | `NLGCP-EXP-2026-002`, `NLGCP-EXP-2026-004` | **Completed (DOY 026 Scope)** | `105.553 km` `EKAK→PHRI` static FLOAT RMSE `0.968/0.584/1.130 m` (`0.0%` FIX); `470–690 km` baselines `1.093–1.377 m` H; reproduced to 4 decimals in B-02. |
| **RO-03** | Model equatorial Nigerian ionospheric dynamics (STEC, ROTI, plasma-bubble surges) and tropical troposphere (UNB3m vs. PRIDE ZTD), and test spatial interpolation under strict LOOCV. | `NLGCP-EXP-2026-005` (`SUPERSEDED`), `NLGCP-EXP-2026-006`, `NLGCP-EXP-2026-007` | **Completed (Experimental); Operational Default = ZERO** | Inside 9-station 2011 hulls, `idw2`/`ipp_idw2` beat `zero` by `+26.1%` to `+30.0%` (`+47.66%` at `OSGF`); perimeter/2024 extrapolation stays `zero`-dominated. UNB3m ZHD RMSE `1.85 mm` vs. PRIDE ZTD; `12.6 cm` coastal-Harmattan ZWD gradient. |
| **RO-04** | Synthesize leak-free observation-based VRS corrections and encode standards-compliant RTCM 3.x (`1005`/`1074`/`1084`) verified by independent decoders. | `NLGCP-EXP-2026-008`, `NLGCP-EXP-2026-009`, `NLGCP-EXP-2026-013` | **Completed (Experimental GPS 1005/1074); Non-RTKLIB MSM4 Open** | RTCM `1005`/`1074` decoded cleanly by RTKLIB `convbin` + `input_rtcm3()`; ESA gLAB v6.0.0 verified CRC-24Q + `1005` (`0.0000 m`), but MSM4 is unsupported (`B-06`); GLONASS FCN missing in standalone `1084` (`B-07`). |
| **RO-05** | Evaluate actual rover ENU positioning accuracy, repeatability, and integer ambiguity resolution using emitted experimental VRS RTCM streams (`B-02`). | `NLGCP-EXP-2026-016`, `NLGCP-EXP-2026-017` | **Completed (FLOAT/DGPS Gains Proven; FIX = 0.0%)** | Verified 2024 `PHRI` extrapolation: static H `+8.23%`, kinematic 3D `+14.14%`, kinematic H `+5.70%` inconclusive; interior 2011 `OSGF` (provisional): kinematic H `+56.65%`, scatter `-57.2%`, DGPS H `+45.38%`. Genuine RTK FIX = `0.0%` (`B-03`). |
| **RO-06** | Design fail-closed hybrid decision, RTCM replay, live CORS ingestion, and NTRIP correction distribution infrastructure without conflating transport with scientific validation. | `NLGCP-EXP-2026-010`..`015` | **Synthetically Validated (Loopback Lab); Live Blocked** | Loopback `127.0.0.1` `NLGCP_TEST` + isolated `NLGCP_VRS_EXP` verified byte-exact; real live CORS ingestion blocked (`GN-01`); 14 Day 7 security findings block non-loopback deployment (`B-09`). |
| **RO-07** | Guarantee reproducible, tamper-evident scientific lineage across all datasets, software binaries, experiments, negative findings, and publication claims (`B-00`). | B-00 Archive Foundation | **Implemented & Verified** | Central machine-readable registry under [`research/archive/`](file:///home/excellence/NLGCP/research/archive/) and read-only `nlgcp archive verify` CLI. |

---

## 3. Explicit Scientific Boundaries

- **Proven:** Offline atmospheric VRS measurably improves FLOAT and DGPS rover positioning (decisively inside an 8-station convex hull, modestly on static/3D under 3-station extrapolation).
- **Refuted / Not Achieved:** Genuine centimetre RTK integer ambiguity resolution (`FIX = 0.0%`), geometry-only VRS superiority over physical anchors, causal real-time atmospheric VRS streaming, commercial rover interoperability, and operational service approval.
