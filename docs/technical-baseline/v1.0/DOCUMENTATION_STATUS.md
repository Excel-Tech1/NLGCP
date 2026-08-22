# Documentation Completion Register

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Baseline:** v1.0  
**Date:** 2026-08-21

## Overall status

**FOUNDATIONAL DOCUMENTATION AND SYSTEM ARCHITECTURE: COMPLETE FOR IMPLEMENTATION BASELINE.**

The remaining unknowns are empirical/operational parameters, not missing architecture. They must be calibrated from Nigerian data and pilot field work.

## Locked architecture decisions

- Source-independent ingest; NIGNET remains strategic national anchor.
- Local/regional service cells, not one nationwide interpolation surface.
- VRS preferred; validated single-base fallback; degraded/unavailable when integrity fails.
- RTKLIB/custom C/C++ live GNSS foundation; PRIDE PPP-AR offline precise validation.
- Go ingestion; NATS JetStream event backbone.
- PostgreSQL/PostGIS authoritative structured/spatial store; object storage for raw GNSS; Redis cache only.
- NTRIP correction plane separate from web/API control plane.
- Docker Compose pilot; Kubernetes later only if scale requires it.

## Pilot-derived parameters (intentionally open)

- maximum operational single-base distance by service condition;
- optimum/maximum reference-station spacing for validated local cells;
- epoch alignment tolerance;
- station-health and residual thresholds;
- ambiguity acceptance/recovery thresholds;
- VRS relocation threshold;
- end-to-end latency and correction-age SLOs;
- field accuracy/fix-rate service commitments;
- exact RTCM message profiles per supported receiver family;
- retention periods and commercial session limits.

These must be closed by experiments documented in Documents 21 and 23.

## Document register

| File | Status | Change rule |
|---|---|---|
| 01-product-and-system-vision.md | Baseline complete | Implementation changes via ADR |
| 02-system-requirements-specification.md | Baseline complete | Implementation changes via ADR |
| 03-gnss-positioning-and-correction-strategy.md | Baseline complete | Implementation changes via ADR |
| 04-nignet-and-data-source-assessment.md | Baseline complete | Implementation changes via ADR |
| 05-cors-network-and-local-service-cell-design.md | Baseline complete | Implementation changes via ADR |
| 06-gnss-data-and-metadata-specification.md | Baseline complete | Implementation changes via ADR |
| 07-data-architecture-and-database-design.md | Baseline complete | Implementation changes via ADR |
| 08-overall-system-architecture.md | Baseline complete | Implementation changes via ADR |
| 09-technology-stack-and-architecture-decisions.md | Baseline complete | Implementation changes via ADR |
| 10-cors-ingestion-and-realtime-streaming-architecture.md | Baseline complete | Implementation changes via ADR |
| 11-gnss-quality-control-and-station-health.md | Baseline complete | Implementation changes via ADR |
| 12-single-base-rtk-processing-design.md | Baseline complete | Implementation changes via ADR |
| 13-network-rtk-and-ambiguity-processing.md | Baseline complete | Implementation changes via ADR |
| 14-atmospheric-and-network-error-modelling.md | Baseline complete | Implementation changes via ADR |
| 15-vrs-generation-and-hybrid-correction-engine.md | Baseline complete | Implementation changes via ADR |
| 16-rtcm-and-ntrip-correction-distribution.md | Baseline complete | Implementation changes via ADR |
| 17-platform-api-and-user-service-architecture.md | Baseline complete | Implementation changes via ADR |
| 18-security-and-access-control-architecture.md | Baseline complete | Implementation changes via ADR |
| 19-infrastructure-high-availability-and-disaster-recovery.md | Baseline complete | Implementation changes via ADR |
| 20-observability-monitoring-and-slo.md | Baseline complete | Implementation changes via ADR |
| 21-testing-validation-and-scientific-benchmarking.md | Baseline complete | Implementation changes via ADR |
| 22-deployment-operations-and-runbooks.md | Baseline complete | Implementation changes via ADR |
| 23-research-experiment-and-reproducibility-plan.md | Baseline complete | Implementation changes via ADR |
| 24-technical-roadmap-and-national-expansion-plan.md | Baseline complete | Implementation changes via ADR |
## ADR register

All ADRs in `adr/` are **Accepted**. A design change that conflicts with an accepted ADR requires a superseding ADR before implementation.

## Build readiness checklist

- [x] Product/system boundary defined.
- [x] Functional/non-functional requirements defined.
- [x] GNSS positioning strategy defined.
- [x] NIGNET/source integration model defined.
- [x] Local CORS/service-cell architecture defined.
- [x] GNSS data and metadata model defined.
- [x] Storage/database architecture defined.
- [x] Overall component architecture defined.
- [x] Technology stack locked.
- [x] Real-time ingestion/event architecture defined.
- [x] GNSS QC/station health architecture defined.
- [x] Single-base processing design defined.
- [x] NRTK/ambiguity design defined.
- [x] Atmospheric/interpolation design defined.
- [x] VRS/hybrid integrity design defined.
- [x] RTCM/NTRIP distribution architecture defined.
- [x] Platform API/user architecture defined.
- [x] Security architecture defined.
- [x] HA/DR architecture defined.
- [x] Observability/SLO framework defined.
- [x] Scientific validation strategy defined.
- [x] Deployment/operations/runbooks defined.
- [x] Research reproducibility framework defined.
- [x] National expansion roadmap defined.

## Next phase

**Implementation Phase 0:** repository/scaffold, station registry, reproducible RTKLIB + PRIDE environment, raw archive, initial data acquisition and single-base baseline reproduction.
