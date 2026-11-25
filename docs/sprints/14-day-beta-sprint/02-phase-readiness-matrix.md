# Phase 11-17 Readiness Matrix

**Sprint:** NLGCP 14-Day Beta Sprint  
**Day:** 1 - audit and freeze  
**Date:** 2026-11-23  
**Status:** Day 1 deliverable

## 1. Status vocabulary

| Status | Meaning in this matrix |
|---|---|
| Complete | Evidence exists for the stated scope; this does not imply operational approval |
| In Progress | Some implementation or evidence exists, but the phase is not complete |
| Not Started | No implementation or evidence for the phase objective exists |
| Blocked | The next required evidence cannot be produced without an external prerequisite or a scientific gate |

`SCAFFOLDED`, `SYNTHETICALLY_VALIDATED`, and `OPERATIONALLY_APPROVED` are Phase 11 registry states, not general phase-completion states.

## 2. Prerequisite and phase matrix

| Phase | Repository status | Observed implementation or evidence | Blocking condition | Permitted beta role |
|---|---|---|---|---|
| Phase 10 - Live CORS ingestion | Complete engineering; real live validation Blocked | Go `internal/ntrip` client library, Python research bridge, capture and synthetic loopback evidence | No authorized live CORS/NTRIP source; `cors-*.rtcm3` files under the home directory lack admitted provenance | Reuse transport concepts and local test harness; do not claim live ingestion |
| Phase 11 - RTCM correction generation | In Progress; synthetic key-message encoders verified with RTKLIB v2.4.2-p13 | Admission gates, message-family registry, field/bit primitives, 1005/1074/1084 bit-level encoders, synthetic 4095 encoder, Phase 9 framing adapter, RTKLIB `convbin` + native `input_rtcm3` independent decoder harness, provenance, Phase 12 handoff schema, 127 synthetic-only package tests | VRS not approved; single-base lacks authentic input; no second non-RTKLIB decoder or receiver test; GLONASS FCN not transported in 1084 | Produce clearly labelled synthetic frames for local integration tests only; no operational or authentic-input claim |
| Phase 12 - NTRIP correction service | In Progress; local loopback synthetic lab caster + client & Day 6 integration/fault assurance verified | `services/correction-service/src/nlgcp_correction_service/` (`127.0.0.1` NTRIP v2/v1 caster, constant-time Basic auth, `NLGCP_TEST` synthetic mountpoint, fail-closed Phase 11 handoff publisher with mandatory `CorrectionStreamArtifact` and `MessageFamilyRegistry` gating, authenticated client with bounded reconnect, 5-dimension diagnostics, 55 tests, 10-stage CLI demo); end-to-end RTKLIB `convbin` + native `input_rtcm3` verified on synthetic 1005/1074/1084 plus all Day 6 admission/fault/lifecycle checks (`11-day6-integration-assurance.md`) | Loopback-only synthetic lab service; no public caster, TLS, production auth/entitlements, authentic CORS source, or commercial receiver validation | Local loopback synthetic integration testing only; no public, operational, or authentic-correction claim |
| Phase 13 - Basic user platform | Not Started | FastAPI health endpoint only; static Next.js placeholder; Phase 2 metadata tables; no auth, entitlement, device, or session schema | No control-plane implementation; no identity model; no real correction data | Read-only local status/health surface and explicit synthetic labels only |
| Phase 14 - Monitoring and operations | Not Started | No Prometheus, Grafana, Alertmanager, SLO, dashboard, or central log configuration; only process health endpoints and Compose healthchecks | No metrics pipeline or scientific health model; no operational service to monitor | Add local diagnostics and structured logs without claiming SLOs or operational health |
| Phase 15 - Security and hardening | Not Started | CI CodeQL and dependency review; localhost port bindings; environment-backed development secrets; non-root container users; NTRIP client TLS validation and redaction | No platform identity, RBAC/ABAC, managed secrets, TLS termination, audit trail, rate limiting, container scan, or secret scan | Keep beta loopback-only; do not create production credentials or expose services |
| Phase 16 - Field validation | Not Started | No field plan, rover/receiver inventory, control-point survey, interoperability records, or field evidence | Hardware availability `UNKNOWN`; coordinate gate unresolved; no authentic correction | No field test unless independently authorized and evidenced; lab fault tests only |
| Phase 17 - Controlled MVP pilot | Not Started; outside this sprint | No implementation | Requires Phases 12-16 and an accepted scientific/operational gate | Out of scope |

## 3. Phase 11 detail

### 3.1 Message-family registry

| Family ID | Message | Registry status | Encoder status | Beta interpretation |
|---|---|---|---|---|
| `REFERENCE_STATION_1005` | 1005 | `SYNTHETICALLY_VALIDATED` | `ReferenceStation1005Encoder`; synthetic vectors | Bit-level synthetic payload only; no independent-decoder or authentic-input claim |
| `MSM4_GPS_1074` | 1074 | `SYNTHETICALLY_VALIDATED` | `GpsMsm4Encoder`; synthetic vectors | Bit-level synthetic payload only; no GPS MSM operational output |
| `MSM4_GLONASS_1084` | 1084 | `SYNTHETICALLY_VALIDATED` | `GlonassMsm4Encoder`; synthetic vectors | Bit-level synthetic payload only; no GLONASS FCN transport or operational output |
| `SYNTHETIC_TEST_FRAME` | 4095 | `SYNTHETICALLY_VALIDATED` | `SyntheticMessageEncoder` | Lab payload only; explicitly not navigable RTCM |

No family is `REAL_INPUT_VALIDATED` or `OPERATIONALLY_APPROVED`.

### 3.2 Admission behavior

`admit_request` fails closed when any of the following is observed:

- a non-admissible or incomplete decision;
- missing decision/request/source provenance;
- an unadmitted or unverified input source;
- unverified station identity;
- missing or unverified coordinate provenance;
- missing GNSS epoch;
- missing GNSS systems, message family, or encoder version;
- unapproved correction model;
- VRS mode under the current non-operational state;
- `OPERATIONAL_APPROVED` output classification;
- an unsupported family or a family without an encoder;
- a synthetic family request without the explicit synthetic-fixture flag;
- any non-operational family without `SYNTHETIC_TEST_ONLY` classification;
- a synthetic request whose coordinate verification state is not
  `SYNTHETIC_TEST_ONLY`.

`NO_CORRECTION` produces no frames. The synthetic encoder requires
`SYNTHETIC_TEST_ONLY`, an explicit fixture flag, and emits the text label
`SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS`.

### 3.3 Validation boundary

The generator delegates framing to the Phase 9 `0xD3`/10-bit-length/CRC-24Q
path. Validation returns `semantic_validation =
NOT_PERFORMED_SYNTHETIC_PAYLOAD` for message 4095 and
`NOT_PERFORMED_NO_INDEPENDENT_DECODER` for 1005/1074/1084. A successful frame
parse therefore proves only internal framing agreement, not RTCM conformance,
message semantics, receiver compatibility, or positioning validity.

### 3.4 Phase 12 handoff

`CorrectionStreamArtifact` is a versioned schema only. It contains stream/decision identity, mode, station identity fields, message families, generation status, frame source, validity interval, classification, and provenance fingerprint. It does not implement transport, accounts, mountpoints, caster sessions, or public/private service exposure.

## 4. Phase 12-16 detail

### 4.1 Phase 12 - NTRIP correction service

Required by the technical baseline:

- RTCM 3.x/MSM boundary where supported;
- NTRIP transport and a stable mountpoint catalogue;
- source and rover authentication/entitlement;
- connection/session limits, revocation, and audit events;
- service status that reflects scientific availability;
- receiver/interoperability testing before brand support is claimed.

Observed state: placeholder README only. No caster is present in `compose.yml`.

### 4.2 Phase 13 - Basic user platform

Required by the technical baseline:

- versioned REST endpoints under `/api/v1`;
- identity, organisations, devices, plans/entitlements, NTRIP credential lifecycle, coverage, sessions, status, support, and audit;
- a Next.js/TypeScript frontend that consumes the API;
- role-appropriate access and separation of control and correction planes.

Observed state: only `GET /health`; static web placeholder; Phase 2 metadata tables; no identity or entitlement schema. This is a Phase 1 foundation, not a basic user platform.

### 4.3 Phase 14 - Monitoring and operations

Required by the technical baseline:

- station/ingest, GNSS quality, processing, distribution, and platform metrics;
- Prometheus, Grafana, and Alertmanager;
- structured, correlated logs;
- SLOs for availability, correction age, processing latency, station availability, caster success, incident response, and validated scientific performance;
- alerts based on user/scientific impact.

Observed state: process-level health only. Existing client metrics counters are local data structures, not an exported monitoring service.

### 4.4 Phase 15 - Security and hardening

Required by the technical baseline:

- network zones and separation of public edge, application, GNSS processing, data, and administration;
- separate web identities and NTRIP/device credentials;
- RBAC/ABAC and service entitlements;
- managed secret storage with rotation;
- privileged, audited coordinate/configuration changes;
- audit logging and location-data minimization;
- threat modelling, dependency scanning, container scanning, secret detection, auth tests, network exposure review, backup/restore, and incident exercises.

Observed state: CodeQL and dependency review in CI, NTRIP TLS validation, redaction, localhost bindings, and non-root containers. These are useful development controls but do not satisfy the Phase 15 release gate.

### 4.5 Phase 16 - Field validation

Required by the technical baseline:

- hardware-in-loop NTRIP rover tests;
- geodetic field validation;
- receiver firmware/profile and GGA behaviour records;
- control-point acceptance and documented accuracy/latency evidence;
- resilience and interoperability tests.

Observed state: no field evidence and no hardware inventory. Hardware availability must remain `UNKNOWN` until independently recorded.

## 5. Dependency matrix

| Dependency | Required by | Current state |
|---|---|---|
| Approved synthetic Phase 11 artifact | Phase 12 local lab caster; Phase 13 status; Phase 14 diagnostics | Available as a scaffold, not operational |
| Local Phase 12 caster | Phase 12 integration; Phase 13 session/status display; Phase 14 distribution metrics | Absent |
| Versioned Phase 13 API | Operator status surface and integration tests | Absent |
| Metrics/logging boundary | Phase 14 diagnostics and beta acceptance | Absent beyond process health |
| Authentic RTCM capture | Phase 11 real-input validation; Phase 12 real correction distribution | Blocked |
| Authorized live NTRIP source | Phase 10 live validation; real-time beta | Blocked |
| Verified coordinate/frame/epoch/reference-point evidence | Phase 8/11 operational decisions; Phase 16 field acceptance | Blocked |
| Promoted correction model | Operational VRS | Blocked; Phase 6 BEST=ZERO; Phase 7 geometry-only |
| Rover/receiver hardware and field plan | Phase 16 | `UNKNOWN` |
| Independent RTCM decoder | Real message conformance | Absent |

Critical engineering path:

`Phase 11 synthetic artifact -> Phase 12 local lab caster -> Phase 13 status surface -> Phase 14 local diagnostics -> Day 7/14 engineering review`

The scientific/operational path is independent and cannot be completed by that engineering path:

`verified coordinates + authentic input + promoted model + independent validation + rover acceptance -> operational correction approval`

## 6. Day 1-2 verdict

Phases 12, 13, 14, 15, and 16 are not started. Phase 11 is an in-progress
research package with synthetic-only 1005/1074/1084 encoders and a synthetic
4095 test encoder; no independent decoder validation has been performed.
Phase 10's transport library is engineering-complete but not live-operational.

The sprint may build a local synthetic integration beta if it preserves these boundaries:

- no operational mountpoint;
- no real user or credential;
- no real correction claim;
- no `OPERATIONAL_APPROVED` classification;
- no field or accuracy claim;
- no substitution of synthetic observations for unavailable authentic data.
