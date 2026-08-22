# 13. Network RTK and Ambiguity Processing

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Goal

Create a stable common ambiguity/network state from multiple reference stations before spatial corrections are interpolated to a rover.

## 2. Network preparation

1. select eligible stations in the chosen service cell;
2. verify common epoch/satellite/signal availability;
3. choose reference station/satellite strategies according to algorithm configuration;
4. form inter-station baselines/observation differences;
5. detect slips/outliers before ambiguity use;
6. estimate ambiguity candidates;
7. validate integer solution;
8. generate network residuals only from accepted states.

## 3. Ambiguity policy

The project may use LAMBDA/MLAMBDA-compatible integer least-squares methods through established GNSS code. Fixed ambiguities are never accepted solely because an algorithm returned integers; validation metrics and residual behaviour are required.

## 4. Network reconfiguration

Station loss changes the geometry and possibly ambiguity state. The engine shall treat a topology change as a controlled state transition. A session may continue only if the remaining network is validated and the integrity engine permits it.

## 5. Sparse-network experiment

The research shall deliberately process subsets with increasing inter-station separation. This quantifies how residual interpolation and ambiguity robustness deteriorate or remain stable under sparse geometry.

## 6. Outputs

- station/network ambiguity state;
- satellite/signal residual field inputs;
- covariance/quality indicators where available;
- topology and station set used;
- state transition events;
- integrity summary consumed by the VRS engine.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

