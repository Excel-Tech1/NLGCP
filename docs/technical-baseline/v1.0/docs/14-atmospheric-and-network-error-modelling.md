# 14. Atmospheric and Network Error Modelling

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Purpose

Estimate spatially varying residual errors that remain after common GNSS effects have been modelled/differenced and provide a local correction field suitable for interpolation.

## 2. Error components

The research tracks, as applicable:

- first-order ionospheric effects and local gradients;
- tropospheric zenith/path delay and gradients;
- orbit/clock residual contribution after the chosen products/models;
- multipath/noise indicators (treated primarily as local QC, not a smooth spatial field);
- unmodelled station-specific biases.

## 3. Nigerian ionosphere emphasis

Low-latitude ionospheric variability is a first-class design concern. The model therefore preserves dual-/multi-frequency observables and may derive TEC/gradient indicators. Global IGS ionosphere products may be used as context/validation, but the operational local model must be driven by the actual reference network.

## 4. Interpolation candidates

Research candidates include linear interpolation, distance-based weighting and low-order surface models. The selected operational method is chosen from measured performance across sparse/dense geometries and atmospheric regimes.

## 5. Model interface

```text
estimate_residuals(network_epoch) -> ResidualField
interpolate(residual_field, rover_position) -> LocalCorrection
quality(residual_field, rover_position) -> ModelQuality
```

The quality output is mandatory; an interpolated numeric correction without confidence/integrity context is insufficient for service delivery.

## 6. Validation

Independent rover/control data are excluded from model fitting and used to test prediction error. Results are stratified by station geometry, baseline distances, local time/season where data allow, satellite geometry and ionospheric indicators.

## 7. Configuration versioning

Every model choice, coefficient, threshold and input product is versioned. Operational changes require replay against a regression dataset before deployment.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

