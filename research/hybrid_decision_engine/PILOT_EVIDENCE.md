# Phase 8 Pilot Evidence — Real DOY 026 Decisions (Reviewed)

Reviewed pilot: Phase 6/7 scientific review COMPLETE.
Phase 6 reviewed `atm-2024d026-phri-target-geometry-v3`: best model
`zero` RMSE 3.076 m beats IDW 3.352 / nearest 3.757 / planar 14.373 m
(n=15948 identical samples; all four folds EXTRAPOLATION); BEST MODEL =
ZERO; no spatial interpolation model promoted. Historical figures
(zero 2.984 / IDW 3.546 / nearest 4.004 / planar 15.300 m, n=17768) are
SUPERSEDED.
Phase 7 reviewed: verdict APPROVED_WITH_PROVISIONAL_LIMITATIONS; mode
`ZERO / VRS_GEOMETRY_ONLY`; promoted spatial model NONE; target leakage
PASS; authoritative experiment `vrs-2024d026-phri-geometry-v3` (24,556
observations, 480/480 epochs, 30 GPS sats, EKAK anchor 105.553 km).
Operational corrected VRS remains NOT APPROVED (fail-closed).
Outcomes below are derived by the engine from observed evidence, not
hard-coded.

Engine: `nlgcp_hybrid_decision 0.1.0`, policy `v1.0`
(`hybrid-decision-policy-v1.json`).
Upstream fingerprints: Phase 6
`phase6-reviewed-geometry-v3-zero-3076-n15948` (model `zero`,
`REJECTED` for correction purposes); Phase 7
`phase7-reviewed-geometry-v3-phri-24556` (status `BLOCKED`
operational, validation `APPROVED_WITH_PROVISIONAL_LIMITATIONS`,
leakage `PASS`).
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
| AUTO | SINGLE_BASE | OK | SINGLE_BASE_SELECTED (fallback, VRS blocked: VRS_MODEL_NOT_VALIDATED) | EKAK00NGA, 105.553 km, band preferred (PROVISIONAL) |
| VRS_ONLY | NO_CORRECTION | BLOCKED | VRS_MODEL_NOT_VALIDATED | none |
| SINGLE_BASE_ONLY | SINGLE_BASE | OK | SINGLE_BASE_SELECTED | EKAK00NGA, 105.553 km |

VRS blockers (AUTO, reviewed): `EXTRAPOLATION_NOT_PERMITTED`,
`NETWORK_NOT_ELIGIBLE`, `GEOMETRY_EXTRAPOLATION`,
`SPATIAL_MODEL_REJECTED`, `VRS_BLOCKED`.
Pre-review blockers additionally included `SPATIAL_MODEL_UNAVAILABLE`,
`VRS_NOT_VALIDATED`, `VRS_TARGET_LEAKAGE_UNASSESSED` with reason
`VRS_UPSTREAM_REVIEW_PENDING` (SUPERSEDED).

AUTO decision fingerprint `737e0f0a…` (reviewed) differs from pre-review
`df11c341…`: old pre-review decisions are STALE (fingerprint-invalidated)
and must not be reused.

`OK` means all decision-engine admission gates passed for the selected
fallback; it does NOT claim centimetre positioning accuracy. Every
single-base decision states `no centimetre accuracy claimed`. The
105.553 km EKAK–PHRI baseline is the nearest admitted fallback under
PROVISIONAL distance policy, not a scientifically proven ideal RTK
distance: Phase 3 found EKAK→PHRI remained FLOAT-only
(horiz RMSE 0.968 m / 3D 1.130 m). Integrity `PASS` (admission) is
reported separately from expected positioning performance
(`PROVISIONAL`; FLOAT-only metre-level must be assumed).

Phase 9 handoff (AUTO): mode `SINGLE_BASE`, source/reference
`EKAK00NGA`, status `OK`, provenance carries reviewed Phase 6/7
fingerprints.

## Held-out scientific test targets, 2024 DOY 026, AUTO (pre-review reference)

Pre-review probes (STALE, retained for history): ABFC → PHRI 470.870 km
`DEGRADED`, EKAK → PHRI 105.553 km `OK`, MGBO → ABFC 689.687 km
`DEGRADED`. Ranking is QC-first: REJECT/BLOCKED neighbours are never
selected over farther ACCEPT stations. Distance bands are PROVISIONAL;
every single-base decision states no centimetre accuracy is claimed
(consistent with Phase 5 FLOAT-only metre-level evidence on these
baselines).

## Claims

Supported: the engine derives fail-closed, explainable decisions from
observed QC/navigation/coordinate evidence; automatic corrected VRS stays
blocked under reviewed evidence (no promoted interpolator; geometry-only
VRS diagnostic-only); single-base fallback selects the nearest ACCEPT
reference with honest PROVISIONAL distance expectations.

NOT claimed: validated spatial correction improvement, centimetre VRS
accuracy, ambiguity-fixed VRS, operational Nigerian network RTK,
single-base centimetre accuracy, production correction availability.
