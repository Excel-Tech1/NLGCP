# NLGCP System Architecture Overview

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Authoritative Baseline:** [`docs/technical-baseline/v1.0/`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/)
**Companion Audits:** [`12-day7-backend-architecture-audit.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/12-day7-backend-architecture-audit.md), [`b00_research_archive_architecture.md`](file:///home/excellence/NLGCP/docs/architecture/b00_research_archive_architecture.md)
**Last Updated:** 2026-11-26

---

## 1. Architectural Planes

NLGCP strictly separates four operational and research planes:

1. **Immutable Data & Provenance Plane (`/home/excellence/nlgcp-data` + `research/archive/`):**
   - Read-only raw GNSS observation archives (`incoming/`, `00-deliveries/`, `raw/`), broadcast navigation products (`external-products/brdc/`), derived working/processed outputs (`working/`, `processed/`, `validation/`), and the B-00 read-only provenance archive (`research/archive/` + `research/research_archive/`).
2. **Offline Scientific Research & Validation Plane (`research/`):**
   - `single_base_rtk` (Phase 3), `gnss_qc` (Phase 4), `network_rtk` (Phase 5), `atmospheric_spatial_model` (Phase 6), `vrs_generator` (Phase 7), `hybrid_decision_engine` (Phase 8), `southern_network_audit` (2011 recovery), `scientific_expansion` (2024 expansion), and `rover_benchmark` (Milestone B-02).
   - Interfaces with pinned external scientific tools: `RTKLIB v2.4.2-p13` (`rnx2rtkp`, `convbin`, native `input_rtcm3()`), `PRIDE PPP-AR 3.2.8` (`pdp3`), and `ESA/gAGE-UPC gLAB v6.0.0`.
3. **Correction Ingestion, Encoding & Loopback Distribution Plane (`research/` + `services/`):**
   - `research/rtcm_replay` (Phase 9 CRC-24Q framing, admission, replay), `research/ntrip_ingestion` + `services/gnss-ingestor` (Phase 10 Go/Python NTRIP client & capture), `research/rtcm_generation` (Phase 11 bit-level RTCM `1005`/`1074`/`1084` encoders + RTKLIB/gLAB adapters), and `services/correction-service` (Phase 12 strictly `127.0.0.1` loopback NTRIP v2/v1 caster hosting strictly segregated synthetic `NLGCP_TEST` and isolated experimental research `NLGCP_VRS_EXP` mountpoints).
   - `services/nrtk-engine` (C++ CTest shell) and `services/station-monitor` (placeholder) remain unimplemented for live real-time operation pending scientific blockers.
4. **Control Plane (`apps/api`, `apps/web`, `compose.yml`):**
   - FastAPI control-plane service (`apps/api`) and Next.js frontend (`apps/web`) backed by local Compose PostgreSQL/PostGIS, NATS JetStream, and Redis bound exclusively to `127.0.0.1`. Phase 13 UI dashboard development was formally deferred on Day 7 pending backend/scientific prerequisites.

---

## 2. Implemented vs. Unwired Runtime Boundaries

| Boundary | Status | Reference |
|---|---|---|
| Phase 3–7 offline scientific data pipeline → B-02 RTKLIB rover positioning benchmark | **Implemented & Executed** (offline, authentic 2011 + 2024 datasets) | [`b02_offline_rover_positioning_benchmark.md`](file:///home/excellence/NLGCP/docs/research/b02_offline_rover_positioning_benchmark.md) |
| Phase 7 experimental VRS → Phase 11 RTCM `1005`/`1074` → Phase 12 `NLGCP_VRS_EXP` loopback caster → RTKLIB + gLAB (`1005`) | **Implemented & Validated (Isolated Research Loopback)** | [`phase6_7_end_to_end_integration_report.md`](file:///home/excellence/NLGCP/docs/research/phase6_7_end_to_end_integration_report.md) |
| Phase 11 synthetic `1005`/`1074`/`1084` → Phase 12 `NLGCP_TEST` loopback caster → Client → RTKLIB | **Synthetically Validated (10/10 Demo Stages)** | [`11-day6-integration-assurance.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/11-day6-integration-assurance.md) |
| Phase 8 `DecisionResponse` → Phase 11 `CorrectionGenerationRequest` runtime adapter | **Not Yet Wired** (`BE-01`) | [`14-day7-beta-readiness-assessment.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/14-day7-beta-readiness-assessment.md) |
| Phase 10 Go ingestor live CORS stream → NATS JetStream → real-time VRS loop | **Blocked** (no authorized live CORS stream `GN-01`, no causal atmospheric filter `B-08`) | [`DEPLOYMENT_STATUS.md`](file:///home/excellence/NLGCP/docs/operations/DEPLOYMENT_STATUS.md) |
| Control-plane `/api/v1` diagnostics & Phase 13 UI | **Deferred** (per Day 7 scope review) | [`12-day7-backend-architecture-audit.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/12-day7-backend-architecture-audit.md) |
