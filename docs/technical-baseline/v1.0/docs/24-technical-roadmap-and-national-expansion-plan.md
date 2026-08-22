# 24. Technical Roadmap and National Expansion Plan

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Generation 0 - Scientific baseline

- acquire/audit candidate NIGNET/partner/IGS data;
- install RTKLIB and PRIDE PPP-AR workflows;
- create station registry and immutable raw archive;
- reproduce single-base solutions;
- establish precise station/control coordinates.

**Exit:** reproducible offline GNSS environment and validated datasets.

## 2. Generation 1 - Offline NRTK prototype

- multi-station epoch synchronisation;
- QC/station health offline;
- network ambiguity/residual extraction;
- candidate interpolation models;
- VRS generation/replay;
- sparse vs dense network experiments.

**Exit:** thesis model demonstrates measurable improvement/limits with hold-out validation.

## 3. Generation 2 - Real-time replay platform

- Go ingestion abstraction;
- NATS JetStream;
- recorded RTCM real-time replay;
- live processing timings;
- RTCM output and lab NTRIP caster;
- end-to-end observability.

**Exit:** deterministic live-like pipeline without dependency on continuous external CORS availability.

## 4. Generation 3 - FCT live pilot

- commissioned local stations/partners;
- live ingestion;
- VRS and approved single-base mountpoints;
- real survey rover testing;
- operator dashboard;
- authentication/device entitlements;
- measured SLOs and runbooks.

**Exit:** limited production pilot accepted against accuracy, latency and resilience criteria.

## 5. Generation 4 - Multi-city platform

Add cells based on demand, existing CORS, geodetic significance, communications and ability to achieve validated geometry. National control plane manages common users, devices, policy and monitoring.

## 6. Generation 5 - National correction infrastructure

- regional processing redundancy;
- multiple edge/caster locations;
- standardised CORS commissioning;
- institutional partnerships;
- formal service-level commitments;
- disaster recovery;
- mature security/operations;
- possible new SSR/PPP-RTK service family after independent research/validation.

## 7. Expansion gate for every region

A city/state is not declared covered because a station exists. Required evidence:

1. source/rights audit;
2. validated station coordinates/metadata;
3. sufficient healthy geometry;
4. offline replay acceptance;
5. live latency/stability acceptance;
6. rover/control field acceptance;
7. operations/support readiness;
8. published service polygon and limitations.

## 8. Documentation completion definition

This baseline closes **system architecture and documentation design**. Work remaining after this point is implementation, data acquisition, parameter calibration, field validation and change-controlled refinement - not foundational redesign unless evidence forces an ADR.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

