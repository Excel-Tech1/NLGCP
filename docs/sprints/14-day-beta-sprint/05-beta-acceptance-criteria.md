# Beta Acceptance Criteria

**Sprint:** NLGCP 14-Day Beta Sprint  
**Day:** 1 - audit and freeze  
**Date:** 2026-11-23  
**Beta class:** Internal, local, fixture-fed engineering integration beta  
**Status:** Day 1 deliverable; all criteria remain unmet until independently evidenced

## 1. Rules for these criteria

- A criterion is satisfied only by recorded, reproducible evidence.
- A synthetic label is mandatory wherever synthetic material is used.
- No numeric accuracy, availability, latency, FIX-rate, or SLO threshold is introduced here. Such values require field evidence and review.
- Passing engineering tests does not open a scientific or operational gate.
- No future task may be marked complete merely because code exists.

## 2. Entry criteria

| ID | Criterion | Evidence required | Status at Day 1 |
|---|---|---|---|
| EN-01 | Day 1 audit and scope documents are complete | This sprint directory, status/evidence updates, and Day 1 report | Met by this deliverable set after final checks |
| EN-02 | Work is isolated on the beta branch from the recorded baseline | Branch name, HEAD, and clean-start record | Met at audit start |
| EN-03 | No implementation relies on unavailable authentic data or hardware | Evidence ledger shows `BLOCKED` or `UNKNOWN`, not substitutes | Must be maintained throughout |
| EN-04 | A local-only deployment scope is documented | Architecture map and Compose/network constraints | Met by Day 1 documents |

## 3. Must-pass acceptance criteria

| ID | Priority | Criterion | Required evidence | Failure condition |
|---|---|---|---|---|
| AC-01 | Must | Every generated frame, session, log, and UI surface is labelled synthetic when it originates from fixtures | Searchable label in frame payload, API/UI, and logs; test assertion | Any unlabelled synthetic output |
| AC-02 | Must | `OPERATIONAL_APPROVED` cannot be emitted or accepted by the beta path | Admission/negative test and generated output inspection | Any operational classification |
| AC-03 | Must | Phase 11 admission fails closed for missing provenance, unverified coordinates, unverified station identity, unavailable source, unapproved model, and unsupported family | Focused negative tests covering each reason code | A request proceeds without required evidence |
| AC-04 | Must | Framing accepts only a well-formed `0xD3` frame with valid length and CRC-24Q; malformed/truncated/CRC-invalid input is rejected or quarantined | Deterministic framing tests and negative cases | Invalid bytes are forwarded as valid |
| AC-05 | Must | A local Phase 12 caster, if implemented, serves only a documented synthetic mountpoint over loopback and exposes its source table state | Local integration test and captured request/response | Public bind, unknown mountpoint served, or operational claim |
| AC-06 | Must | A local test client can connect, receive labelled synthetic frames, and report connection/frame/CRC status without claiming a position | Loopback integration transcript and counters | Client output implies a real rover or correction result |
| AC-07 | Must | Buffer exhaustion, disconnect, stale stream, and invalid input have explicit, tested behavior; no silent frame loss is allowed | Fault-injection tests and recorded outcome | Silent drop, fabricated continuation, or healthy status after failure |
| AC-08 | Must | The status/API surface exposes at least: service state, mountpoint state, classification, and scientific-validity status | API test and UI snapshot or request/response record | Status hides the synthetic/blocked state |
| AC-09 | Must | The API uses a versioned boundary under `/api/v1` for new beta status routes and generates typed OpenAPI schemas | OpenAPI document and route test | Unversioned or untyped control-plane route |
| AC-10 | Must | Authentication/authorisation is not simulated as production-ready; local test access is isolated and not committed | Configuration review and secret scan | Real credential, default reusable password, or public exposure |
| AC-11 | Must | All beta services are loopback-only or on an isolated Compose network; no public ingress is added | Compose configuration and port review | External interface exposure |
| AC-12 | Must | No real CORS/NTRIP source, real rover, or field result is claimed or implied | Evidence ledger and UI copy review | Live/field/accuracy claim |
| AC-13 | Must | Unit, replay, integration, and fault tests for the beta path pass; deterministic outputs are reproducible | Test command, output, and artifact hashes where applicable | Failure, unexplained skip, or non-deterministic output |
| AC-14 | Must | The complete repository quality gate passes after implementation | `make check` output | Regression in lint, typing, tests, build, or Compose syntax |
| AC-15 | Must | Evidence is stored with provenance, labels, and explicit limitations; no raw GNSS data is modified | Evidence manifest and `git diff` review | Missing provenance, altered raw data, or invented result |
| AC-16 | Must | Day 14 review explicitly decides whether the internal engineering beta is accepted; it cannot approve an operational service | Review record with accepted/rejected scope and residual blockers | Implicit promotion or operational claim |

## 4. Should-pass diagnostic criteria

| ID | Priority | Criterion | Required evidence |
|---|---|---|---|
| AC-17 | Should | Structured logs carry local session/request identifiers and distinguish transport success from scientific validity | Log samples and field review |
| AC-18 | Should | Counters cover connection attempts, successful connections, frames received, CRC failures, bytes, buffer high-water mark, and dropped/rejected counts | Metrics/log output |
| AC-19 | Should | A local operator can see blocked reasons and the last observed failure without reading source code | UI/API response |
| AC-20 | Should | CI adds the beta integration test without network access | CI job definition and successful local run |
| AC-21 | Should | The Compose stack starts, passes healthchecks, and stops cleanly | Recorded command output |
| AC-22 | Should | The Day 14 handover records every remaining Phase 12-16 gap | Handover document |
| AC-23 | Should | Synthetic 1005/1074/1084 payloads match hardcoded independent vectors and explicit field offsets; registry status remains `SYNTHETICALLY_VALIDATED` and semantic validation remains `NOT_PERFORMED_NO_INDEPENDENT_DECODER` | `test_rtcm_messages.py`, Day 2 report, registry output | Mismatched vector, unsupported/operational status, or a claim of independent decoder/receiver validation |

## 5. Scientific and operational non-acceptance

The following are explicitly not acceptance criteria and cannot be used to declare the beta successful:

- RTK FIX or fixed-ambiguity performance;
- horizontal, vertical, or 3D accuracy;
- TTFF or loss-of-fix recovery in the field;
- correction age or latency against a real rover;
- VRS or NRTK improvement;
- live CORS availability;
- receiver compatibility with Leica, Trimble, Topcon, Emlid, CHCNAV, South, Hi-Target, or any other vendor;
- production authentication, billing, entitlements, or service-level commitments;
- any field result.

These require separate reviewed evidence under the technical baseline.

## 6. Exit decision

The Day 14 decision has three permitted outcomes:

1. **Internal engineering beta accepted** - all Must criteria met; all scientific/operational claims remain blocked.
2. **Internal engineering beta accepted with documented gaps** - only non-scientific engineering gaps remain; the missing authentic/field evidence is explicit.
3. **Beta rejected** - one or more Must criteria fail or a scientific/operational claim cannot be withdrawn.

No outcome may promote the beta to a public, field, or operational correction service.
