# Phase 8 — Hybrid Correction Decision Engine

## Purpose

Phase 8 decides **which correction strategy is permitted for a rover**:

```text
VRS | SINGLE_BASE | NO_CORRECTION
```

with the operational qualifier:

```text
OK | DEGRADED | BLOCKED | DIAGNOSTIC_ONLY
```

Phase 8 does NOT manufacture a correction, promote a spatial model,
generate RTCM, run NTRIP, ingest live streams, or resolve ambiguities.
It makes a scientifically defensible, fail-closed decision about which
correction strategy is permitted, and explains itself with
machine-readable reason codes plus a human-readable trace.

Decision hierarchy (default `AUTO` strategy):

```text
1. Validated VRS (all approval gates pass)
2. Acceptable single-base fallback (one ACCEPT physical reference)
3. No correction (fail closed with blockers)
```

VRS is never preferred merely because a VRS generator exists: automatic
VRS selection requires the conjunction of every approval gate.

## Architecture

```text
rover request (models.DecisionRequest)
     ↓  discovery.py — candidate stations from observed evidence
station candidates (QC / navigation / coordinates / coverage)
     ↓  network.py — admitted-reference count, geometry, coverage
network eligibility (VRS network candidate or blockers)
     ↓  single_base.py — deterministic QC-first ranking
single-base fallback assessment
     ↓  vrs.py — conjunctive approval gate over upstream contracts
VRS selectability (APPROVED-only)
     ↓  decision.py — AUTO / VRS_ONLY / SINGLE_BASE_ONLY routing
CorrectionDecision + Phase 9 handoff + trace + provenance
```

Module map (`research/hybrid_decision_engine/src/nlgcp_hybrid_decision/`):

| Module | Responsibility |
|---|---|
| `models.py` | Request/response models, `VRSStatus` / `SpatialModelStatus` upstream contracts, `CorrectionDecision`, Phase 9 handoff view, stable `ReasonCode`s |
| `policy.py` | Versioned decision policy (`v1.0`); PROVISIONAL-labelled distance bands; validation floor of 3 references |
| `discovery.py` | Candidate stations from Phase 4 QC results, verified coordinates, navigation products; never invents coordinates |
| `network.py` | Network eligibility: admitted count, target-fan geometry proxy, extrapolation flag, common-interval presence, navigation coverage |
| `single_base.py` | Deterministic single-base ranking: QC → navigation → coordinates → overlap → distance (nearest survivor only) |
| `vrs.py` | Conjunctive VRS approval gate over consumed upstream assessments; never promotes a model |
| `integrity.py` | Transparent `PASS` / `DEGRADED` / `BLOCKED` integrity (no numeric scores) |
| `provenance.py` | Upstream fingerprint preservation and decision fingerprinting; cache invalidation inputs |
| `decision.py` | Mode routing (`AUTO` / `VRS_ONLY` / `SINGLE_BASE_ONLY`), fallback handling, diagnostic watermarking |
| `reporting.py` | Human-readable trace, per-request output bundle, summary CSVs |

## Upstream contracts (parallel-development isolation)

Phase 8 never imports Phase 6/7 implementation details. It consumes two
stable assessment records:

- `SpatialCorrectionAssessment` — Phase 6 contract: `model_name`,
  `validation_status` (`APPROVED` / `PROVISIONAL` / `REJECTED` /
  `BLOCKED` / `UNAVAILABLE`), metrics vs zero/nearest controls,
  `sample_count`, `geometry_status`, `extrapolation`, `fingerprint`,
  `provenance`.
- `VRSCapabilityAssessment` — Phase 7 contract: `status` (`APPROVED` /
  `PROVISIONAL` / `NOT_VALIDATED` / `BLOCKED` / `UNAVAILABLE`),
  `experiment_id`, `target`, `reference_stations`, `anchor`,
  `correction_mode`, `model_status`, `observation_coverage`,
  `validation_status`, `target_leakage_status`, `fingerprint`,
  `provenance`.

Phase 6/7 scientific review is COMPLETE and merged. The real-data default
now represents reviewed evidence: Phase 6 as `REJECTED` for correction
purposes (best model `zero` RMSE 3.076 m beats IDW 3.352 / nearest 3.757 /
planar 14.373 m, n=15948 identical samples, all folds EXTRAPOLATION; no
interpolator promoted — zero wins as the control and is NOT a promotable
spatial correction model) and Phase 7 as `BLOCKED` for operational
corrected service (synthesis reviewed
`APPROVED_WITH_PROVISIONAL_LIMITATIONS`, mode `ZERO / VRS_GEOMETRY_ONLY`,
promoted model NONE, leakage PASS; geometry-only diagnostic available,
operational corrected VRS NOT APPROVED), so automatic corrected VRS stays
fail-closed. Custom assessments may be supplied as JSON (`--spatial`,
`--vrs`) to exercise the approved path synthetically. Historical
pre-review defaults (Phase 6 `UNAVAILABLE` 2.984 m n=17768 / Phase 7
`NOT_VALIDATED`) are SUPERSEDED; their fingerprints
(`phase6-pre-review-no-promoted-model` /
`phase7-pre-review-not-validated`) invalidate old decisions.

## VRS approval rule

VRS is automatically selected ONLY IF **all** of the following hold:

```text
Phase 4 network admission PASS (ACCEPT-only admitted references)
AND network geometry PASS (no unpermitted extrapolation)
AND Phase 6 correction model APPROVED
AND Phase 7 VRS APPROVED
AND target leakage PASS (target excluded from model fit)
AND provenance PASS (both upstream fingerprints present)
AND required data/products available
```

Any false condition blocks automatic VRS with a stable reason code
(`VRS_UPSTREAM_REVIEW_PENDING`, `VRS_MODEL_NOT_VALIDATED`,
`VRS_GEOMETRY_INSUFFICIENT`, `VRS_TARGET_LEAKAGE`,
`VRS_PROVENANCE_INVALID`).

## Single-base fallback

If VRS is unavailable or blocked and policy plus the request permit
fallback, physical-base candidates are evaluated in strict gate order.
Distance never overrides a failed science gate: a nearer `REJECT`
station is never selected over a farther `ACCEPT` station. Distance
bands (`preferred` ≤150 km, `degraded` ≤500 km, `maximum` ≤1100 km) are
**PROVISIONAL engineering defaults**, not empirically calibrated for
Nigeria; long baselines carry degraded expectations and no centimetre
claim is ever made.

## No-correction mode

When neither path passes admission, the engine returns
`NO_CORRECTION` (`BLOCKED`, or `DIAGNOSTIC_ONLY` in diagnostic mode)
with useful blockers (e.g. `NO_NAVIGATION_PRODUCT`,
`NO_QC_ADMITTED_STATIONS`). Failing closed is successful behaviour.

## Requested modes

- `AUTO`: validated VRS → single-base fallback → no correction.
- `VRS_ONLY`: VRS if all gates pass, else `NO_CORRECTION` (no fallback
  unless the request explicitly permits it — currently never falls back).
- `SINGLE_BASE_ONLY`: never considers VRS.

## Diagnostic mode

`diagnostic=true` exposes unvalidated candidates and rejected stations
in the trace/assessments but watermarks the decision `DIAGNOSTIC_ONLY`
with `NOT_FOR_OPERATIONAL_CORRECTION`. Diagnostic output is never
silently admissible as an operational correction.

## Policy

Versioned policy lives in
`research/hybrid_decision_engine/config/hybrid-decision-policy-v1.json`
(policy `v1.0`). Every value carries a calibration label
(`SCIENTIFICALLY_VALIDATED`, `PROVISIONAL`, `ENGINEERING_DEFAULT`).
The 3-reference floor mirrors the Phase 5 triangle minimum. WARN never
auto-converts to ACCEPT.

## Provenance and fingerprinting

Every decision records Phase 4 QC fingerprints, Phase 6/7 assessment
fingerprints, station metadata provenance, navigation hashes, coordinate
frame/epoch, engine version, Git commit, policy fingerprint, and
execution timestamp. The decision fingerprint covers target coordinate,
request time, station set, QC/navigation/coordinates fingerprints,
upstream assessments, policy, and software version. The engine always
recomputes (no stale cache); any fingerprint change yields a new
fingerprint, invalidating prior decisions.

## CLI

```bash
export NLGCP_DATA_ROOT=/home/excellence/nlgcp-data
.venv/bin/python scripts/run_hybrid_decision.py inspect --target-station PHRI00NGA --year 2024 --doy 26
.venv/bin/python scripts/run_hybrid_decision.py plan --target-station PHRI00NGA --year 2024 --doy 26 --desired-mode AUTO --request-id <id>
.venv/bin/python scripts/run_hybrid_decision.py decide --target-station PHRI00NGA --year 2024 --doy 26 --desired-mode AUTO --request-id <id> [--dry-run]
.venv/bin/python scripts/run_hybrid_decision.py explain --target-station PHRI00NGA --year 2024 --doy 26 --desired-mode AUTO --request-id <id>
.venv/bin/python scripts/run_hybrid_decision.py summarize
```

Optional: `--spatial <phase6.json> --vrs <phase7.json>`,
`--target-leakage-pass/--target-leakage-fail`, `--no-fallback`,
`--diagnostic`, `--policy <file>`.

## Outputs

Under `${NLGCP_DATA_ROOT}/processed/hybrid-decisions/` (outside Git):

```text
requests/<request-id>/{request,candidate-stations,network-assessment,
  vrs-assessment,single-base-assessment,decision,phase9-handoff,
  provenance,policy}.json + trace.txt
summaries/{decisions,blockers,fallback-usage}.csv
```

## Status semantics (`OK` vs positioning performance)

`OK` / `DEGRADED` / `BLOCKED` qualify admission integrity only: `OK`
means all decision-engine admission gates passed for the selected mode.
It does NOT claim centimetre positioning accuracy. Every `SINGLE_BASE`
decision states `no centimetre accuracy claimed` and carries the
PROVISIONAL distance band; the 105.553 km EKAK–PHRI baseline is the
nearest admitted fallback under provisional policy, not a scientifically
proven ideal RTK distance (Phase 3 found it remained FLOAT-only,
horiz RMSE 0.968 m). Integrity `PASS` (admission) is reported separately
from expected positioning performance (`PROVISIONAL` / `DEGRADED`).

## Tests

59 synthetic-only tests (`SYNTHETIC TEST DATA — NOT VALID FOR
SCIENTIFIC RESULTS`): mode routing, VRS approval/blocking, network
gates, single-base ranking (QC beats distance), WARN handling,
fallback on/off, diagnostic watermarking, provisional policy,
fingerprints and cache invalidation on target/Phase 6/Phase 7/QC/policy
change, Phase 9 handoff shape, malformed input, determinism, plus
reviewed-integration tests (Phase 6 zero winner, reviewed Phase 7 but no
promoted model, geometry-only VRS cannot become operational, reviewed
fingerprints, stale pre-review invalidation,
APPROVED_WITH_PROVISIONAL_LIMITATIONS semantics, AUTO fallback after
review).

## Real-data pilot

See `PILOT_EVIDENCE.md`: 2024 DOY 026 at PHRI (plus ABFC/EKAK/MGBO
scientific test targets). Reviewed state keeps automatic corrected VRS
blocked (`VRS_MODEL_NOT_VALIDATED`: Phase 6 `REJECTED`, Phase 7 `BLOCKED`
operational, geometry `EXTRAPOLATION`); `AUTO` falls back to
`SINGLE_BASE` via `EKAK00NGA` (105.553 km, preferred PROVISIONAL,
FLOAT-only history, no centimetre claim), `VRS_ONLY` returns
`NO_CORRECTION`/`BLOCKED`, `SINGLE_BASE_ONLY` returns `SINGLE_BASE` via
EKAK00NGA.

## Phase 6/7 review handoff

Reviewed evidence is integrated as the CLI defaults plus optional JSON
assessments (`--spatial`, `--vrs`). Fingerprints
(`phase6_assessment_fingerprint`,
`phase7_assessment_fingerprint`, `policy_fingerprint`,
`decision_fingerprint`) invalidate pre-review decisions automatically
(old Phase 6 `phase6-pre-review-no-promoted-model` != reviewed
`phase6-reviewed-geometry-v3-zero-3076-n15948`; old Phase 7
`phase7-pre-review-not-validated` != reviewed
`phase7-reviewed-geometry-v3-phri-24556`). No further Phase 8 code change
is needed to consume the reviewed evidence.

## What Phase 8 is not

No RTCM replay/encoding, no live CORS ingestion, no NTRIP, no rover
sessions, no production streaming, no ambiguity-resolution or accuracy
claims. The Phase 9 handoff (`CorrectionDecisionPhase9`: mode, source,
reference/virtual station, status, validity window, provenance) is the
only interface later phases need.
