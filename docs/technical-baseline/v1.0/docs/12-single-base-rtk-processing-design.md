# 12. Single-Base RTK Processing Design

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Purpose

Define the benchmark and fallback processing mode used to quantify how baseline length and atmospheric conditions affect conventional RTK in the study area.

## 2. Inputs

- physical base observations;
- base coordinates and metadata;
- rover observations or live rover measurements where available;
- navigation/ephemeris products required by the processing mode;
- processing configuration (signals, elevation mask, ambiguity policy, atmosphere models).

## 3. Core processing

RTKLIB provides standard relative-positioning mechanics. The experiment records float/fixed solution state, ambiguity validation metrics, baseline length, satellite count, PDOP, residuals, age/latency and coordinate error against control.

## 4. Baseline experiment

Test points shall cover progressively increasing distances and varied azimuths/conditions where possible. The research does not assume 10 km, 20 km or any other published rule is automatically valid in Nigeria. The output is an empirical `D_SB,max` under defined conditions and acceptance criteria.

## 5. Fallback eligibility

Operational single-base fallback requires all of:

- base `HEALTHY`;
- validated coordinate/equipment interval;
- rover inside the approved single-base region or distance policy;
- correction age and latency within current integrity limits;
- ambiguity/solution quality policy satisfied.

## 6. Metrics

Horizontal/vertical error, RMSE, 95th percentile error, fix rate, false-fix indicators, TTFF, loss-of-fix rate, recovery time and correction latency.

## 7. Reproducibility

Each run captures RTKLIB build/version, configuration, exact input hashes and control coordinates. No manually edited solution file may be used as final thesis evidence.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

