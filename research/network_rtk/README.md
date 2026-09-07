# Phase 5 — Offline Network RTK Engine

## Purpose

Phase 5 establishes the scientifically rigorous, fail-closed offline
multi-reference-station processing framework required to evaluate
network-based RTK methods on the NIGNET/OSGoF dataset. It produces
admitted network experiments, deterministic geometry and overlap
assessments, independent per-baseline RTKLIB solutions (network INPUTS),
a reusable residual dataset for later Phase 6 modelling, and aggregate
metrics with honest comparisons.

Phase 5 does NOT produce atmospheric corrections (Phase 6), virtual
observations or VRS solutions (Phase 7), live RTCM/ NTRIP services, or
any new ambiguity-resolution claims.

## Architecture

```text
Phase 4 network_rtk ACCEPT sessions (qc-result.json)
        ↓  admission.py — fail-closed QC admission
station/day eligibility (admission.json)
        ↓  overlap.py — common interval from actual epochs
common observation interval (overlap.json)
        ↓  geometry.py — verified coordinates only
network station selection + geometry (geometry.json)
        ↓  reference/rover partition (experiment definition)
individual baseline solutions, REF→TEST (baselines/<id>/)
        ↓  residuals.py — per-baseline ENU residual rows
network observation/residual representation (baselines/network-residuals.csv)
        ↓  metrics.py — single-baseline vs network-input aggregates
offline network solution dataset + metrics + evidence
```

Module map (`research/network_rtk/src/nlgcp_network_rtk/`):

| Module | Responsibility |
|---|---|
| `models.py` | Experiment definition, validation, status enums |
| `admission.py` | Phase 4 QC admission, eligibility rows, fingerprints |
| `geometry.py` | Verified-coordinate geometry, baseline matrix |
| `overlap.py` | Common-epoch intersection from measured coverage |
| `baselines.py` | Per-baseline RTKLIB execution (reuses Phase 3) |
| `residuals.py` | Network residual dataset + unavailable-field log |
| `metrics.py` | Single vs aggregate metrics, nearest-vs-network comparison |
| `runner.py` | Plan/validate/run, resumability, bounded parallel execution |
| `summarize.py` | Data-root summary aggregation |
| `io.py` | Data-root resolution, atomic JSON, provenance |

## Input requirements

- `${NLGCP_DATA_ROOT}` configured and a directory.
- Phase 4 `network_rtk` QC results under
  `processed/qc/profiles/network_rtk/sessions/<year>/<station>/<doy>/qc-result.json`.
- Verified coordinates in `processed/single-base/derived-coordinates.json`
  (only `scientifically_valid` entries are used; others BLOCK).
- Converted observations referenced by the QC results and the broadcast
  navigation product referenced by the experiment definition.

## Relationship to Phase 4

Phase 5 never selects a session because a file exists. Admission requires
`network_rtk QC status == ACCEPT` unless the experiment is explicitly
labelled `diagnostic: true` (diagnostic runs are watermarked in outputs
and summaries). Rejections keep their Phase 4 reason; missing results are
`BLOCKED` with machine-readable text. Phase 4 artefacts are read, never
rewritten.

## Experiment schema

See `models.NetworkExperimentDefinition`: `experiment_id`,
`research_question`, `year`/`day_of_year`, `processing_mode`,
`reference_stations[]`, `test_station`, `navigation_products[]`,
`start_time`/`end_time`, `sampling_interval_seconds`, `coordinate_frame`,
`coordinate_epoch`, `qc_profile`, `minimum_reference_station_count`
(floor: 3, see below), `software_provenance`, `diagnostic`, `notes`.

### Minimum reference-station count

The network minimum is **3 admitted reference stations**. Three is the
smallest count that forms a triangle/polygon around or alongside a rover
and therefore the smallest geometry that can later support Phase 6
spatial error modelling. The requirement is enforced in definition
validation and recorded in every manifest. Geometry adequacy (spatial
extent, triangle area, reference-to-rover distances) is assessed
separately and may BLOCK an experiment even when the count is met. No
claim is made that any three stations are always sufficient.

## Geometry methodology

Only coordinates that passed provenance/verification gates are used
(`scientifically_valid == true` with explicit reference frame and
coordinate epoch). Mixed frames BLOCK. Outputs: ECEF station coordinates,
pairwise baseline matrix (symmetric, zero diagonal), network centroid,
reference-to-rover distances, nearest/farthest/mean reference, spatial
extent (maximum pairwise distance), triangle area for exactly three
references (Heron), baseline count. No coordinates are invented.

## Temporal overlap

Overlap is the intersection of measured per-station
(`first_epoch`, `last_epoch`) windows from Phase 4 results — never an
assumed whole-day window from a shared DOY (precedent: MGBO DOY 018 is
partial). Mixed sampling intervals BLOCK. Overlap below the minimum
duration (default 3600 s) or coverage is `BLOCKED` with reasons.

## RTKLIB processing

Source-verified `rnx2rtkp` (RTKLIB `v2.4.2-p13`, recorded SHA-256
`b4a96cd0…f7d21`) with Phase 3 configuration defaults (static, L1+L2,
GPS-only, 15° mask, continuous AR, explicit `-r` base ECEF). Each
`REF→TEST` pair runs independently with full provenance (config hash,
binary SHA, command, return code, solution metrics). Outputs are labelled
**network input/baseline solutions** — running several baselines does not
produce a network correction.

## Metrics

Per-baseline: solution status, epoch counts, FIX/FLOAT/SINGLE counts, fix
rate, TTFF if achieved, ENU residuals, horizontal/vertical/3D RMSE,
availability, baseline distance, RTKLIB config and provenance.
Network aggregates (mean RMSE, availability, FIX/FLOAT distribution,
inter-baseline consistency as the population standard deviation of
per-baseline horizontal RMSE, geometry summary) are labelled
**network-input aggregates of independent single-base solutions (NOT a
VRS solution)**. Improvement over the nearest single reference may only
be claimed where computed values support it.

## Limitations

- Real-data eligibility is whatever Phase 4 admits; as of the canonical
  2024 run only DOY 026 admits ≥3 `network_rtk` sessions
  (ABFC/EKAK/MGBO/PHRI). Other days are `BLOCKED`, which is a valid
  scientific result.
- All tested baselines to date are long (105–1029 km); FLOAT-only outcomes
  under the fixed Phase 3 configuration are expected and claimed as such.
- Satellite-level residual fields (per-satellite id, constellation,
  elevation/azimuth, common-satellite count) are unavailable from `.pos`
  outputs and recorded as null with reasons, not invented.

## Real-data availability

Run `scripts/run_network_rtk.py discover` for eligible days,
`plan`/`validate` for admission/geometry/overlap without execution, and
`run` for deterministic multi-baseline processing. Summaries land in
`processed/network-rtk/summaries/`.

## Reproducibility

Experiment fingerprints cover input hashes, QC result fingerprints,
station metadata, RTKLIB config and executable provenance, the experiment
definition, and the implementation hash. Cached results are reused only on
fingerprint match; `reused_verified_result` is recorded. Parallel workers
are bounded (≤8) and outputs are sorted by baseline id, so results do not
depend on completion order.

## Boundary between Phase 5 and Phase 6

Phase 5 stops at independent baseline inputs, residual datasets, and
aggregates. Atmospheric/spatial error interpolation, correction modelling,
VRS generation, live RTCM ingestion, and NTRIP services belong to later
phases and are not implemented here.
