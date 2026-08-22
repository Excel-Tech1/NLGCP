# 20. Observability, Monitoring and Service-Level Objectives

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Principle

Operational health combines **IT health** and **GNSS scientific health**. CPU usage alone cannot tell whether an RTK correction is trustworthy.

## 2. Metrics

### Station/ingest
connection state, RTCM byte/message rate, GNSS epoch age, arrival latency, gap rate, reconnect count.

### GNSS quality
satellite count by constellation, C/N0 summaries, cycle-slip indicators, residual statistics, ambiguity/network state, station health.

### Processing
aligned epochs/s, queue lag, processing duration, model residual quality, VRS generation duration, mode transitions.

### Distribution
caster connections, mountpoint availability, output bytes/s, client errors, correction age at publish time where measurable.

### Platform
API latency/errors, database health, NATS health, Redis health, object-store errors, authentication failures.

## 3. Tooling

Prometheus scrapes metrics; Grafana provides operator dashboards; Alertmanager routes actionable alerts. Logs are structured and correlated by station/session/request IDs. Distributed tracing may be added for control-plane/API paths; the GNSS real-time path relies primarily on timestamped stage metrics and structured events.

## 4. SLO model

Define SLOs for:

- correction service availability by region;
- maximum correction/data age;
- processing latency percentile;
- eligible station availability;
- caster connection success;
- incident acknowledgement/recovery;
- scientific performance indicators (fix rate/accuracy) as validated service commitments.

Numeric values are pilot-derived. They shall be established from field evidence and receiver/mobile-network behaviour, then versioned by service tier.

## 5. Alerts

Alerts must represent user/scientific impact, not every metric fluctuation. Examples: cell loses minimum healthy geometry, stale RTCM from a contributing station, residual field exceeds threshold, correction publisher lag threatens age budget, caster service unavailable.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

