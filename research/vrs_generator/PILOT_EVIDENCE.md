# Phase 7 — DOY 026 held-out pilot evidence (AUTHORITATIVE: geometry-v3)

Engineering synthesis and all four held-out diagnostic runs completed.
Independent scientific review is COMPLETE with verdict
**APPROVED_WITH_PROVISIONAL_LIMITATIONS**
(see `docs/phase6-7-scientific-validation.md`).
**NO VALIDATED INTERPOLATION GAIN. No spatial model promoted.**

Authoritative configurations use `vrs-2024d026-<target>-geometry-v3` with
explicit 180-second GPST sampling of the 30-second real reference observations.
All four runs used **ZERO spatial correction** (`ZERO / VRS_GEOMETRY_ONLY`);
no candidate was promoted. Earlier `geometry`, `geometry-v1` and `geometry-v2`
identifiers are **SUPERSEDED / NON-AUTHORITATIVE** (their observation/geometry
numerics were verified identical to v3; only virtual IDs/provenance differ —
see `research/scientific_validation/evidence/corrected-results.json`).

| Held-out target | References | Anchor | Anchor km | Observations | Epochs | GPS satellites |
|---|---|---|---:|---:|---:|---:|
| PHRI | ABFC, EKAK, MGBO | EKAK | 105.553 | 24,556 | 480/480 | 30 |
| ABFC | EKAK, MGBO, PHRI | PHRI | 470.870 | 17,764 | 480/480 | 30 |
| EKAK | ABFC, MGBO, PHRI | PHRI | 105.553 | 17,847 | 480/480 | 30 |
| MGBO | ABFC, EKAK, PHRI | ABFC | 689.687 | 17,893 | 480/480 | 30 |

**Total: 78,060 virtual observations.** All runs cover the scheduled grid
00:00:00–23:57:00 GPST (480 epochs; 100% grid coverage). This is not full-rate
30-second coverage. Station names in the table abbreviate canonical `00NGA` IDs.

## Held-out residual metrics

Code values below remove one mean receiver-clock/code offset per epoch/code.
Phase values are time-differenced double differences over 180 s with a
common pivot and continuity gates. They are **not positioning errors**,
undifferenced phase RMSE or estimates of fixed-ambiguity accuracy. Values are
copied from the geometry-v3 `validation.json` artifacts (see
[PILOT_EVIDENCE.json](PILOT_EVIDENCE.json)).

| Target | Code | Diagnostic | Compared residuals | Matched/generated | RMSE m | MAE m | Bias m | Std m |
|---|---|---|---:|---:|---:|---:|---:|---:|
| PHRI | C1 | code clock-adjusted SD | 4471 | 4471/5090 | 0.597398 | 0.447265 | 0.000000 | 0.597465 |
| PHRI | L1 | phase TD-DD | 3843 | 4449/4928 | 2.087014 | 0.172485 | -0.077021 | 2.085864 |
| PHRI | L2 | phase TD-DD | 3809 | 4422/4846 | 3.202432 | 0.279736 | -0.096593 | 3.201395 |
| PHRI | P1 | code clock-adjusted SD | 0 | 0/4846 | — | — | — | — |
| PHRI | P2 | code clock-adjusted SD | 4422 | 4422/4846 | 0.767866 | 0.563189 | 0.000000 | 0.767953 |
| ABFC | C1 | code clock-adjusted SD | 4471 | 4471/4471 | 2.055959 | 1.449081 | 0.000000 | 2.056189 |
| ABFC | L1 | phase TD-DD | 3844 | 4449/4449 | 1.202816 | 0.190285 | 0.007523 | 1.202949 |
| ABFC | L2 | phase TD-DD | 3809 | 4422/4422 | 1.562901 | 0.268645 | -0.036049 | 1.562690 |
| ABFC | P2 | code clock-adjusted SD | 4422 | 4422/4422 | 2.742829 | 1.986889 | 0.000000 | 2.743139 |
| EKAK | C1 | code clock-adjusted SD | 4471 | 4471/4472 | 0.597372 | 0.447218 | 0.000000 | 0.597439 |
| EKAK | L1 | phase TD-DD | 3843 | 4449/4467 | 2.087016 | 0.172480 | 0.077029 | 2.085866 |
| EKAK | L2 | phase TD-DD | 3809 | 4422/4454 | 3.202435 | 0.279732 | 0.096601 | 3.201398 |
| EKAK | P2 | code clock-adjusted SD | 4422 | 4422/4454 | 0.767822 | 0.563108 | -0.000000 | 0.767909 |
| MGBO | C1 | code clock-adjusted SD | 4471 | 4471/4501 | 3.749014 | 2.461310 | 0.000000 | 3.749433 |
| MGBO | L1 | phase TD-DD | 3922 | 4449/4484 | 0.655840 | 0.282721 | -0.056231 | 0.653508 |
| MGBO | L2 | phase TD-DD | 3880 | 4422/4454 | 1.249318 | 0.360174 | -0.059889 | 1.248042 |
| MGBO | P2 | code clock-adjusted SD | 4422 | 4422/4454 | 4.442922 | 3.057066 | -0.000000 | 4.443424 |

PHRI generation counts: C1 5,090; P1 4,846; P2 4,846; L1 4,928; L2 4,846.
PHRI C1 support is 7–14 satellites per generated epoch. Target PHRI has no
compatible GPS P1 comparison samples, so P1 validation metrics remain null.
Its C1 matching coverage is 87.84%; P2 91.25%; L1 90.28%; L2 91.25%.
Phase residual counts are smaller than matched counts because differencing
needs a pivot and adjacent continuous observations. Undetected slips may
remain; large phase residuals are retained rather than filtered to improve RMSE.

## Controls, limitations and provenance

- Corrected Phase 6 comparison (identical-sample LOOCV, n = 15,948, experiment
  `atm-2024d026-phri-target-geometry-v3`): zero 3.076 m, IDW 3.352 m,
  nearest 3.757 m, planar 14.373 m. **No spatial interpolator beats the zero
  control; nothing was promoted.** All four held-out rotations are
  extrapolation cases. These are Phase 6 proxy metrics, not Phase 7 VRS
  residual metrics. Older Phase 6 figures (zero 2.984 m, n = 17,768) are
  SUPERSEDED and match no stored artifact.
- No corrected candidate VRS was generated. Diagnostic requests block because
  the arc-detrended GF proxy lacks validated observation-datum translation.
- The upstream Phase 6 navigation radians/GPST defects found during review were
  corrected and the affected evidence regenerated; the corrected ranking above
  is the conservative veto. VRS synthesis uses pinned RTKLIB directly and its
  observation/geometry numerics were verified identical across versions.
- Target leakage: PASS in all four rotations
  (`held_out_observations_used_in_synthesis=false`). Target observation bodies
  are excluded from synthesis. Only verified target coordinates and upstream
  validation metadata are consumed. Source-file aliases are rejected;
  validation loads target observations separately.
- No absolute atmosphere, measured meteorology, integer ambiguity, centimetre
  positioning, network-RTK improvement or accuracy gain is claimed.
- RINEX export is uncertified and RTKLIB positioning validation was NOT PERFORMED.
- IGS20 station coordinates and GPS broadcast WGS84 realization limitations,
  inherited antenna/hardware/clock effects and uncorrected atmosphere remain explicit.
- PHRI generation re-run verified matching material/output hashes and returned
  `reused=true` without regenerating observations.

Full outputs are outside Git:

```text
${NLGCP_DATA_ROOT}/processed/vrs/experiments/vrs-2024d026-phri-geometry-v3/
${NLGCP_DATA_ROOT}/processed/vrs/experiments/vrs-2024d026-abfc-geometry-v3/
${NLGCP_DATA_ROOT}/processed/vrs/experiments/vrs-2024d026-ekak-geometry-v3/
${NLGCP_DATA_ROOT}/processed/vrs/experiments/vrs-2024d026-mgbo-geometry-v3/
```

Exact metrics, material fingerprints and artifact SHA-256s are copied from
validated machine output into [PILOT_EVIDENCE.json](PILOT_EVIDENCE.json).
Runtime provenance records the base commit plus the exact per-file source
hashes of the reviewed tree. The fingerprint excludes Git commit/timestamp
metadata so the committed identical algorithm can reuse and verify these
records. Unversioned/v1/v2 outputs are retained outside Git and are
SUPERSEDED / NON-AUTHORITATIVE.

Reproduce using the checked-in configurations and the CLI commands in
[README.md](README.md). Changing scientific inputs requires a new experiment ID.
The reference observations and raw dataset were not modified.

## Checks and review

79 Phase 7 tests pass (including leakage-exclusion tests and six native RTKLIB
tests using labelled synthetic orbits); 355 total repository Python tests pass.
Final `make check` PASS: Ruff, mypy strict, pytest, Go format/vet/tests,
CMake/CTest, ESLint, TypeScript and Next.js production build.
See `EVIDENCE_INDEX.md` and `docs/phase6-7-scientific-validation.md`.

Next: merge the reviewed branch into main under the recorded conditions, then
acquire denser multi-day observations. Correction mode stays
ZERO / VRS_GEOMETRY_ONLY. Phase 8 implementation has not begun.
