# NLGCP Project Status (Synchronized Index)

**Authoritative Status Record:** [`PROJECT_STATUS.md`](file:///home/excellence/NLGCP/PROJECT_STATUS.md) (repository root — single authoritative phase-by-phase table)
**Active Handoff:** [`CURRENT_WORK.md`](file:///home/excellence/NLGCP/CURRENT_WORK.md)
**Evidence Log:** [`EVIDENCE_INDEX.md`](file:///home/excellence/NLGCP/EVIDENCE_INDEX.md)
**Machine-Readable Archive:** [`research/archive/`](file:///home/excellence/NLGCP/research/archive/)
**Last Synchronized:** 2026-11-26

---

## 1. Governance Rule

To avoid duplicate drifting status tables, the root [`PROJECT_STATUS.md`](file:///home/excellence/NLGCP/PROJECT_STATUS.md) remains the **single authoritative phase-status table** for NLGCP. This document provides a concise executive roll-up synchronized with root `PROJECT_STATUS.md` and `research/archive/`.

---

## 2. Milestone Summary (as of 2026-11-26)

| Workstream / Milestone | Status | Evidential Summary |
|---|---|---|
| **B-00 Research Archive & Reproducibility Foundation** | **Complete (Pending Review/Commit)** | Machine-readable archive (`research/archive/`), read-only `nlgcp archive` verification CLI, 21 datasets, 17 experiments, 24 artifacts (+311 nested B-02 outputs), 8 software records, 18 findings, 12 limitations, 14 publication claims, 14 security findings, 6 reproduction records. |
| **B-02 Offline Rover Positioning Benchmark** | **Complete** (`5b5217a`) | 52 full-24h (`2,880` ep) RTKLIB runs, 311 hashed outputs, 12/12 failure checks. Verified 2024 `PHRI` extrapolation: static H `+8.23%`, kinematic 3D `+14.14%`, kinematic H `+5.70%` inconclusive. Interior 2011 `OSGF` (provisional): kinematic H `+56.65%`, scatter `-57.2%`, DGPS H `+45.38%`. **Genuine RTK FIX = `0.0%`**. |
| **Phase 6/7 Atmospheric & Experimental VRS Sprint** | **Complete** (`5b5217a`) | 3,018 2011 files audited; stratified LOOCV `+26.1%`–`+30.0%` interior gains; UNB3m ZHD `1.85 mm` vs. PRIDE ZTD; RTCM `1005`/`1074` + `NLGCP_VRS_EXP` + gLAB v6.0.0 (`1005`) validated. Operational defaults unchanged (`ZERO` / `VRS_GEOMETRY_ONLY`). |
| **14-Day Beta Sprint Days 1–7** | **Complete** (`5b5217a`) | Synthetic Phase 11 `1005`/`1074`/`1084` encoders, RTKLIB independent decode, loopback Phase 12 `NLGCP_TEST` caster, Day 6 integration assurance (6 defects fixed), Day 7 architecture/security audit (14 findings). Phase 13 dashboard formally deferred. |
| **Phases 0, 1, 4, 5, 6, 8, 9, 10** | **Complete** (scoped) | Offline engineering & pilots complete within documented single-day DOY 026 / synthetic boundaries; Phase 9 real replay & Phase 10 real live CORS remain `BLOCKED`. |
| **Phases 2, 3, 7, 11, 12** | **In Progress / Validation** | Verified multi-day coordinates, fixed-ambiguity RTK, promoted operational VRS, authentic RTCM encoding, and non-loopback hardened NTRIP remain open. |
| **Phases 13–17** | **Not Started** | User platform (deferred), Monitoring & Ops, Security Hardening, Field Validation, Controlled MVP Pilot. |

---

## 3. Preserved Safety & Operational Gates

- `OPERATIONAL_APPROVED = FORBIDDEN`
- Operational Phase 6 default: `BEST = ZERO`
- Operational Phase 7 default: `VRS_GEOMETRY_ONLY`
- Loopback-only network boundary (`127.0.0.1`) strictly enforced across services and Compose.
