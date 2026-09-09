# Phase 6 Pilot Evidence — `atm-2024d026-phri-target-geometry-v3` (AUTHORITATIVE)

> SUPERSESSION NOTICE: the original pilot record under
> `atm-2024d026-phri-target` (quoted zero RMSE 2.984 m, n = 17768) is
> SUPERSEDED as current evidence. Those figures are corroborated by the
> byte-verified pre-refresh summary snapshots in
> `research/scientific_validation/evidence/historical-summaries/` and are
> retained there as labelled history. The authoritative reviewed evidence is
> `atm-2024d026-phri-target-geometry-v3`, regenerated after the Phase 6/7
> scientific-validation sprint corrected 13 geometry/science defects
> (see `docs/phase6-7-scientific-validation.md`). Frozen pre-review hashes of
> the old outputs are preserved in
> `research/scientific_validation/evidence/before-review.json`.

Real-data pilot on the Phase 5 DOY 026 admitted network
(`net-2024d026-phri-rover`): references ABFC00NGA / EKAK00NGA / MGBO00NGA,
target PHRI00NGA. Epoch stride 6 (180 s effective sampling).

## Status

```text
derive    COMPLETE (satellite-derived proxies; no position-RMSE substitution)
fit       COMPLETE (predictions of differential proxies at target; not VRS)
validate  COMPLETE (leave-one-out on identical comparison samples)
```

Real-data atmospheric modelling: **COMPLETE at pilot scope** (one day,
four stations). National/general claims: **explicitly NOT made**.

## Observable audit (RINEX extraction, not `.pos`)

RTKLIB `.pos` files provide position-domain residuals only
(`pos_satellite_fields_available: false`). Satellite observables come
from the RINEX 2.11 observation files via `observations.py`:

```text
common observation codes: C1 L1 L2 P1 P2 (GPS L1/L2 compatible: true)
common epochs (all 4 stations): 480 of 480 kept (stride 6 of 30 s)
common satellites per epoch: median 16, minimum 12
GPS L1/L2 common per epoch: median 9, minimum 7
usable epochs: 100% (480/480)
constellation appearances: GPS 4498, SBAS/R 3122 (non-GPS excluded from GF)
```

L1/L2 cycle ratio verified physical (≈1.2834 = f1/f2) on every station
after the blank-line alignment fix (see §Failure modes below).

## Ionospheric proxies (GPS L1/L2 geometry-free, arc-detrended SD)

```text
ABFC-EKAK  487.636 km  5069 samples  COMPLETE
ABFC-MGBO  689.687 km  5198 samples  COMPLETE
ABFC-PHRI  470.870 km  4506 samples  COMPLETE
EKAK-MGBO  979.075 km  4879 samples  COMPLETE
EKAK-PHRI  105.553 km  4474 samples  COMPLETE
MGBO-PHRI 1029.034 km  4474 samples  COMPLETE
pair-SD value range: -24.4 … +25.1 m, mean +0.10 m, RMS 4.18 m (28600 rows)
```

Labelled `GF_SD_ARC_DETRENDED` (differential residual proxy, slant-L1
variation in m + first-order TECU). Never labelled absolute TEC.

## Tropospheric a priori chain

Standard-atmosphere only (no station meteorology; labelled "not measured
station meteorology"): Berg (1948) pressure, Saastamoinen (1972) ZHD,
0.12 m exponential ZWD default, Niell (1996) mapping, 10° mask, GPS
broadcast ephemeris (`BRDC00IGS_R_20240260000_01D_MN.rnx.gz`,
SHA-256 `a6418387…`, hash match true):

```text
troposphere COMPLETE, 17984 a priori slant terms, 0 geometry exclusions
```

## Spatial records and fit

```text
spatial records: 17119 (independent station fields; fold-local reference datum)
target predictions: 17696 total, 17247 fitted (zero/nearest/IDW/planar)
```

Target-fit reference sets exclude the target's own record (no leakage).

## Leave-one-out cross-validation (identical samples, n = 15948)

| model   | RMSE (m) | MAE (m) | pred–obs corr | coverage ±0.05 m |
|---|---|---|---|---|
| zero    | 3.076 | 2.012 | — | 0.021 |
| idw     | 3.352 | 2.036 | 0.282 | 0.042 |
| nearest | 3.757 | 2.298 | 0.234 | 0.041 |
| planar  | 14.373 | 6.565 | 0.013 | 0.032 |

Best model: **zero** — no spatial interpolator beats the zero-correction
control on this sparse network (3 references over 105–1029 km). **All four
held-out target rotations are extrapolation cases** (barycentric
point-in-triangle containment: every target lies outside its reference
triangle), so planar extrapolation failure is expected, not anomalous.
Simpler winners reported, not hidden.

## Distance / decorrelation (pilot evidence only)

Pair SD-proxy RMS vs baseline: slope **+0.000591 m/km** (0.591 mm/km),
correlation 0.48, 6 pairs (105 km → 4.19 m RMS; 1029 km → 4.64 m RMS).
Weak positive distance dependence. **Not a national decorrelation law:**
one day, six pairs.

## Failure modes found and fixed during this pilot

1. RINEX parser skipped blank lines inside satellite blocks,
   desynchronising all later records (L1/L2 misassigned, 1e7 m garbage).
   Fixed: exact line consumption; regression test with 14-code blocks.
2. Stride-unaware arc gap test shredded decimated series into singleton
   arcs. Fixed: effective step (`interval x stride`); gaps open new arcs.
3. Nonzero-LLI splits shredded PHRI (static L2 LLI=4 converter
   annotation). Fixed: arcs split on LLI *changes*; evidence recorded
   (full-cycle header, f1/f2 ratio, smooth GF).
4. Fit included the target's own value as a reference (distance-zero
   leakage). Fixed: references restricted to reference stations.
5. Datum-target LOOCV fold had no observed values. Fixed: datum
   self-difference zero records anchor the field.
6. Model ranking compared non-identical samples. Fixed: identical-sample
   comparison with per-model evaluable counts reported.

Buggy-run outputs were deleted and regenerated; fingerprints
(`derive_key 47ca5400…`, code `b8fb8184…`) invalidate the old products.

## Scientific-validation sprint defects (corrected in geometry-v3)

The 2026-09-09 review corrected 13 further defects; full record in
`docs/phase6-7-scientific-validation.md` and
`docs/phase6-7-equation-traceability.md`:

1. Earth rotation rate factor-100 error (7.29e-07 → 7.2921151467e-05 rad/s).
2. RINEX broadcast angles/rates wrongly scaled by π (RINEX stores radians).
3. +18 s UTC leap offset applied to GPS-time labels (removed).
4. `toe_week` derived by rounding instead of reading the week field.
5. No ephemeris health/age screening (unhealthy/stale excluded beyond 7201 s).
6. Nav parser dropped records with blank trailing spares (fixed-width reader).
7. Geocentric latitude in ENU/elevation (→ geodetic).
8. Bounding-circle containment (→ barycentric point-in-triangle; all folds
   proven EXTRAPOLATION).
9. Unscaled normal-equation plane fit (→ scaled SVD with conditioning guard).
10. GF→L1 sign error (−1/(γ−1) → +1/(γ−1)).
11. Niell coefficient/hemisphere/height errors (transcribed from pinned RTKLIB).
12. Fixed global datum with zero self-differences (→ independent station
    fields with fold-local reference datum; no target leakage).
13. Epoch-flag/LLI/GPS-system handling gaps (flags 2/3/5 excluded, half-cycle
    arcs split, GPS time-system enforced).

Corrected derive fingerprint: `derive_key c88893e2…` (geometry-v3).

## Phase 7 interface

Phase 7 consumes `models/target-predictions.csv` (IDW/planar fields at
PHRI), `validation/loocv.json` (winner: zero control — i.e. no
interpolator earned its place yet), `tables/` + `figures/`, and the
COMPLETE/PARTIAL/BLOCKED status contract. The consumed source is the
reviewed `atm-2024d026-phri-target-geometry-v3` experiment. VRS synthesis
is out of scope here and was not performed.

Full outputs (outside Git):

```text
${NLGCP_DATA_ROOT}/processed/atmospheric-model/experiments/atm-2024d026-phri-target-geometry-v3/
${NLGCP_DATA_ROOT}/processed/atmospheric-model/summaries/
```

Historical note: `${NLGCP_DATA_ROOT}/processed/atmospheric-model/experiments/atm-2024d026-phri-target/`
is SUPERSEDED (see notice at top; frozen hashes in
`research/scientific_validation/evidence/before-review.json`).
