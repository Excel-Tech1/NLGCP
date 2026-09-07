# NLGCP Phase 6 — Atmospheric & Spatial Error Model

Phase 6 estimates and models the spatially correlated GNSS error field across
an admitted reference-station network. It prepares the correction model that
Phase 7 (VRS) will consume. Phase 6 does **not** generate a VRS.

## Scientific boundary

Phase 6 distinguishes, where the observations permit:

```text
ionospheric contribution
tropospheric contribution
orbit/clock/common-mode contribution
station-dependent residual contribution
measurement noise/multipath
```

Where components cannot be independently estimated, results use honest labels:

```text
combined spatially correlated residual
differential residual proxy
estimated spatial correction term
arc-detrended geometry-free residual proxy
```

Position-domain RMSE from Phase 5 `.pos` outputs is **never** treated as an
atmospheric correction observable. Satellite-level observables are extracted
from RINEX observation files (RINEX 2.11 in the 2024 archive); RTKLIB `.pos`
files provide only position-domain network inputs.

## Pipeline

```text
Phase 4 QC-qualified station-days
        ↓
Phase 5 admitted network experiment (admission.json reused by fingerprint)
        ↓
RINEX observation extraction (observations.py)
        ↓
common satellites and epochs (common-observation engine)
        ↓
measurement combinations (combinations.py: GF, SD, DD)
        ↓
ionospheric proxies (ionosphere.py) + tropospheric a priori (troposphere.py)
        ↓
spatial records (spatial.py)
        ↓
interpolation candidates (interpolation.py: zero/nearest/IDW/planar)
        ↓
leave-one-out cross-validation (validation.py)
        ↓
Phase 7-ready correction representation (models/ + validation/)
```

## Status model

Every derived stage reports one of `COMPLETE`, `PARTIAL`, or `BLOCKED` with
explicit reasons. If satellite-level extraction is impossible, real
atmospheric modelling is marked `BLOCKED` (fail-closed); the interpolation
and validation interfaces are then exercised on synthetic fixtures labelled
`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`.

## Layout

```text
research/atmospheric_spatial_model/
  README.md
  config/phase6-pilot-net-2024d026.json
  src/nlgcp_atmospheric_model/  (models, observations, combinations,
    satellite_geometry, ionosphere, troposphere, spatial, interpolation,
    validation, metrics, provenance, pipeline)
  tests/  (synthetic-only unless a test reads versioned fixtures)
```

CLI: `scripts/run_atmospheric_model.py` (`inspect`, `plan`, `derive`, `fit`,
`validate`, `summarize`, each with `--dry-run`).

Outputs (outside Git): `${NLGCP_DATA_ROOT}/processed/atmospheric-model/`.

Per experiment: `definition.json`, `admission.json`, `derive-status.json`
(fingerprint-gated), `common-observations/` (discovery, per-epoch common
counts), `ionosphere/` (`station-gf.csv` arc-annotated station series,
`pair-sd.csv` single-differenced proxies), `troposphere/` (a priori
slants, geometry exclusions), `residuals/spatial-records.csv`
(datum-anchored differential field, datum self-differences identically
zero), `models/target-predictions.csv` (target excluded from its own
reference set), `validation/loocv.json` (identical-sample ranking),
`tables/` (baseline matrix, LOOCV summary, decorrelation) and `figures/`
(reproducibly generated PNGs). Cross-experiment `summaries/*.csv` are
written by the `summarize` command.

## References

See `docs/phase6-atmospheric-spatial-model.md` for the observation model,
equations, symbols, units, frames, assumptions, and literature sources.
