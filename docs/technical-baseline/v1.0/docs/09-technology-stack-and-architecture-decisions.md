# 09. Technology Stack and Architecture Decisions

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Locked stack baseline

| Concern | Baseline |
|---|---|
| GNSS real-time core | RTKLIB + custom C/C++ |
| Precise offline validation | PRIDE PPP-AR |
| Research/model development | Python 3, NumPy, SciPy, pandas, pyproj, GeoPandas, matplotlib/Jupyter |
| Stream ingestion | Go |
| Internal real-time messaging | NATS + JetStream |
| Cache/session state | Redis |
| Structured/spatial DB | PostgreSQL 18 + PostGIS |
| Raw/large artefacts | S3-compatible object storage; MinIO for pilot |
| Platform backend | FastAPI + Pydantic |
| Web frontend | Next.js + TypeScript + MapLibre GL |
| Correction distribution | RTCM 3.x over NTRIP v2-compatible caster tier |
| Monitoring | Prometheus + Grafana + Alertmanager |
| Containers | Docker; Docker Compose for pilot |
| National orchestration | Kubernetes only when multi-node operational scale justifies it |
| OS | Ubuntu Linux LTS-class server environment |
| CI/CD | GitHub Actions or equivalent controlled pipeline |

## 2. Why RTKLIB + custom code

RTKLIB provides tested GNSS primitives, real-time stream handling and RTK workflows. It is not treated as the finished NRTK product; the custom engine owns the thesis-specific network residual, VRS and integrity logic.

## 3. Why PRIDE PPP-AR

PRIDE PPP-AR is an independent precise-processing tool for station coordinates, long-session reference solutions and validation. It remains outside the per-epoch correction serving path.

## 4. Why Go for ingress

Ingestion is I/O-bound, connection-heavy and long-lived. Go offers a simple concurrency/runtime model and static deployment while keeping GNSS computation in C/C++ and scientific experiments in Python.

## 5. Why NATS JetStream

The platform needs low-latency fan-out, persistence/replay and independent consumers for processing, archive writing and monitoring. NATS subjects also create a clean boundary between station ingestion and downstream algorithms.

## 6. Why PostgreSQL/PostGIS

Station metadata, service cells, entitlement and audit state are relational; service routing is spatial. One mature relational database plus PostGIS reduces complexity versus separate GIS and transactional databases.

## 7. Explicit non-selections for MVP

- Kafka: unnecessary operational weight for initial station counts.
- Kubernetes in pilot: delays research without solving a demonstrated scaling problem.
- Machine learning in core corrections: classical geodetic models must be established first.
- Custom NTRIP protocol: interoperability risk; use standard clients/casters.
- Raw observations in PostgreSQL: wrong storage/access pattern at scale.

## 8. ADR rule

Any replacement of a locked baseline above requires an ADR containing problem, alternatives, evidence, migration impact, scientific-validation impact and rollback plan.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

