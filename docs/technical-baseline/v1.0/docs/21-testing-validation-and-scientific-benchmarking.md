# 21. Testing, Validation and Scientific Benchmarking

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Test pyramid

1. unit tests for parsing, geometry, interpolation and policy logic;
2. component tests for RTKLIB bindings/process wrappers, NATS and storage;
3. deterministic RINEX/RTCM replay tests;
4. algorithm regression datasets;
5. integration tests from ingest to caster;
6. hardware-in-loop NTRIP rover tests;
7. geodetic field validation;
8. resilience/security/load testing.

## 2. Core scientific experiment

Compare:

- uncorrected/benchmark GNSS where useful;
- single-base RTK at multiple baseline lengths;
- sparse-network VRS;
- densified local-network VRS;
- hybrid service behaviour;
- PRIDE PPP-AR/control coordinates as independent reference where appropriate.

## 3. Metrics

- East/North/height errors;
- 2D/3D RMSE and percentile errors;
- fixed-solution percentage;
- TTFF;
- false-fix indicators;
- loss-of-fix/recovery;
- residual interpolation error;
- correction/processing latency;
- service availability;
- performance during station failure/reconfiguration;
- performance stratified by ionospheric/temporal conditions.

## 4. Avoiding leakage

Rover/control data used to validate an interpolation model must not also be used to fit that model. Network configurations and parameter tuning have separate development and hold-out validation sessions where dataset size permits.

## 5. Interoperability

NTRIP/RTCM tests shall record receiver firmware, message profile, constellation settings, GGA behaviour, successful fix and observed incompatibilities.

## 6. Resilience tests

Inject station disconnect, stale stream, packet delay, metadata error, broker restart, caster failure and cell geometry reduction. The required outcome is not always “keep serving”; sometimes the correct outcome is a controlled degradation or stop.

## 7. Release gate

No production algorithm release without regression replay against the approved benchmark corpus and no new region without field acceptance against documented control.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

