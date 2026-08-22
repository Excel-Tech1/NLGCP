# 01. Product and System Vision

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Purpose

This document fixes the product boundary and engineering intent for NLGCP. The platform is a GNSS correction infrastructure that combines national geodetic anchoring, local/regional CORS densification, real-time network processing, standards-compliant correction distribution, and a digital control plane for users and operators.

## 2. Problem statement

Nigeria has geodetic reference infrastructure, including NIGNET, but a national geodetic backbone and an operational centimetre-level RTK service have different density, availability, latency and integrity requirements. Long base-to-rover distances weaken conventional single-base RTK; sparse network geometry can also reduce the ability of VRS/NRTK to model local atmospheric gradients. A national service therefore needs local correction cells tied to the national reference frame rather than assuming one sparse nationwide network can provide homogeneous RTK performance.

## 3. Product definition

NLGCP shall:

1. ingest live GNSS observations from NIGNET, partner/private CORS and platform-owned CORS;
2. preserve raw RINEX/RTCM evidence and complete station metadata;
3. synchronise, quality-control and process multi-station observations;
4. provide conventional single-base RTK where technically suitable;
5. produce network/VRS corrections within validated regional cells;
6. refuse or downgrade service when integrity criteria are not satisfied;
7. encode and distribute correction streams using standard GNSS correction protocols, primarily RTCM over NTRIP;
8. expose a separate web/API control plane for users, organisations, devices, coverage, service status, subscriptions and operations;
9. preserve reproducibility so any correction session can be investigated or replayed;
10. scale from an Abuja/FCT pilot to multiple regional service cells and, ultimately, national coverage.

## 4. Product boundaries

NLGCP is **not** a GNSS receiver, satellite constellation, cadastral database, generic GIS, or web-only NTRIP proxy. The web platform must never be in the critical correction path. A website outage must not stop valid correction delivery.

## 5. Primary users

- Professional surveyors and geospatial firms.
- Construction, mining, agriculture, hydrography and infrastructure users.
- Government geodetic and mapping organisations.
- Universities and research users requiring archived GNSS observations.
- CORS partners/operators contributing stations.
- Platform network operations and GNSS integrity personnel.

## 6. Core operating principles

**Geodetic traceability.** Every station and correction cell must have coordinates, reference frame, coordinate epoch and equipment history that are auditable.

**Source independence.** Processing must not be hard-coded to one provider. NIGNET is strategically important, but the same internal observation model shall support partner and platform-owned CORS.

**Integrity before availability.** A correction stream that appears online but is scientifically unreliable is worse than a declared outage. The system shall fail closed when defined integrity checks fail.

**Local modelling, national control.** Atmospheric/network modelling occurs within validated regional cells; identity, policy, service catalogue and monitoring are nationally coordinated.

**Replayability.** Raw input, processing configuration, software versions and output metrics shall be retained sufficiently to reproduce scientific findings and diagnose incidents.

## 7. Target service modes

- **Nearest/selected single-base RTK** - short baseline service where an approved healthy physical base meets the pilot-derived distance and integrity criteria.
- **VRS/NRTK** - primary multi-station mode within validated cells.
- **Research/archive** - RINEX/metadata access subject to rights and policy.
- **Future SSR/PPP-RTK augmentation** - explicitly outside MVP, but the architecture shall avoid blocking it.

## 8. Success definition

The platform is successful when an authorised rover can connect using standard NTRIP, be routed to a valid service, receive timely corrections, achieve statistically validated positioning performance within the supported coverage area, and the operator can explain which stations, models and health states supported that solution.

## 9. Architecture invariant

```text
GNSS/CORS -> Ingestion -> Real-time bus -> QC/epoch alignment -> GNSS/NRTK engine
          -> Integrity decision -> RTCM -> NTRIP caster -> Rover

Web/API/control plane is adjacent to, not inside, the correction path.
```

## 10. Deferred, pilot-derived values

The following are intentionally not frozen until data collection and field testing: maximum single-base distance, reference-station spacing by region, correction-age threshold, residual limits, health-score weights, ambiguity validation thresholds, acceptable TTFF, and commercial service SLOs.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

