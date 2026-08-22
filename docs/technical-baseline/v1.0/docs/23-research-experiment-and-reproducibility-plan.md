# 23. Research Experiment and Reproducibility Plan

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Goal

Make every thesis result independently reproducible from preserved inputs, software and configuration.

## 2. Experiment manifest

Each experiment stores:

```yaml
experiment_id: string
research_question: string
stations: [ids]
rover_or_control: string
start: timestamp
end: timestamp
sampling_rate_hz: float
input_objects: [{uri, sha256}]
station_metadata_versions: [ids]
rtklib_build: string
pride_version: string?
custom_engine_commit: string
configuration_hash: string
precise_products: [ids]
interpolation_model: string
output_objects: [uris]
validation_metrics: object
notes: string
```

## 3. Dataset tiers

- development dataset;
- parameter-selection dataset;
- hold-out scientific validation dataset;
- operational regression corpus.

## 4. Notebooks

Jupyter notebooks are analysis/reporting interfaces, not the sole implementation of critical algorithms. Reusable computations move into versioned Python/C++ packages with tests; notebooks call those packages.

## 5. Environment capture

Record OS/container image, package lockfiles, compiler versions, RTKLIB commit/build, PRIDE PPP-AR version, exact products and configuration. PRIDE PPP-AR current repository releases are external dependencies and must be pinned per experiment.

## 6. Publication artefacts

Figures/tables are generated from stored result files using scripts. Manual editing of numeric results in Word/Excel is not permitted as the authoritative workflow.

## 7. Thesis-to-production bridge

The same `nrtk-core` model code is exercised offline against RINEX and online against normalised RTCM epochs. This prevents a disconnected “thesis algorithm” and “production algorithm”.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

