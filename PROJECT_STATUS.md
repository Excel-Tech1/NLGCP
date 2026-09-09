# Project Status

Allowed statuses: Not Started, Planning, In Progress, Blocked, Testing, Validation, Complete.

| Phase | Status | Scope |
|---|---|---|
| Phase 0 — Documentation & Architecture | Complete | Authoritative bootstrap architecture and phase plan |
| Phase 1 — Engineering Foundation | Complete | Engineering foundation verified: toolchains, Compose services, health checks, GNSS tool provenance, and project-wide quality gates pass |
| Phase 2 — Data Acquisition & Station Registry | In Progress | Approved data acquisition and authoritative station metadata; P2-S1 metadata import foundation, P2-S2 RINEX inventory, and P2-S3 file manifest complete |
| Phase 3 — Single-Base RTK Baseline | Validation | Reproducible offline single-base RTK baseline; real scientific execution completed for DOY 2024/026 (ABFC base, 3 float-only baselines) plus a shorter-baseline control experiment (EKAK-PHRI 105.553 km, also FLOAT-only, horiz RMSE 0.968 m) with recorded evidence, figures, tables, and validation report; fixed-ambiguity demonstration is a documented follow-on |
| Phase 4 — GNSS Quality-Control Engine | Complete | Engineering milestone COMPLETE and full 2024 dataset validation run COMPLETE on `main` (1290 canonical sessions, 8 stations, 3870 profile results, 0 unexpected failures; archive ACCEPT 694/WARN 596; single-base RTK ACCEPT 4/REJECT 341/BLOCKED 945; network RTK ACCEPT 4/REJECT 341/BLOCKED 945; 7 navigation-covered sessions; DOY 026 four-station ACCEPT overlap ABFC/EKAK/MGBO/PHRI; report, tables, figures generated). Scientific QC profile calibration remains PROVISIONAL pending Level 3 review against Nigerian field evidence — a documented follow-on, not part of this milestone |
| Phase 5 — Offline NRTK Engine | Complete | Engineering COMPLETE and real-data pilot COMPLETE on `main` (fail-closed `network_rtk` ACCEPT admission; verified-coordinate geometry; common-epoch overlap; 3 independent `rnx2rtkp v2.4.2-p13` baseline inputs in `net-2024d026-phri-rover`; residual dataset; aggregate metrics; CLI; 44 tests; `make check` green). Scientific scope: representative DOY 026 only (sole ≥3-station ACCEPT overlap); nearest single reference outperformed the network-input mean — no general NRTK improvement proven or claimed |
| Phase 6 — Atmospheric & Spatial Error Model | Complete | Engineering COMPLETE and real-data pilot COMPLETE on the Phase 5 DOY 026 admitted network (RINEX-extracted GPS L1/L2 geometry-free arc-detrended SD proxies for all 6 pairs; Saastamoinen/Niell a priori troposphere; datum-anchored spatial records; zero/nearest/IDW/planar interpolation; identical-sample LOOCV with zero control winning honestly; weak pilot decorrelation slope 0.59 mm/km). Scientific scope: representative DOY 026 only (sole ≥3-station ACCEPT overlap; 3 references over 105–1029 km); no interpolator beat the zero control — no general spatial-correction improvement proven or claimed |
| Phase 7 — VRS Generator | Validation | Engineering COMPLETE and four real DOY 026 held-out pilots COMPLETE as reviewed `*-geometry-v3` (78,060 observations, 480/480 epochs, 30 GPS sats/rotation; nearest anchor, pinned RTKLIB geometry, zero-only fail-closed selection, clock/ambiguity-aware diagnostics, provenance/resumability, CLI). Scientific review COMPLETE (APPROVED_WITH_PROVISIONAL_LIMITATIONS); merge conditions satisfied on the review branch (geometry-v3 PILOT_EVIDENCE, old-ID supersession, v1/v2 retirement). Correction mode ZERO / VRS_GEOMETRY_ONLY; no model promoted. Positioning validation NOT PERFORMED; operational correction readiness NOT CLAIMED; no Phase 8 implementation |
| Phase 6/7 — Scientific Validation & Geometry Hardening | Validation | Review sprint COMPLETE 2026-09-09 on `phase67/scientific-validation-geometry-hardening`, closure committed: 13 bugs fixed (orbits, ENU, containment, GF sign, Niell, LOOCV datum, parsing); Phase 6 regenerated as `*-geometry-v3` (engineering COMPLETE, reviewed pilot COMPLETE, promotion NONE, scope PROVISIONAL/pilot-only; zero 3.076 m still best, n=15948, all folds EXTRAPOLATION); VRS regenerated as `*-geometry-v3` (engineering COMPLETE, review APPROVED_WITH_PROVISIONAL_LIMITATIONS, mode ZERO/VRS_GEOMETRY_ONLY, positioning NOT PERFORMED, operational readiness NOT CLAIMED; 78,060 obs, leakage excluded); `make check` PASS (355 tests). Merge conditions satisfied; branch ready to merge into main. Phase 8 NOT STARTED |
| Phase 8 — Hybrid Correction Decision Engine | Not Started | Correction selection |
| Phase 9 — Recorded RTCM Replay | Not Started | Deterministic replay |
| Phase 10 — Live CORS Ingestion | Not Started | Approved live streams |
| Phase 11 — RTCM Correction Generation | Not Started | Standards-compliant encoding |
| Phase 12 — NTRIP Correction Service | Not Started | Correction distribution |
| Phase 13 — Basic User Platform | Not Started | User control plane |
| Phase 14 — Monitoring & Operations | Not Started | Operational visibility |
| Phase 15 — Security & Hardening | Not Started | Production security controls |
| Phase 16 — Field Validation | Not Started | Controlled rover validation |
| Phase 17 — Controlled MVP Pilot | Not Started | Limited real-user pilot |

Phase completion is evidence-based. Compilation or synthetic tests are not scientific validation.
