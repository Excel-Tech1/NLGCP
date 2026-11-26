# NLGCP Publication Evidence Map

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Machine-Readable Map:** [`publication_evidence_map.json`](file:///home/excellence/NLGCP/research/archive/validation/publication_evidence_map.json) (`14` claims)
**Lineage Verifier:** `.venv/bin/nlgcp archive provenance report`
**Last Updated:** 2026-11-26

---

## 1. Publication Governance Rule

Every scientific, thesis, or technical claim about NLGCP MUST trace through a verified provenance chain:

`Claim` → `Finding(s)` → `Experiment(s)` → `Dataset(s) + Software + Artifact(s)`

Claims lacking supporting findings or contradicted by observed negative evidence are explicitly marked `INSUFFICIENT_EVIDENCE`, `REFUTED_OR_NEGATIVE`, or `BLOCKED` and MUST NOT be stated as established results.

---

## 2. Claim-to-Evidence Traceability Table (`NLGCP-CLM-001` – `014`)

| Claim ID | Status | Supporting Findings | Key Limitations | Claim Statement |
|---|---|---|---|---|
| `NLGCP-CLM-001` | `SUPPORTED_WITH_LIMITATIONS` | `FIND-001, FIND-014` | `LIM-001, 003, 004, 006` | On verified IGS20 `2024-01-26` `PHRI00NGA` (3-ref extrapolation, zero leakage), `vrs_idw2_unb3m` measurably improves static FLOAT H RMSE (`+8.23%`, CI `[+0.047, +0.121] m`) and kinematic 3D (`+14.14%`) over the physical anchor. |
| `NLGCP-CLM-002` | `SUPPORTED_WITH_LIMITATIONS` | `FIND-002, FIND-007` | `LIM-001, 002, 004, 006` | Inside an 8-ref Nigerian convex hull (`2011-03-20` `OSGF`), offline atmospheric VRS (`vrs_ipp_idw2_unb3m`) reduces kinematic H RMSE by `+56.65%`, static H by `+57.06%`, and truth-independent centered scatter by `-57.2%` vs. physical anchor. *(Provisional OSGoF truth only.)* |
| `NLGCP-CLM-003` | **`REFUTED_OR_NEGATIVE`** | `FIND-003, FIND-004` | `LIM-001` | *NLGCP experimental VRS currently achieves genuine centimetre-level RTK integer ambiguity resolution (FIX).* — **REFUTED (`0.0%` genuine FIX; 7 `Q=1` epochs confirmed false fixes).** |
| `NLGCP-CLM-004` | **`SUPPORTED`** | `FIND-005` | `LIM-006` | Geometry-only VRS without differential tropospheric modelling underperforms a physical anchor in `RTKLIB v2.4.2-p13` due to loss of automatic baseline hydrostatic cancellation in `zdres()`. |
| `NLGCP-CLM-005` | **`REFUTED_OR_NEGATIVE`** | `FIND-006` | `LIM-003, 011` | *Full-day 2024 `PHRI` kinematic H RMSE gain (`+5.70%`) is statistically conclusive under 3-ref extrapolation.* — **REFUTED (95% CI `[-0.085, +0.240] m` crosses zero).** |
| `NLGCP-CLM-006` | `SUPPORTED_WITH_LIMITATIONS` | `FIND-008` | `LIM-002, 003` | Spatial ionospheric interpolation beats `ZERO` inside multi-station hulls (`+26.1%`–`+30.0%` in 2011 9-station LOOCV), whereas sparse perimeter extrapolation remains `ZERO`-dominated. |
| `NLGCP-CLM-007` | `SUPPORTED_WITH_LIMITATIONS` | `FIND-015` | `LIM-003, 011` | UNB3m predicts Nigerian ZHD within `1.85 mm` RMSE vs. PRIDE PPP-AR ZTD on 2024 DOY 026 while exposing a `12.6 cm` coastal-vs-Harmattan ZWD gradient. |
| `NLGCP-CLM-008` | **`SUPPORTED`** | `FIND-014` | `LIM-001` | NLGCP reproduces its Phase 3 `EKAK→PHRI` static control (`105.553 km`) numerically to four decimals (`0.9677 / 0.5838 / 1.1301 m`) using pinned `RTKLIB v2.4.2-p13`. |
| `NLGCP-CLM-009` | `SUPPORTED_WITH_LIMITATIONS` | `FIND-016, FIND-010` | `LIM-005, 006, 007, 008` | Synthetic RTCM `1005/1074/1084` encoders and loopback `NLGCP_TEST` NTRIP operate byte-exact and decode cleanly in unmodified `RTKLIB v2.4.2-p13`. *(Synthetic-only; no GLONASS FCN in `1084`.)* |
| `NLGCP-CLM-010` | **`INSUFFICIENT_EVIDENCE`** | `FIND-010, FIND-018` | `LIM-006, 009` | *NLGCP RTCM `1005/1074` streams are independently verified across multiple non-RTKLIB MSM4 decoders and commercial receivers.* — **INSUFFICIENT (gLAB decodes `1005` only; zero receivers tested).** |
| `NLGCP-CLM-011` | **`INSUFFICIENT_EVIDENCE`** | `NONE` | `LIM-004, 005` | *NLGCP supports causal real-time streaming atmospheric VRS generation.* — **INSUFFICIENT (current leveling is offline non-causal).** |
| `NLGCP-CLM-012` | **`BLOCKED`** | `FIND-017` | `LIM-005` | *NLGCP ingests authorized live Nigerian CORS / NTRIP streams in production.* — **BLOCKED (`GN-01`).** |
| `NLGCP-CLM-013` | **`BLOCKED`** | `FIND-013` | `LIM-008, 009` | *NLGCP backend NTRIP caster is hardened for controlled-network or public deployment.* — **BLOCKED (`SEC-01`–`SEC-10`).** |
| `NLGCP-CLM-014` | **`BLOCKED`** | `FIND-003, 013, 017` | `LIM-001, 002, 003, 005, 008, 009` | *NLGCP is approved for operational GNSS correction service delivery (`OPERATIONAL_APPROVED`).* — **FORBIDDEN / BLOCKED.** |
