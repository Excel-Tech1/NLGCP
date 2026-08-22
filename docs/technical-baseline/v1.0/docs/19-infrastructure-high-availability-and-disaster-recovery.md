# 19. Infrastructure, High Availability and Disaster Recovery

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Environments

- **Research workstation/lab:** local RINEX replay, Jupyter, RTKLIB, PRIDE.
- **Pilot:** Docker Compose on hardened Ubuntu server(s), 2-5+ CORS, one service cell, non-critical users.
- **Production regional:** redundant ingest/process/caster nodes, replicated messaging and database, independent monitoring.
- **National:** multiple regional processing domains with national control-plane services and disaster-recovery capacity.

## 2. High availability

Production targets remove single points from the correction path:

- at least two public caster instances;
- multiple GNSS processing workers where state model permits;
- NATS clustered/replicated streams;
- PostgreSQL HA with tested failover;
- redundant Internet/power for critical CORS where feasible;
- immutable off-node backups;
- object storage replication/versioning according to deployment tier.

## 3. Kubernetes decision

Kubernetes is not required for the research/pilot. It becomes justified when multiple regions, rolling updates, node failure handling and standardised multi-service deployment outweigh its operational complexity.

## 4. DR objectives

RPO/RTO values are defined per data class after pilot operational analysis. Geodetic metadata/configuration require much stricter recovery protection than disposable UI cache. Raw thesis datasets should have zero intentional data loss through independent backup.

## 5. Failure scenarios

- caster host failure;
- processing node failure;
- broker quorum issue;
- database primary failure;
- object store failure;
- whole regional site outage;
- upstream NIGNET/partner outage;
- mobile carrier degradation;
- DNS/certificate failure.

Each scenario has a detection signal, automatic response where safe, operator runbook and post-recovery validation.

## 6. Backup

Nightly/continuous database strategy as deployment requires; object-store versioning/replication; encrypted offsite configuration backup; regular restore drills. A backup that has not been restored in a test is not considered operationally verified.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

