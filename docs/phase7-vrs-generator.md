# Phase 7 — Offline Virtual Reference Observation Generator

## Scope and scientific status

This is an offline **VRS_GEOMETRY_ONLY** technical control. It transforms
traceable physical observations to a verified station coordinate, preserving
the anchor receiver's clock, hardware, noise and ambiguity datum. Every output
is marked **NO VALIDATED INTERPOLATION GAIN**. It is not an operational VRS
service, and no fixed-ambiguity or positioning accuracy claim follows from it.

The implementation follows baseline documents 13, 14, 15, 21 and 23 and
ADR-002/003/011/012. The master sprint explicitly permits this structured
geometry-only control with zero atmospheric correction. The baseline's
validated-network requirement remains mandatory for correction service;
there is no architecture change and no live stream is fabricated.

Scientific changes require Level 3 review under `CONTRIBUTING.md`. Engineering
checks, an analytic synthetic orbit comparison and held-out real-observation
diagnostics do not replace independent scientific review or surveyed field
validation. Phase 4 admission thresholds remain **PROVISIONAL**.

## Observation equations and units

Let `a` denote the anchor, `v` the virtual marker coordinate, `s` a GPS satellite,
`f` a frequency, `P` code in metres and `L` phase in cycles. With phase ambiguity
sign convention defined by `+lambda*N`, the observation equations are:

```text
P_a,f^s        = rho_a^s + c(dt_a - dt_s,a) + T_a^s + I_a,f^s + b_P + noise_P
lambda_f L_a,f^s = rho_a^s + c(dt_a - dt_s,a) + T_a^s - I_a,f^s
                  + lambda_f N_a,f^s + b_L + windup + noise_L

Delta_rho = rho_v^s - rho_a^s
Delta_clock = -c(dt_s,v - dt_s,a)
Delta_g = Delta_rho + Delta_clock

P_v,f^s = P_a,f^s + Delta_g
L_v,f^s = L_a,f^s + Delta_g / lambda_f
```

The code and phase signs follow the [ESA/UPC observation equations](https://gssc.esa.int/navipedia/index.php/GNSS_Basic_Observables).
The last two equations define this particular zero-atmosphere control: the
anchor's atmospheric effects remain in the source measurements; setting the
**applied spatial correction** to zero does not assert atmosphere is zero.
A future validated atmospheric translation would add `Delta_T + Delta_I_f`
to code and `Delta_T - Delta_I_f` to phase in metres. No such translation is
implemented or inferred from a proxy here.

`c=299792458 m/s`, GPS L1 `1575420000 Hz`, L2 `1227600000 Hz`; wavelength is
`c/f`. Only existing GPS `C1/P1/P2/L1/L2` values are transformed. Doppler, SNR
observables, other bands and constellations are explicitly excluded. SSI is
retained as a source quality indicator, not synthesized as an observable.

Established VRS processing also needs network clock, atmosphere and ambiguity
datums; see [Odijk (2002), section 6.5](https://gnss.curtin.edu.au/wp-content/uploads/sites/21/2016/04/Odi02.pdf).
This control inherits the physical anchor datum rather than estimating a
network ambiguity solution. No integers are invented, resolved or fixed.

## Satellite geometry and clock treatment

`native/geometry.c` is a small adapter linked against **unmodified** RTKLIB
`v2.4.2-p13`, commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`.
Every compiled dependency is byte-compared with that commit and SHA-256 hashed.
The build command, compiler version, adapter hash and executable hash are
recorded. Compilation occurs in the Phase 7 worktree's ignored `build/vrs/`.
No upstream source or installed RTKLIB binary is modified.

The adapter uses `readrnxt`, `uniqnav`, `satposs`, `geodist`, `ecef2pos` and
`satazel`. These are source-verified in the [pinned RTKLIB source](https://github.com/tomojitakasu/RTKLIB/tree/71db0ffa0d9735697c6adfd06fdf766d0e5ce807/src).

1. Select an actual anchor code deterministically: positive C1, else P1, else P2.
2. Supply the RINEX GPST calendar epoch and that code to `satposs`. It computes
   transmit time from the code, applies broadcast clock correction and
   propagates the selected ephemeris. No fixed satellite coordinates are used.
3. Compute anchor range with RTKLIB's first-order Sagnac formulation:
   `rho = |r_s-r_r| + omega_E/c * (x_s*y_r-y_s*x_r)`.
4. Initialize virtual range from this position. Iterate virtual pseudorange
   `P_v = P_a + (rho_v-rho_a) - c(dt_s,v-dt_s,a)`, call `satposs` for that
   virtual pseudorange, and recompute virtual range. This accounts for the
   target's distinct transmit time at the same receiver-clock epoch.
5. Stop when range change is below `1e-5 m`, with eight iterations maximum.
   These are numerical convergence safeguards, not scientific accuracy or
   model promotion thresholds. Nonconvergence blocks that observation.

Satellite clock translation is separated from geometric displacement in the
CSV. RTKLIB's broadcast clock has relativistic treatment; group delays are
not separately translated. The source code's timing bias, atmosphere and
receiver clock datum are inherited, so this is not a fully calibrated
physical-observation simulator. The [ESA satellite-coordinate treatment](https://gssc.esa.int/navipedia/index.php/Satellite_Coordinates_Computation)
explains the emission/reception-time and Earth-rotation distinction.

RTKLIB enforces its pinned GPS ephemeris age bound (`MAXDTOE+1`, 7201 seconds),
and nonzero SV health, unavailable positions, nonpositive ranges, and satellites
at/below the geometric horizon at anchor or target are excluded. No arbitrary
scientific elevation mask is introduced. Elevation uses RTKLIB geodetic ENU;
its first-order direction does not rotate the line of sight separately for
Sagnac. Low-elevation observations remain diagnostics, not service admission.

## Phase 6 audit and fail-closed selection

The recorded DOY 026 validation is preserved: zero 2.984 m, IDW 3.546 m,
nearest 4.004 m, planar 15.300 m on the recorded identical comparison samples.
No interpolator beats zero in that record. Phase 7 verifies the experiment
context, inputs, completion, metric finiteness, sample counts and declared
winner, then selects zero. Missing or contradictory validation blocks even
geometry-only generation.

During Phase 7 source review, two upstream geometry concerns were identified:

- Phase 6's RINEX navigation parser multiplies angles by pi even though RINEX
  stores orbital angles in radians and rates in radians/second. See the
  [IGS RINEX specification, navigation table](https://files.igs.org/pub/data/format/rinex211.txt).
- Phase 6 observation calendar labels are stored with a UTC offset and its
  geometry path adds 18 seconds to them; the real pilot headers declare GPS
  time. Phase 7 keeps GPST labels explicitly and adds no UTC leap offset.

Phase 6 code and outputs were not changed in this sprint. Its recorded ranking
is consumed as a veto, **not re-certified as scientifically valid**. The affected
satellite geometry, troposphere and combined-field validation require an
upstream correction, regeneration and review before any promotion. Phase 7
uses RTKLIB directly and tests nonzero orbital radians, GPST, dynamic transmit
positions and Sagnac against an independent analytic circular orbit.

`GF_SD_ARC_DETRENDED` is an arc-median-detrended, station-differenced GPS L1/L2
ionospheric proxy. Its absolute offset is unresolved; it is not absolute TEC
or an absolute code/phase correction. No target-field CSV values are used in
synthesis. Phase 6's Berg pressure, Saastamoinen ZHD, default 0.12 m ZWD and
Niell mapping are a priori with no measured meteorology; no Phase 7
tropospheric correction is applied.

## Promotion rule

A numerical candidate can only be considered for `APPROVED_FOR_VRS` after:

- it improves both zero and nearest on identical, independent validation keys;
- reviewed coverage and effective sample-size criteria are met, accounting for
  temporal/satellite dependence rather than treating every row as independent;
- reviewed station geometry and extrapolation criteria pass without pathology;
- proxy-to-code/phase units, signs, datum and ambiguity translation are validated;
- upstream geometry findings are resolved and Level 3 evidence is reviewed.

Only the first comparison can currently be evaluated numerically. The repository
has no approved empirical bounds for the other conditions, and Phase 7 does not
invent them. Accordingly **no model can be promoted by this version**. The gate
records missing criteria explicitly, even if a synthetic test makes IDW's RMSE
smaller than both controls. Enabling approval needs a reviewed policy/code change
with new validation evidence; a boolean in an input file cannot authorize it.

Explicit `diagnostic=true` candidate requests are recognized but return BLOCKED
with the unresolved proxy-translation reason. Candidate RMSE comparison is
available from the Phase 6 evidence in `correction-model.json`; corrected VRS
candidate observations are not claimed to have been generated.

## Admission, coordinates and leakage prevention

Targets are existing **scientifically_valid** PRIDE station coordinates only.
Frame and coordinate epoch must exactly match the definition, and original
PRIDE position files are checksum-verified. No hand-picked/invented locations
or coordinate propagation is supported. ECEF is authoritative; latitude,
longitude and height are derived using the repository's WGS84 ellipsoid helper.
That ellipsoid conversion does not rename the ECEF frame.

Station coordinates remain **IGS20** at their recorded coordinate epoch.
Navigation positions retain **GPS broadcast WGS84** provenance. No realization
transformation is silently applied; the unresolved alignment is a declared
limitation of this technical control and precludes precision claims. Marker to
antenna phase centre offsets, antenna patterns, hardware biases, phase wind-up
and their displacement changes are not calibrated in Phase 7.

References require current Phase 4 `network_rtk` ACCEPT results consistent with
Phase 5 admission, source hashes and verified coordinates. Phase 5 geometry,
manifest and admission files and Phase 6 derivation/validation/model files are
fingerprinted. The anchor is the smallest ECEF chord distance to the target,
with lexical station ID tie breaking. It stays fixed throughout an experiment.

The generator's dataset map must exactly match the reference list. The target
must be absent. Path aliases, duplicate reference contents and target/reference
content aliases are rejected. Only reference datasets determine the epoch,
satellite and code intersections. Target observations are first read by the
separate `validate` operation; changing target observation contents does not
feed measurements into synthesis. Prior Phase 5/6 aggregate evidence includes
target data, but is used only for context and a conservative zero-correction
veto, never as a fitted numerical correction. Target coordinates themselves
come from the station's PRIDE daily solution and are not independent surveyed
truth; that limitation is explicit.

RINEX 2.11 GPS-time headers, full-cycle wavelength factors and finite records
are required. Power-failure flags and LLI/SSI survive parsing. Unsupported event
or header updates, nonzero epoch receiver-clock fields, duplicate epochs,
malformed/truncated records and unsupported time systems fail closed. There is
no interpolation across missing epochs. Sampling is selected on the definition's
GPST grid, with an interval that is an integer multiple of reference intervals.

## Held-out validation

Comparison uses exact matching GPST epoch, satellite and observation code.
Two distinct diagnostics avoid incompatible datums:

```text
code SD_s(t) = P_VRS,s(t) - P_target,s(t)
code residual_s(t) = SD_s(t) - mean_over_matched_satellites(SD(t))

phase SD_s(t) = lambda * (L_VRS,s(t) - L_target,s(t))
phase residual_s,p(t) = [SD_s(t)-SD_s(t-interval)]
                       - [SD_p(t)-SD_p(t-interval)]
```

Code requires at least two satellites; the removed epoch/code offset is recorded
in the residual CSV. This fits a nuisance receiver clock/code datum on the same
validation samples. It does not test absolute code bias and reduces residual
variance relative to an unfitted comparison.

Phase uses adjacent scheduled epochs and a lexical pivot satellite common to
both. The same satellite pair is differenced at both epochs; constant
inter-receiver ambiguities and common receiver-clock changes cancel. Gaps,
power failures, half-cycle states, loss-of-lock flags or changed LLI at either
receiver exclude the pair. Constant LLI bit 2 (A/S annotation) is retained;
it is not treated as a new slip every epoch. Undetected slips can remain.

Phase metrics are **time-differenced double-difference residuals over 180 s**,
not undifferenced phase error, fixed-ambiguity evidence or phase prediction
accuracy. Metrics report count, bias, MAE, RMSE, standard deviation and exact
matching coverage by code. No Phase 6 provisional 0.05 m tolerance is imported.
Residual series are not necessarily independent, so no significance test or
confidence interval is claimed. Positioning validation is not performed.

## Output and reproducibility contract

```text
${NLGCP_DATA_ROOT}/processed/vrs/experiments/<experiment-id>/
  definition.json             # resolved ECEF/LLH, frame, epoch, navigation, software
  admission.json              # reference QC fingerprints and provisional status
  target.json                 # verified coordinate and source provenance
  anchor.json                 # deterministic identity/distance/reason
  correction-model.json       # zero selection, recorded comparison, promotion veto
  virtual-observations.csv    # source, deltas, satellite geometry, flags, output
  provenance.json             # inputs, software hashes, Git commit/dirty, timestamp
  metrics.json                # generation coverage and counts
  exclusions.json             # explicit exclusion reasons/counts
  completion.json             # material fingerprint and all generation output hashes
  validation-residuals.csv    # independent held-out diagnostics
  validation.json             # held-out hashes, metrics, limitations
```

Each row points to the provenance fingerprint and source observation SHA-256.
Virtual IDs are `VRS_<experiment-id>`, never an existing physical station ID.
Derived observations are labelled **VIRTUAL / SYNTHETIC DERIVED OBSERVATION**.
Unit fixtures separately carry **SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS**.

Generation publishes an isolated temporary directory by rename only after
successful synthesis and a second input fingerprint check. Existing results
are reused only after material and output hashes match. Changed inputs, source
code, navigation, coordinates, QC or model/validation evidence block reuse;
choose a new experiment ID to retain both records. Corrupted/missing outputs
block reuse. Validation records its own target input and residual hashes;
`summarize` verifies them before returning a stored result. Dry runs do not
build the adapter or write derived experiment outputs.

## RINEX policy and Phase 8 interface

RINEX VRS export is deliberately deferred, including header generation. A
request for `rinex_output=true` is rejected. Before export, independently review
antenna/receiver metadata policy, marker versus phase-centre displacement,
clock/phase datums, receiver interoperability, time system and format round-trip
validation. The structured representation is the deliverable for this phase.

Phase 8 can later consume the versioned JSON/CSV contract and the explicit
`automatic_correction_approved=false` decision. This is readiness for offline
interface integration only, not for selecting a production VRS correction.
No Phase 8 decision engine, RTCM, caster, rover connection, live CORS ingestion
or streaming is implemented. Acquire denser, multi-day data and resolve the
Phase 6 audit before seeking scientific promotion.
