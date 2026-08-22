# 07. Data Architecture and Database Design

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Storage principle

Different data classes have different access patterns. The architecture deliberately avoids forcing raw GNSS measurements, relational metadata and sub-second live state into one database.

## 2. Stores

### PostgreSQL + PostGIS

Authoritative structured state:

- stations and providers;
- equipment/coordinate history;
- service cells and polygons;
- users, organisations, devices and entitlements;
- mountpoints;
- experiments/configurations;
- correction sessions and summary metrics;
- incidents, maintenance and audit events.

### Object storage (S3-compatible / MinIO in pilot)

Immutable/large artefacts:

- RINEX;
- raw RTCM recordings;
- navigation files;
- SP3/CLK/SINEX/IONEX and precise products;
- processed research datasets;
- experiment output bundles;
- diagnostic artefacts.

### NATS JetStream

Real-time ordered event transport and short-duration replay for observation and operational streams.

### Redis

Short-lived cache/session/rate-limit state only. Redis is not the source of truth for geodetic metadata or raw observations.

## 3. Core relational entities

```text
Provider 1---* Station 1---* EquipmentInterval
                    | 1---* CoordinateInterval
                    | *---* ServiceCell (membership)
                    | 1---* StreamEndpoint
                    | 1---* StationHealthSample

Organisation 1---* User
Organisation 1---* Device
Device       1---* CorrectionSession
ServicePlan  *---* Entitlement
Mountpoint   *---1 ServiceCell
```

## 4. Spatial functions

PostGIS is required for:

- point-in-service-polygon routing;
- nearest eligible station queries;
- station-baseline distance calculations;
- network convex-hull/geometry analysis;
- coverage and overlap maps;
- location-based reporting without embedding geometry logic in frontend code.

## 5. Retention

Retention periods are policy decisions, but raw research data supporting published thesis results shall be preserved with reproducibility metadata. Operational session detail may use tiered retention. Personally linked rover tracks must have stricter privacy retention than scientific station observations.

## 6. Data lineage

Every derived correction/research product should be traceable to:

`input object hashes -> station metadata versions -> processing configuration -> software build -> output hash -> validation metrics`.

This chain is essential for incident analysis and academic reproducibility.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

