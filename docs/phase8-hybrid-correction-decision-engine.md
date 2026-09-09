# Phase 8 — Hybrid Correction Decision Engine

## 1. Purpose

Phase 8 answers one question for a rover request:

```text
WHAT CORRECTION MODE SHOULD NLGCP USE FOR THIS ROVER?
```

It chooses among `VRS`, `SINGLE_BASE`, and `NO_CORRECTION`, qualified
by `OK`, `DEGRADED`, `BLOCKED`, or `DIAGNOSTIC_ONLY`. It does not
manufacture a correction, promote a spatial model, or produce RTCM /
NTRIP output. Failing closed (`NO_CORRECTION` with blockers) is a
successful engine behaviour.

## 2. Position in the pipeline

```text
rover request (location + time)
     ↓ Phase 4 QC state (ACCEPT-only admission; WARN never auto-ACCEPT)
station availability (candidates + navigation + verified coordinates)
     ↓ network geometry (admitted count, extent, extrapolation)
Phase 6 model status (consumed contract, never re-derived)
     ↓ Phase 7 VRS status (consumed contract, never re-derived)
single-base candidates (deterministic QC-first ranking)
     ↓ integrity / provenance checks
decision → VRS | SINGLE_BASE | NO_CORRECTION
```

## 3. Parallel-development constraint (review COMPLETE)

The Phase 6/7 scientific validation and geometry hardening review ran
independently and is now COMPLETE
(`APPROVED_WITH_PROVISIONAL_LIMITATIONS`, merged). Phase 8 therefore
depends only on two stable interfaces, never on unreviewed Phase 7
implementation details (now populated against reviewed geometry-v3
evidence):

- `SpatialCorrectionAssessment` with `SpatialModelStatus` (`APPROVED`,
  `PROVISIONAL`, `REJECTED`, `BLOCKED`, `UNAVAILABLE`).
- `VRSCapabilityAssessment` with `VRSStatus` (`APPROVED`,
  `PROVISIONAL`, `NOT_VALIDATED`, `BLOCKED`, `UNAVAILABLE`).

Reviewed defaults (Phase 6/7 review COMPLETE) represent Phase 6 as
`REJECTED` for correction purposes — best model `zero` RMSE 3.076 m
beats IDW 3.352 / nearest 3.757 / planar 14.373 m (n=15948 identical
samples, all folds EXTRAPOLATION); BEST MODEL = ZERO; no interpolator
promoted; zero wins as the control and is NOT a promotable spatial
correction model — and Phase 7 as `BLOCKED` for operational corrected
service (synthesis reviewed `APPROVED_WITH_PROVISIONAL_LIMITATIONS`,
mode `ZERO / VRS_GEOMETRY_ONLY`, promoted model NONE, leakage PASS;
geometry-only diagnostic available, operational corrected VRS NOT
APPROVED), so automatic corrected VRS remains fail-closed. Historical
pre-review defaults (Phase 6 `UNAVAILABLE` 2.984 m n=17768 / Phase 7
`NOT_VALIDATED`) are SUPERSEDED. Reviewed evidence is integrated as the
CLI defaults plus optional JSON assessments with no further Phase 8 code
change; changed fingerprints invalidate pre-review decisions (see §11).

## 4. Decision priority and approval rules

Default `AUTO` strategy: validated VRS → single-base fallback → no
correction. VRS is selected automatically ONLY IF every gate passes:

```text
Phase 4 network admission PASS
AND network geometry PASS
AND Phase 6 correction model APPROVED
AND Phase 7 VRS APPROVED
AND target leakage PASS
AND provenance PASS
AND required data/products available
```

Any failure blocks automatic VRS. `VRS_ONLY` never falls back;
`SINGLE_BASE_ONLY` never considers VRS.

## 5. Admission gates

- Network mode consumes Phase 4 `network_rtk == ACCEPT` only;
  single-base mode consumes `single_base_rtk == ACCEPT` only
  (the engine reads per-station single-base QC where available and
  otherwise the candidate QC status). `WARN` requires review and never
  converts to `ACCEPT`; `REJECT`/`BLOCKED` are excluded from automatic
  selection.
- Station eligibility is confirmed before ranking: QC status,
  navigation product presence (SHA-256), coordinate verification
  (IGS20 frame + epoch from `derived-coordinates.json`, only
  `scientifically_valid` entries), observation/common-interval
  presence, equipment metadata, and Phase 4 fingerprint are recorded
  per candidate.
- Single-base ranking order: QC → navigation → coordinates → overlap
  → distance (nearest survivor only) → recorded completeness. The
  rover itself is excluded. Distance bands (`preferred` ≤150 km,
  `degraded` ≤500 km, `maximum` ≤1100 km) are PROVISIONAL engineering
  defaults: distance never overrides a failed gate, and no centimetre
  accuracy is ever claimed (Phase 5 evidence on these baselines is
  FLOAT-only, metre-level: EKAK→PHRI 105.553 km at 0.968 m horizontal
  RMSE; ABFC→PHRI 470.870 km at 1.093 m; MGBO→PHRI ~1029 km at
  1.802 m).

## 6. Request and response models

`DecisionRequest`: `request_id`, `request_time`, target
latitude/longitude/height and/or `target_ecef` and/or
`target_station_id` (resolved against verified coordinates only —
targets are never invented), requested start/end, `desired_mode`
(`AUTO`/`VRS_ONLY`/`SINGLE_BASE_ONLY`), `allow_fallback`,
`diagnostic`, `year`/`day_of_year`, plus optional receiver
capabilities, constellations, supported RTCM messages, sampling and
latency requirements.

`CorrectionDecision`: `decision_id`, `request_id`, `timestamp`, `mode`,
`status`, `reason_code`, `reason_text`, selected reference / network /
VRS experiment, candidate references, distance to selected reference,
network station count and geometry status, QC / spatial-model / VRS /
integrity statuses, full `provenance`, `fallback_used`,
`warnings[]`, `blockers[]`, `decision_fingerprint`, `diagnostic` flag.

Stable reason codes include `VRS_APPROVED`,
`VRS_MODEL_NOT_VALIDATED`, `VRS_GEOMETRY_INSUFFICIENT`,
`VRS_UPSTREAM_REVIEW_PENDING`, `SINGLE_BASE_SELECTED`,
`SINGLE_BASE_TOO_DISTANT`, `SINGLE_BASE_QC_REJECTED`,
`SINGLE_BASE_NAVIGATION_MISSING`, `NO_ACCEPTABLE_CORRECTION_SOURCE`,
`NO_NAVIGATION_PRODUCT`, `NO_QC_ADMITTED_STATIONS`,
`INVALID_TARGET_COORDINATE`, `STALE_PROVENANCE`, `DIAGNOSTIC_PREVIEW`.

## 7. Integrity, provenance, fingerprinting

Integrity is the transparent status `PASS` / `DEGRADED` / `BLOCKED`
derived from explicit decision evidence; no numeric score is
implemented. Provenance preserves Phase 4 QC fingerprints, Phase 6/7
assessment fingerprints, station metadata, navigation hashes,
coordinate frame/epoch, engine version, Git commit, policy fingerprint,
and execution timestamp. The decision fingerprint covers target,
request time, station set, QC/navigation/coordinate evidence, upstream
assessments, policy, and software version — the engine recomputes every
decision, so any change yields a new fingerprint and invalidates prior
cached decisions.

## 8. Diagnostic mode

`diagnostic=true` previews unvalidated candidates and rejected
stations but watermarks the outcome `DIAGNOSTIC_ONLY` with
`NOT_FOR_OPERATIONAL_CORRECTION`. Diagnostic output can never silently
become operational admission.

## 9. Policy

`research/hybrid_decision_engine/config/hybrid-decision-policy-v1.json`
(policy `v1.0`, schema `1.0`). The 3-reference floor mirrors the Phase 5
triangle minimum (scientifically validated); distance bands and the
common-interval floor are labelled `PROVISIONAL` / `ENGINEERING_DEFAULT`.

## 10. Current real-data behaviour (DOY 026 pilot, reviewed)

Only DOY 026 provides a four-station ACCEPT overlap
(ABFC/EKAK/MGBO/PHRI). Under reviewed defaults the engine derives:
`AUTO` at PHRI → `SINGLE_BASE`/`OK` via EKAK00NGA (105.553 km,
fallback, `VRS_MODEL_NOT_VALIDATED`: Phase 6 `REJECTED`, Phase 7
`BLOCKED` operational, geometry `EXTRAPOLATION`); `VRS_ONLY` →
`NO_CORRECTION`/`BLOCKED` (`VRS_MODEL_NOT_VALIDATED`; no fallback);
`SINGLE_BASE_ONLY` → `SINGLE_BASE` via EKAK00NGA. `OK` means admission
gates passed, not centimetre accuracy: every decision states `no
centimetre accuracy claimed`; the 105.553 km EKAK–PHRI baseline is the
nearest admitted fallback under PROVISIONAL policy, not a proven ideal
RTK distance (Phase 3: FLOAT-only, horiz RMSE 0.968 m). Pre-review
behaviour (`VRS_UPSTREAM_REVIEW_PENDING`, fingerprints
`phase6-pre-review…` / `phase7-pre-review…`) is SUPERSEDED/STALE.
Held-out AUTO probes (pre-review reference): ABFC → PHRI 470.870 km
`DEGRADED`; EKAK → PHRI 105.553 km `OK`; MGBO → ABFC 689.687 km
`DEGRADED`. Full evidence in
`research/hybrid_decision_engine/PILOT_EVIDENCE.md`; outputs under
`${NLGCP_DATA_ROOT}/processed/hybrid-decisions/` (outside Git).

## 11. Phase 6/7 review integration and Phase 9 interface

Reviewed Phase 6/7 evidence is integrated as the CLI defaults plus
optional `--spatial` / `--vrs` JSON assessments. Pre-review decisions
are fingerprint-invalidated (Phase 6 `phase6-pre-review…` != reviewed
`phase6-reviewed-geometry-v3-zero-3076-n15948`; Phase 7
`phase7-pre-review…` != reviewed
`phase7-reviewed-geometry-v3-phri-24556`). Later replay/streaming phases
consume only
`CorrectionDecisionPhase9` (`mode`, `source`, `reference_station`,
`virtual_station`, `correction_artifact`, `status`, `valid_from`,
`valid_until`, `provenance`) via `phase9-handoff.json`.

## 12. Non-goals and claims not made

No recorded RTCM replay, live CORS ingestion, RTCM encoding/generation,
NTRIP caster, rover sessions, or production streaming. No claim of VRS
superiority, single-base centimetre accuracy, a validated Nigerian
network model, fixed ambiguities, or production correction
availability. Phase 8 decides availability; it does not manufacture
scientific validity.
