# 08. Overall System Architecture

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Architectural style

NLGCP uses a **real-time correction data plane** separated from a **digital control plane**.

### Correction data plane

CORS -> ingestion -> stream backbone -> epoch/QC -> GNSS/NRTK engine -> integrity -> RTCM -> NTRIP caster -> rover.

### Control plane

Identity, organisations, device registration, entitlements, coverage metadata, operations, configuration, billing hooks, dashboards, audit and reporting.

The control plane may configure and authorise the data plane, but page/API availability must not be a per-epoch dependency for existing correction processing.

## 2. Major components

1. **CORS Sources** - NIGNET, partners, platform-owned sites.
2. **Ingestion Gateways** - persistent NTRIP/TCP stream handling and timestamping.
3. **Real-Time Bus** - NATS subjects/streams for fan-out and replay.
4. **Archive Writer** - loss-tolerant preservation of RTCM/RINEX artefacts.
5. **Epoch Synchroniser** - aligns multi-station observations.
6. **Quality/Station Health Engine** - rejects stale or untrustworthy contributors.
7. **RTK/NRTK Core** - RTKLIB/custom C/C++ computational services.
8. **Atmospheric/Network Model** - residual estimation and interpolation.
9. **VRS Session Engine** - rover position, cell selection, virtual observations.
10. **Hybrid/Integrity Engine** - VRS vs single-base vs degraded decision.
11. **RTCM Encoder/Publisher** - correction stream construction.
12. **NTRIP Caster Tier** - standards-based external distribution.
13. **Platform API** - FastAPI control services.
14. **Web App** - Next.js/MapLibre operations and customer portal.
15. **Persistence** - PostgreSQL/PostGIS, object storage, Redis.
16. **Observability** - Prometheus/Grafana/central logs/alerts.

## 3. Trust boundaries

- Internet rover/user zone.
- Public gateway/caster/API zone.
- Private application services zone.
- Restricted GNSS processing/control zone.
- Restricted data stores and administrative management zone.

## 4. Scale model

A regional cell may run its processing close to its CORS sources while national services manage identity, configuration and monitoring. This limits latency and blast radius while enabling national expansion.

## 5. Failure containment

A broken CORS stream must not crash a cell; a broken cell must not stop other regions; a frontend outage must not stop valid NTRIP sessions; a database read problem must not silently bypass scientific integrity checks.

## 6. Canonical diagrams

See `../diagrams/01_system_context.png`, `02_live_data_flow.png`, `03_vrs_session.png`, `04_multiregion_topology.png`, `05_security_zones.png`, and `06_data_architecture.png`.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

