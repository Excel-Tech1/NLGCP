# Phase 8 Pilot Evidence — Real DOY 026 Decisions

Pre-review pilot: Phase 6/7 scientific review PENDING. Phase 6 model
status `UNAVAILABLE` (no interpolator promoted; zero control
2.984 m won LOOCV honestly), Phase 7 status `NOT_VALIDATED`
(`ZERO / VRS_GEOMETRY_ONLY`). Automatic VRS therefore stays
fail-closed; outcomes below are derived by the engine from observed
evidence, not hard-coded.

Engine: `nlgcp_hybrid_decision 0.1.0`, policy `v1.0`
(`hybrid-decision-policy-v1.json`).
Outputs: `${NLGCP_DATA_ROOT}/processed/hybrid-decisions/requests/`
(`pilot-d026-phri-{auto,vrs-only,single-base-only}/`).

## PHRI00NGA (rover), 2024 DOY 026

Candidates (observed): ABFC00NGA ACCEPT 470.870 km, EKAK00NGA ACCEPT
105.553 km, MGBO00NGA ACCEPT 1029.034 km, PHRI00NGA ACCEPT 0.000 km
(self, excluded from selection); BKFP00NGA REJECT, ULAG00NGA REJECT,
UNEC00NGA BLOCKED (correctly never ranked above ACCEPT stations).
Navigation product `a6418387…aa7b2b` present on all candidates.
Network: 3 admitted references, geometry `EXTRAPOLATION`
(`EXTRAPOLATION_NOT_PERMITTED` under policy `v1.0`).

| Request | Mode | Status | Reason | Reference |
|---|---|---|---|---|
| AUTO | SINGLE_BASE | OK | SINGLE_BASE_SELECTED (fallback, VRS blocked: VRS_UPSTREAM_REVIEW_PENDING) | EKAK00NGA, 105.553 km, band preferred (PROVISIONAL) |
| VRS_ONLY | NO_CORRECTION | BLOCKED | VRS_UPSTREAM_REVIEW_PENDING | none |
| SINGLE_BASE_ONLY | SINGLE_BASE | OK | SINGLE_BASE_SELECTED | EKAK00NGA, 105.553 km |

VRS blockers (AUTO): `EXTRAPOLATION_NOT_PERMITTED`,
`NETWORK_NOT_ELIGIBLE`, `GEOMETRY_EXTRAPOLATION`,
`SPATIAL_MODEL_UNAVAILABLE`, `VRS_NOT_VALIDATED`,
`VRS_TARGET_LEAKAGE_UNASSESSED`.

## Held-out scientific test targets, 2024 DOY 026, AUTO

| Target | Mode | Status | Reference | Distance |
|---|---|---|---|---|
| ABFC00NGA | SINGLE_BASE | DEGRADED | PHRI00NGA | 470.870 km |
| EKAK00NGA | SINGLE_BASE | OK | PHRI00NGA | 105.553 km |
| MGBO00NGA | SINGLE_BASE | DEGRADED | ABFC00NGA | 689.687 km |

Ranking is QC-first: REJECT/BLOCKED neighbours are never selected over
farther ACCEPT stations. Distance bands are PROVISIONAL; every
single-base decision states no centimetre accuracy is claimed
(consistent with Phase 5 FLOAT-only metre-level evidence on these
baselines).

## Claims

Supported: the engine derives fail-closed, explainable decisions from
observed QC/navigation/coordinate evidence; VRS stays blocked
pre-review; single-base fallback selects the nearest ACCEPT reference
with honest PROVISIONAL distance expectations.

NOT claimed: VRS superiority, single-base centimetre accuracy, a
validated Nigerian network model, fixed ambiguities, or production
correction availability.
