# Project Status

Allowed statuses: Not Started, Planning, In Progress, Blocked, Testing, Validation, Complete.

| Phase | Status | Scope |
|---|---|---|
| Phase 0 — Documentation & Architecture | Complete | Authoritative bootstrap architecture and phase plan |
| Phase 1 — Engineering Foundation | Complete | Engineering foundation verified: toolchains, Compose services, health checks, GNSS tool provenance, and project-wide quality gates pass |
| Phase 2 — Data Acquisition & Station Registry | In Progress | Approved data acquisition and authoritative station metadata; P2-S1 metadata import foundation, P2-S2 RINEX inventory, and P2-S3 file manifest complete |
| Phase 3 — Single-Base RTK Baseline | Validation | Reproducible offline single-base RTK baseline; real scientific execution completed for DOY 2024/026 (ABFC base, 3 float-only baselines) plus a shorter-baseline control experiment (EKAK-PHRI 105.553 km, also FLOAT-only, horiz RMSE 0.968 m) with recorded evidence, figures, tables, and validation report; fixed-ambiguity demonstration is a documented follow-on |
| Phase 4 — GNSS Quality-Control Engine | Complete | Engineering milestone COMPLETE and full 2024 dataset validation run COMPLETE on `main` (1290 canonical sessions, 8 stations, 3870 profile results, 0 unexpected failures; archive ACCEPT 694/WARN 596; single-base RTK ACCEPT 4/REJECT 341/BLOCKED 945; network RTK ACCEPT 4/REJECT 341/BLOCKED 945; 7 navigation-covered sessions; DOY 026 four-station ACCEPT overlap ABFC/EKAK/MGBO/PHRI; report, tables, figures generated). Scientific QC profile calibration remains PROVISIONAL pending Level 3 review against Nigerian field evidence — a documented follow-on, not part of this milestone |
| Phase 5 — Offline NRTK Engine | Validation | Offline network framework implemented on `phase5/offline-network-rtk` (admission, geometry, overlap, multi-baseline RTKLIB inputs, residual dataset, metrics, CLI, 44 tests); real pilot `net-2024d026-phri-rover` COMPLETE (3/3 baselines, FLOAT-only incl. 2 isolated FIX epochs on 1029 km; no improvement claimed); `make check` green (EXIT 0) |
| Phase 6 — Atmospheric & Spatial Error Model | Not Started | Validated error models |
| Phase 7 — VRS Generator | Not Started | Validated virtual observations |
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
