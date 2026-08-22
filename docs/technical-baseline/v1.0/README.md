# Nigeria Localised GNSS Correction Platform (NLGCP) - Technical Documentation Baseline

**Baseline:** v1.0  
**Date:** 2026-08-21

This repository is the authoritative system-design baseline for the proposed Nigeria-wide RTK/NRTK correction platform. It is deliberately implementation-oriented and designed so a GNSS research team, backend/platform engineers and operations staff can work from the same architecture.

## Start here

1. `DOCUMENTATION_STATUS.md` - completion and locked/open decisions.
2. `docs/01-product-and-system-vision.md`
3. `docs/02-system-requirements-specification.md`
4. `docs/08-overall-system-architecture.md`
5. `docs/09-technology-stack-and-architecture-decisions.md`
6. `docs/24-technical-roadmap-and-national-expansion-plan.md`

## Architecture baseline

- NIGNET-anchored, source-independent station ingestion.
- Local/regional NRTK/VRS cells, nationally coordinated.
- VRS primary; empirically eligible single-base fallback; fail-closed integrity.
- RTKLIB/custom C/C++ real-time GNSS core.
- PRIDE PPP-AR precise offline validation.
- Go ingest, NATS JetStream, PostgreSQL/PostGIS, Redis, S3/MinIO.
- FastAPI control plane, Next.js/TypeScript/MapLibre frontend.
- RTCM/NTRIP correction delivery independent of the web UI.
- Docker Compose for research/pilot; Kubernetes only at justified production scale.

## Repository map

- `docs/` - 24 authoritative design documents.
- `adr/` - 12 locked Architecture Decision Records.
- `diagrams/` - canonical architecture diagrams.
- `schemas/` - canonical data/experiment examples.
- `runbooks/` - initial operational emergency procedures.

## What “documentation complete” means

Foundational product, scientific, data, component, security, deployment, operations and validation architecture has been specified. The next phase is evidence-driven implementation. Numeric thresholds explicitly labelled pilot-derived remain open because they must be measured, not guessed.
