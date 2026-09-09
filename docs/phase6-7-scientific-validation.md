# NLGCP Phase 6/7 Scientific Validation & Geometry Hardening — Review Record

Branch: `phase67/scientific-validation-geometry-hardening` (from `phase7/vrs-generator` @ `59c986a`).
Date: 2026-09-09. Data root: `/home/excellence/nlgcp-data` (outside Git).
Scope: DOY 2024/026, stations ABFC00NGA / EKAK00NGA / MGBO00NGA / PHRI00NGA, frame IGS20.

This sprint validates; it does not develop features, does not promote any spatial
model, does not implement RINEX export/RTCM/NTRIP/positioning, and does not start Phase 8.

## 1. Review objective

Phase 7 found potential Phase 6 geometry defects (radians handling, GPST handling).
Determine from code and regenerated evidence which components were wrong, fix them,
regenerate affected evidence under segregated IDs, and decide whether Phase 7 may merge.

## 2. Original concern (confirmed and extended)

The concern was correct: Phase 6 satellite geometry was unusable as implemented
(orbit errors at the kilometre scale from three compounding bugs). The audit found
nine further defects in spatial/interpolation/validation layers. Baseline chord
lengths themselves were always correct; the errors were in orbit propagation,
local-frame construction, containment classification, the ionospheric sign, the
Niell mapping, and LOOCV datum handling.

## 3. Geometry audit (all PASS after correction)

- **Coordinate provenance.** All four stations: IGS20, epoch 2024-01-26T11:59:42Z,
  PRIDE PPP-AR daily solutions, per-file SHA-256 re-verified against
  `processed/single-base/derived-coordinates.json`. RINEX approximate coordinates
  never admitted. Status: VERIFIED. Admission now additionally enforces
  `scientifically_valid`, frame/epoch match, pos-file hash, RINEX hash, and finite
  coordinates (fail-closed).
- **ECEF chord distances (two independent norms: `math.dist` vs NumPy).**
  All six pairs agree to ≤1.2e-10 m with the historical Phase 5 matrix — historical
  values stand, unchanged:
  ABFC–EKAK 487.636 km; ABFC–MGBO 689.687 km; ABFC–PHRI 470.870 km;
  EKAK–MGBO 979.075 km; EKAK–PHRI 105.553 km; MGBO–PHRI 1029.034 km.
- **Geodesic surface distances** (PROJ `geod`, WGS84 ellipsoidal inverse) recorded
  beside chords, e.g. EKAK–PHRI 105.553 km surface vs 105.553 km chord;
  MGBO–PHRI 1030.129 km surface vs 1029.034 km chord. Chord (3-D marker separation
  including height) and geodesic (surface distance, heights excluded) differ by
  construction; they must never be interchanged.
- **ECEF→geodetic.** Cross-checked against an independent native build of pinned
  RTKLIB `ecef2pos` (v2.4.2-p13): latitude/longitude agree to <1e-8 deg, height to
  <1e-3 m for all four stations. Pole/centre/non-finite handling corrected and tested.
- **ECEF→ENU.** Previous code used geocentric latitude; corrected to geodetic
  (ellipsoidal-normal) latitude. Tilt error up to ~0.08° over Nigeria is removed.
- **Centroid/frame.** Each interpolation fit uses one shared origin: the ECEF
  centroid of the *usable* references only (held-out target excluded), converted to
  geodetic for the ENU rotation. Target and references share the frame. Verified per
  rotation in `geometry-audit.json`.
- **Reference triangles (common-ENU planar areas).**
  PHRI-held-out 156408.2 km²; EKAK 134567.6 km²; ABFC 46557.6 km²; MGBO 24818.3 km².
  Historical Phase 5 Heron (3-D chord-triangle) areas differ by ≤0.25% — a different
  area definition, not a numerical error; both retained with labels.
- **Target containment (corrected classifier: barycentric point-in-triangle,
  tol 1e-9; degenerate triangles count as extrapolation).**
  ALL FOUR rotations are OUTSIDE (EXTRAPOLATION). The old bounding-circle test
  misclassified three of them as inside. Barycentric weights recorded per rotation.
  Aspect ratios (longest-edge²/2·area): ABFC 2.9, EKAK 1.3, MGBO 2.4, PHRI 1.1 —
  no degeneracy, but every prediction is an extrapolation, which explains the planar
  failure and tempers any interpolation expectation on this network.
- **Satellite geometry.** 16 real satellite/epoch comparisons against an independent
  native RTKLIB `eph2pos` parse/propagation agree to <6.4e-8 m. Niell mapping:
  48 native cross-checks agree to <1e-12.

## 4. Bugs found (13, all fixed with regression tests)

Phase 6 / shared:
1. Earth rotation rate 7.2921151467e-07 (factor-100 error) → corrected to
   7.2921151467e-05 rad/s (RTKLIB `OMGE`).
2. Seven RINEX broadcast fields multiplied by π (semicircle assumption) → identity;
   RINEX stores radians (verified: raw i0 = 0.9905 rad = 56.7°).
3. +18 s UTC leap offset added to GPS-time labels → removed (headers declare GPS).
4. `toe_week` derived by rounding instead of reading the week-number field.
5. No ephemeris health/age screening → unhealthy/stale records excluded (>7201 s).
6. Orbit-line tokenizer silently dropped records with blank trailing spares → fixed
   19-column field reader with optional-spares handling.
7. Geocentric latitude in ENU rotation and elevation/azimuth → geodetic.
8. Bounding-circle containment → barycentric point-in-triangle; degenerate guard.
9. Plane fit via unscaled normal equations → scaled SVD with rank/condition
   diagnostics; singular/ill-conditioned (cond ≥ 1/sqrt(eps)) planes refused.
10. GF→L1 sign: factor was −1/(γ−1); carrier GF = (γ−1)·I1, so +1/(γ−1).
11. Niell coefficients: wrong table entries, stepwise bins, missing southern-hemisphere
    seasonal shift, height correction, and fixed wet coefficients → transcribed from
    pinned RTKLIB `nmf`, 48/48 cross-checks pass.
12. Datum leakage: a fixed global datum with identically-zero self-difference records
    made the datum fold unevaluable-or-trivially-zero and mixed I vs I+T estimands →
    independent per-station fields (`station-fields.csv`, uniform field kind) with a
    fold-local lexical-first-reference datum applied identically to target and
    references in `run_loocv(reference_datum=True)`. Target perturbation cannot
    change its own predictors (tested).
13. Epoch-flag/LLI handling: epoch flags 2/3/5 now excluded (event-count lines are not
    satellites); LLI bit-2 (half-cycle ambiguity) opens new arcs; nonzero LLI bits
    force arc segmentation. RINEX time-system header must read GPS. Non-finite
    observations/coordinates rejected.

Bugs not found (verified correct as committed): baseline chord computation, RINEX
blank-line structural parsing, stride-aware gap handling, GF combination form
(L1·λ1 − L2·λ2), TECU scaling convention, Saastamoinen ZHD equation, IDW normalisation
mathematics (rescaled to overflow-safe equivalent form), VRS native geometric
transformation and Sagnac treatment, anchor-selection ordering.

## 5. Corrected methodology (what changed in the pipeline)

- Derive emits independent station fields with one uniform estimand per experiment
  (IONO_VARIATION_PLUS_APRIORI_TROPO when tropo COMPLETE, else IONO_VARIATION_ONLY);
  legacy `DD_DETRENDED_METHOD` wording retired as imprecise (single differences of
  separately arc-detrended series, not double differences).
- Validate builds fold-local datums; writes `validation/comparison-samples.csv`;
  per-fold model metrics recorded; identical-sample ranking retained.
- Fingerprints cover coordinates, admission, inputs, nav hash, and derived-product
  checksums; downstream stages refuse stale/modified derivatives (`verify_derived`).
- Epoch ISO labels no longer carry a misleading `+00:00` UTC suffix (labels are GPST).

## 6. Old vs corrected Phase 6 (frozen reproduction → geometry-v3)

Full table: `research/scientific_validation/evidence/old-vs-corrected.csv`.
n = 13326 → 15948 identical comparison samples (all four folds evaluable now;
previously the ABFC fold evaluated 0).

| model | previous RMSE | corrected RMSE | Δ | ranking |
|---|---|---|---|---|
| zero | 3.546 m | 3.076 m | −0.470 m (−13.3%) | best (unchanged) |
| IDW (p=2) | 3.887 m | 3.352 m | −0.536 m (−13.8%) | 2nd (unchanged) |
| nearest | 3.985 m | 3.757 m | −0.228 m (−5.7%) | 3rd (unchanged) |
| planar | 15.721 m | 14.373 m | −1.348 m (−8.6%) | last (unchanged) |

Decorrelation slope 0.591014 → 0.591010 mm/km (unchanged; pilot-only, 6 pairs).
Baseline chords, pair-SD RMS, and common-epoch structure essentially unchanged —
the orbit fixes move mapping/elevation terms, not the differential observables at
this day's geometry. Conclusion revalidated: **no interpolator beats the zero
control**, now on a larger evaluable sample and with all folds proven extrapolated.
Spatial records 20187 → 17119 (uniform-estimand support); tropo terms 17207 → 17984
with geometry exclusions 480 → 0 under corrected elevations at the 10° mask.

Provenance incident (recorded, not hidden): the old pilot directory was re-run
under its own ID on 2026-09-08 ~14:10 local, after the 13:37 freeze inventory
(9 files changed; derivation/validation outputs only — summaries untouched).
Changed-in-place files are listed in `corrected-results.json`
(`historical_preservation.changed_old_experiment_rerun`); frozen hashes in
`before-review.json` remain the authoritative historical record. The documented
pilot figures (zero 2.984 m, n = 17768) are corroborated by the byte-verified
pre-refresh summary snapshots in `research/scientific_validation/evidence/`
`historical-summaries/` and reappear as `.original_pilot` rows in
`old-vs-corrected.csv`; they are SUPERSEDED as current evidence, not orphaned.
The `previous` column of the main comparison is the post-freeze reproduction
(zero 3.546 m, n = 13326).

## 7. Phase 7 audit

- **Geometric transformation:** PASS. Native adapter unchanged; equation
  P_v = P_a + Δg, L_v = L_a + Δg/λ with Δg = (ρ_v − ρ_a) − c·Δdt_s verified by
  existing analytic tests; VRS observation/geometry columns bit-identical v2→v3
  for all four rotations (only virtual IDs/provenance differ), metrics exactly equal.
- **Target leakage:** PASS. `held_out_observations_used_in_synthesis=false` in all
  four validations; target files consumed only by validation; new tests attempt
  leakage (target-as-reference, target-anchored synthesis) and verify refusal.
- **Anchors (corrected chords, unchanged selections):**
  PHRI→EKAK 105.553 km; EKAK→PHRI 105.553 km; ABFC→PHRI 470.870 km;
  MGBO→ABFC 689.687 km. Nearest-by-chord with lexical tie-break; reason recorded.
- **Correction mode:** ZERO / VRS_GEOMETRY_ONLY retained (zero won revalidation;
  no promotion criteria met or invented).
- **Regenerated:** all four rotations as `*-geometry-v3` (+ fresh replay of Phase 6
  proving deterministic numerics: 7/7 product files bit-identical, LOOCV equal).
  Virtual observations: PHRI 24556, ABFC 17764, EKAK 17847, MGBO 17893;
  total 78060. Each rotation: 480/480 epochs, 30 GPS satellites.
- **Corrected PHRI diagnostics (unchanged by construction):**
  C1 clock-adjusted RMSE 0.597 m (n=4471), P2 0.768 m (n=4422);
  L1 TD-DD RMSE 2.087 m (n=3843), L2 3.202 m (n=3809). Diagnostic residuals,
  not positioning errors. EKAK shows the expected near-reciprocal values
  (C1 0.597372 vs 0.597398 m; opposite-sign carrier biases) — verified distinct
  artifacts, not duplication.
- **Positioning validation:** NOT PERFORMED (RINEX export deferred; documented blocker:
  export format/ambiguity handling not yet certified). **RINEX export:** not ready;
  no RTCM implemented.

## 8. Equation traceability

`docs/phase6-7-equation-traceability.md`: 30 calculations traced to
source/variables/units/conventions/assumptions/code/tests.
Two legacy attributions marked REFERENCE REVIEW REQUIRED (exact 40.308 TEC
coefficient source; "Berg 1948" pressure provenance — equation retained as
repository standard-atmosphere approximation). No citations invented.

## 9. Numerical stability

Scaled-SVD plane diagnostics with 1/sqrt(eps) conditioning guard; IDW rescaled to
overflow-safe equivalent weights; exact-coincidence and non-finite guards;
Kepler non-convergence raises; degenerate-triangle extrapolation forcing;
barycentric tolerance scaled by triangle size. Fail-closed throughout.

## 10. Tests

Repo total 319 → **355 Python tests, all pass**; `make check` (Ruff, mypy strict on
108+ files, pytest, Go, CTest, ESLint, tsc, Next.js build) EXIT 0 with
`RTKLIB_SOURCE=/home/excellence/RTKLIB`.
New: 14 geometry-hardening + 11 scientific-review Phase 6 tests; +5 Phase 7
leakage/admission tests (79 pass with RTKLIB source; 6 native checks skip without it).
No existing test weakened. All Phase 1–5 tests green.

## 11. Evidence status

- VERIFIED: baseline matrix, coordinates/provenance, ECEF/geodetic/ENU, VRS
  transformation, leakage exclusion, anchors, decorrelation slope, zero-wins ranking.
- CORRECTED: orbits/ephemeris handling, ENU frames, containment, GF sign, Niell
  mapping, LOOCV datum/estimand, Phase 6 geometry-v3 evidence, four VRS geometry-v3
  rotations, equation traceability.
- SUPERSEDED: old pilot on-disk outputs (overwritten post-freeze; hashes in
  `before-review.json`), `PILOT_EVIDENCE.md` figures, VRS v1/v2 (numerics identical,
  IDs retired), old bounding-circle containment labels.
- PROVISIONAL: ionospheric arc-detrended proxy interpretation, standard-atmosphere
  troposphere (no measured met), 0.05 m coverage display threshold, one-day
  decorrelation slope, VRS diagnostic residuals.
- BLOCKED: RINEX export certification, RTKLIB positioning validation, any non-zero
  model promotion, Phase 8.

## 12. Remaining limitations

One day, four stations, three references over 105–1029 km; all folds extrapolated;
FLOAT-only long-baseline context; no measured meteorology; undetected cycle slips
possible in TD-DD; PRIDE daily coordinates as target truth; broadcast (not precise)
orbits for mapping only; doc-number orphan noted above must be repaired.

## 13. Phase 7 merge recommendation

**APPROVED_WITH_PROVISIONAL_LIMITATIONS** (i.e. DO NOT MERGE until the three
conditions are met; no further scientific revalidation required beyond them):
1. Rewrite `research/atmospheric_spatial_model/PILOT_EVIDENCE.md` from geometry-v3
   artifacts (or mark it superseded and point to this document + evidence files).
2. Mark the old pilot experiment directory SUPERSEDED in its provenance (do not
   silently reuse its ID), keeping `before-review.json` hashes as the audit trail.
3. Retire VRS v1/v2 IDs in favour of `*-geometry-v3` in Phase 7 docs/provenance.

### Closure addendum (2026-09-09, review-closure sprint)

All three conditions are satisfied on this branch:
1. `research/atmospheric_spatial_model/PILOT_EVIDENCE.md` rewritten from
   geometry-v3 artifacts (corrected LOOCV n = 15948, zero 3.076 m, all folds
   extrapolation; old 2.984 m figures retained only as labelled SUPERSEDED
   history). `research/vrs_generator/PILOT_EVIDENCE.{md,json}` rewritten from
   geometry-v3 artifacts (78,060 observations; ZERO / VRS_GEOMETRY_ONLY).
2. Old pilot ID `atm-2024d026-phri-target` marked SUPERSEDED in the Phase 6
   evidence doc and in `EVIDENCE_INDEX.md`; frozen hashes preserved in
   `research/scientific_validation/evidence/before-review.json`.
3. Checked-in VRS definitions `research/vrs_generator/config/*.json` now declare
   `*-geometry-v3` IDs (CLI `plan` fingerprints match the recorded v3 outputs
   exactly); docs, evidence index and lookup paths reference geometry-v3;
   v1/v2 marked SUPERSEDED / NON-AUTHORITATIVE.
Recommendation: **MERGE this branch into main.**

## 14. Phase 8 readiness

No. Phase 8 remains Not Started by design; correction streaming/RTCM/NTRIP/live
ingestion untouched.
