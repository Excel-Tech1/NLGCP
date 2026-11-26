# NLGCP Technical Decision Register

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Authoritative ADR Directory:** [`docs/technical-baseline/v1.0/adr/`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/)
**Last Updated:** 2026-11-26

---

## 1. Governance Policy

Per [`AGENTS.md`](file:///home/excellence/NLGCP/AGENTS.md), architectural changes require an explicit Architecture Decision Record (ADR) or documented superseding decision. Silent architectural drift is prohibited.

---

## 2. Technical Baseline v1.0 ADRs (`ADR-001` – `ADR-012`)

| ADR ID | Decision Title | Baseline File | Current Implementation & Compliance Status |
|---|---|---|---|
| **ADR-001** | Source-Independent GNSS Ingestion | [`ADR-001-source-independent-ingestion.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-001-source-independent-ingestion.md) | Active — Phase 10 Go/Python clients decouple ingestion from upstream CORS vendor/caster; real live ingestion currently `BLOCKED` (`GN-01`). |
| **ADR-002** | RTKLIB as Primary Real-Time / Baseline Core | [`ADR-002-rtklib-primary-realtime-core.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-002-rtklib-primary-realtime-core.md) | Active — Unmodified `RTKLIB v2.4.2-p13` (`71db0ffa…`) pinned by SHA-256 across Phases 3, 5, 7, 11, 12, and B-02. |
| **ADR-003** | PRIDE PPP-AR for Independent Offline Validation | [`ADR-003-pride-pppar-validation.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-003-pride-pppar-validation.md) | Active — `PRIDE PPP-AR 3.2.8` (`4907bfe5…`) produced verified IGS20 2024 DOY 026 coordinates and ZTD; 2011 offline PPP blocked by absent 2011 `SP3`/`CLK`. |
| **ADR-004** | Go for High-Concurrency GNSS Ingestion | [`ADR-004-go-ingestion.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-004-go-ingestion.md) | Active — `services/gnss-ingestor` implemented in Go (`1.25.6`) with `internal/ntrip` and `internal/health` tests passing; `SEC-05` HTTP timeouts remain open before non-loopback use. |
| **ADR-005** | NATS JetStream for Internal Event Streaming | [`ADR-005-nats-jetstream.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-005-nats-jetstream.md) | Active — Local Compose NATS (`127.0.0.1:4222`) & `correction.{replay,live}.*` subjects defined; runtime streaming wire-up (`BE-02`) and NATS auth/TLS (`SEC-06`) open. |
| **ADR-006** | PostgreSQL + PostGIS for Station & Spatial Metadata | [`ADR-006-postgresql-postgis.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-006-postgresql-postgis.md) | Active — Local Compose Postgres/PostGIS (`127.0.0.1`); `SEC-06` default `CHANGE_ME` password must be removed before controlled-network use. |
| **ADR-007** | Separate Control Plane and Real-Time Correction Plane | [`ADR-007-separate-control-and-correction-planes.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-007-separate-control-and-correction-planes.md) | Active — `apps/api` + `apps/web` strictly separated from `services/correction-service` and `services/gnss-ingestor`. |
| **ADR-008** | Local Service Cells | [`ADR-008-local-service-cells.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-008-local-service-cells.md) | Active — Spatial hull stratification in Phase 6/7 & B-02 empirically confirmed interior convex-hull gains vs. perimeter extrapolation degradation. |
| **ADR-009** | Immutable Raw GNSS Archive | [`ADR-009-immutable-raw-archive.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-009-immutable-raw-archive.md) | Active & Enforced — Raw archives (`incoming/`, `00-deliveries/`, `raw/`) never altered; B-00 SHA-256 verification (`nlgcp archive verify`) audits integrity strictly read-only. |
| **ADR-010** | Docker Compose Pilot First, Kubernetes Later | [`ADR-010-docker-pilot-kubernetes-later.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-010-docker-pilot-kubernetes-later.md) | Active — Single-host `compose.yml` only; zero Kubernetes manifests added. |
| **ADR-011** | Fail-Closed Scientific & Operational Integrity | [`ADR-011-fail-closed-integrity.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-011-fail-closed-integrity.md) | Active & Enforced — Enforced across Phases 4–12, B-02 (`12/12` failure scenarios, `assert_no_rover_leakage()`), and B-00 (`exit 1`/`3`, authentic/synthetic isolation). |
| **ADR-012** | Hybrid VRS / Single-Base Correction Architecture | [`ADR-012-hybrid-vrs-single-base.md`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/adr/ADR-012-hybrid-vrs-single-base.md) | Active — Phase 8 hybrid decision engine blocks unvalidated VRS and falls back deterministically to single-base `EKAK00NGA`; operational VRS remains `VRS_GEOMETRY_ONLY` / `FORBIDDEN`. |

---

## 3. Documented Post-Baseline Operational & Research Decisions (Non-Superseding)

| Date | Decision | Authoritative Record | Scope |
|---|---|---|---|
| 2026-09-09 | Retain operational Phase 6 `BEST = ZERO` and Phase 7 `VRS_GEOMETRY_ONLY` after 13-bug geometry review (`geometry-v3`) | [`docs/phase6-7-scientific-validation.md`](file:///home/excellence/NLGCP/docs/phase6-7-scientific-validation.md) | Scientific promotion gate |
| 2026-11-25 | Formally defer Phase 13 web dashboard UI; document 10 future read-only `/api/v1` prerequisites | [`12-day7-backend-architecture-audit.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/12-day7-backend-architecture-audit.md) | Sprint scope control |
| 2026-11-25 | Isolate authentic experimental VRS loopback mountpoint `/NLGCP_VRS_EXP` strictly from synthetic `/NLGCP_TEST` | [`phase6_7_end_to_end_integration_report.md`](file:///home/excellence/NLGCP/docs/research/phase6_7_end_to_end_integration_report.md) | Lab segregation (`127.0.0.1`) |
| 2026-11-26 | Enforce autonomous epoch-0 SPP GGA virtual ARP for B-02 VRS positioning (zero truth-coordinate leakage) | [`b02_offline_rover_positioning_benchmark.md`](file:///home/excellence/NLGCP/docs/research/b02_offline_rover_positioning_benchmark.md) | Benchmark fairness |
| 2026-11-26 | Establish machine-readable `research/archive/` + strictly read-only `nlgcp archive` verification CLI (`B-00`) | [`b00_research_archive_architecture.md`](file:///home/excellence/NLGCP/docs/architecture/b00_research_archive_architecture.md) | Reproducibility foundation |
