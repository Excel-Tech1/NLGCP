# 14-Day Beta Sprint Tracker

**Sprint:** NLGCP 14-Day Beta Sprint  
**Tracked beta:** Internal, local, fixture-fed engineering integration beta  
**Start:** Day 1, 2026-11-23  
**Status rule:** A day is complete only when its deliverables and acceptance evidence exist. Future days are never pre-marked complete.

## 1. Status summary

| Day | Objective | Primary dependencies | Status |
|---|---|---|---|
| 1 | Audit, scope freeze, Day 1 deliverables | Repository baseline | Complete |
| 2 | RTCM 1005/1074/1084 synthetic encoder implementation | Day 1; RTKLIB reference layout | Complete |
| 3 | Independent RTCM conformance review | Day 2; synthetic vectors; independent decoder if available | Complete (RTKLIB v2.4.2-p13; non-RTKLIB second decoder unavailable) |
| 4-5 | Local Phase 12 lab caster | Day 3; synthetic artifact | Complete (loopback `127.0.0.1` caster + client + RTKLIB E2E; synthetic-only; committed at `459143e`) |
| 6 | End-to-end synthetic loopback integration | Day 4-5 | Complete (Phase 9/10/11/12 integration, admission & fault verification; 6 defects fixed; AC-01–AC-20 PASS) |
| 7 | Backend checkpoint and scope review | Day 6 | Not Started |
| 8 | Read-only Phase 13 status surface | Day 7 | Not Started |
| 9 | API/caster/local diagnostics integration | Day 8 | Not Started |
| 10 | Local observability and security hardening | Day 9 | Not Started |
| 11 | Compose deployment and field-readiness preparation | Day 10 | Not Started; hardware `UNKNOWN` |
| 12 | Initial field test or documented no-go | Day 11; scientific/field gates | Blocked by default |
| 13 | Field validation/troubleshooting or lab fault closure | Day 12 | Blocked by default |
| 14 | Beta review, acceptance decision, handover | Days 1-13 evidence | Not Started |

## 2. Day-by-day plan

### Day 1 - Audit and freeze

**Tasks**

- record branch, HEAD, worktree, and baseline;
- inspect Phases 11-16, API/web, services, database, Compose, CI, and scientific evidence;
- define the defensible beta class and non-goals;
- create the Day 1 deliverables;
- update `CURRENT_WORK.md`, `PROJECT_STATUS.md`, and `EVIDENCE_INDEX.md`;
- run the documentation-appropriate checks and record git status.

**Deliverables**

- `01-repository-audit.md`;
- `02-phase-readiness-matrix.md`;
- `03-scientific-readiness.md`;
- `04-beta-architecture.md`;
- `05-beta-acceptance-criteria.md`;
- `06-fourteen-day-tracker.md`;
- `07-day1-report.md`.

**Acceptance evidence**

- all seven documents exist and are internally consistent;
- no code or data changes outside documentation/status files;
- repository quality gate result recorded;
- no operational, field, accuracy, or live-service claim;
- Day 1 stop point recorded.

**Blockers**

- none for documentation;
- scientific and live-source gates remain blocked.

### Day 2 - RTCM 1005/1074/1084 synthetic encoder implementation

**Status:** Complete (2026-11-24). Report: `08-day2-report.md`.

**Objective**

Implement deterministic bit-level encoders for the three real Phase 11 message
families using an approved reference layout and clearly labelled synthetic
fixtures.

**Tasks completed**

- added 1005, 1074, and 1084 payload models and encoders;
- pinned layouts to RTKLIB v2.4.2-p13 source;
- added independent hardcoded payload/frame vectors and field-offset checks;
- strengthened admission so non-operational families require synthetic
  classification and a synthetic fixture flag;
- changed registry status to `SYNTHETICALLY_VALIDATED` for 1005/1074/1084;
- recorded semantic validation as `NOT_PERFORMED_NO_INDEPENDENT_DECODER`;
- ran focused and repository quality gates.

**Acceptance evidence**

- payload/frame vectors match the hardcoded expected bytes (using valid 1-based RTKLIB/RTCM GPS signals `2`/`9` and GLONASS signals `2`/`8`);
- 103 focused RTCM message tests + 14 scaffold tests pass (117 Phase 11 tests; 191 combined Phase 9/11 tests);
- `make check` passes (759 passed, 6 skipped; Ruff, ESLint, mypy 222 files,
  TypeScript, Go, CTest, Next.js);
- no operational, authentic-input, or scientific claim is made;
- no commit created.

**Limitations**

- no independent decoder was run;
- no authentic observation or coordinate was used;
- GLONASS FCN is not transported in 1084;
- 1005/1074/1084 are not `REAL_INPUT_VALIDATED` or
  `OPERATIONALLY_APPROVED`.

### Day 3 - Independent RTCM conformance review

**Status:** Complete (2026-11-24). Report: `09-day3-report.md`.

**Objective**

Determine what can honestly be validated without authentic RTCM and without
inventing message layouts or receiver behaviour.

**Tasks completed**

- compared the Phase 11 registry and message implementations against the
  technical baseline's message-matrix requirement (`16-rtcm-and-ntrip-correction-distribution.md`);
- verified shared CRC-24Q/framing behavior and message decoding against
  unmodified RTKLIB v2.4.2-p13 (`convbin` SHA-256 `b575f81e…` and read-only
  native C `input_rtcm3()` adapter);
- verified all 19 GPS and 7 GLONASS 1-based MSM signal-ID mappings and proved
  reserved Signal ID `1` is rejected as unknown (`"(1)"`) by RTKLIB;
- empirically confirmed standalone 1084 GLONASS FCN carrier-phase limitation
  (`L_cyc=0`) and verified sub-mm phase decoding with synthetic test FCNs;
- tested CRC flips, payload flips, truncated frames, bad preambles, wrong 1005
  length, `nsat*nsig > 64`, truncated MSM4 body, and lab message `4095`;
- recorded non-RTKLIB second decoder as NOT AVAILABLE and authentic RTCM
  semantic validation as `BLOCKED`.

**Deliverables**

- `09-day3-report.md`;
- `research/rtcm_generation/native/rtklib_rtcm_decode.c`,
  `src/nlgcp_rtcm_generation/independent_decoder.py`,
  `tests/test_independent_decoder.py`;
- updated `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`, and
  `02-phase-readiness-matrix.md`.

**Acceptance evidence**

- 201 focused RTCM tests passed with `RTKLIB_SOURCE=/home/excellence/RTKLIB`
  (10 independent decoder + 103 message + 14 scaffold + 74 Phase 9);
- `make check` passed (764 passed, 11 skipped; Ruff, ESLint, mypy 224 files,
  TypeScript, Go vet/tests, CTest, Next.js build);
- 1005/1074/1084 remain `SYNTHETICALLY_VALIDATED`; no operational, receiver,
  authentic-input, or positioning claim;
- authentic input remains explicitly `BLOCKED`; no commit created.

**Primary blockers**

- no admitted authentic RTCM capture;
- no second non-RTKLIB decoder (`pyrtcm`, BKG BNC, or hardware receiver)
  installed/available.

### Day 4-5 - Local Phase 12 lab caster and client integration

**Status:** Complete (2026-11-24). Report: `10-phase12-ntrip-implementation.md`.

**Objective**

Implement a loopback-only (`127.0.0.1`) NTRIP v2/v1 caster and authenticated
local client connecting the Phase 11 synthetic RTCM `1005`/`1074`/`1084`
pipeline to independent RTKLIB validation.

**Tasks completed**

- implemented loopback-only `LocalNtripCaster` (`GET /`, `GET /NLGCP_TEST`,
  `POST`, `SOURCE`), constant-time Basic auth (`CredentialStore`), synthetic
  mountpoint registry (`NLGCP_TEST`), Phase 9 CRC-24Q/framing publication gate,
  bounded FIFO `MountpointBroker`, 5-dimension diagnostics, and `LocalNtripClient`
  with bounded exponential backoff under `services/correction-service/`;
- created safe local example config `services/correction-service/.env.example`
  and reproducible CLI demo `scripts/run_phase12_lab_demo.py`;
- verified end-to-end synthetic `1005/1074/1084 -> NLGCP_TEST -> Client ->
  RTKLIB convbin & input_rtcm3` over NTRIP v2 and v1 plus 1-byte TCP splits
  and all 12 required negative/resilience scenarios (AC-01 through AC-18).

**Deliverables**

- `services/correction-service/src/nlgcp_correction_service/` and `tests/` (29 tests);
- `services/correction-service/.env.example`, `services/correction-service/README.md`,
  `scripts/run_phase12_lab_demo.py`;
- `docs/sprints/14-day-beta-sprint/10-phase12-ntrip-implementation.md`;
- updated `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`, and
  `02-phase-readiness-matrix.md`.

**Acceptance evidence**

- CLI demo `ok=true`, `byte_exact_match=true`, RTKLIB `convbin` + native
  `input_rtcm3` semantic verification PASS;
- 230 focused Phase 9/11/12 tests passed with `RTKLIB_SOURCE=/home/excellence/RTKLIB`;
- `make check` passed (792 passed, 12 skipped; Ruff, ESLint, mypy 237 files,
  TypeScript, Go vet/tests, CTest, Next.js build);
- strictly `127.0.0.1` loopback-only and `SYNTHETIC_TEST_ONLY`; no commit created.

**Primary blockers**

- operational caster exposure, TLS, production auth/entitlements (Phases 13/15),
  authentic CORS/RTCM source, non-RTKLIB decoder, and commercial receiver/field
  validation remain blocked.

### Day 6 - End-to-end synthetic loopback integration

**Status:** Complete (2026-11-25). Report: `11-day6-integration-assurance.md`.

**Objective**

Exercise and verify Phase 9 -> Phase 10 -> Phase 11 -> Phase 12 local loopback integration, admission controls, fault propagation, diagnostics separation, and lifecycle resource safety without external network dependencies.

**Tasks completed**

- verified Day 1–3 (`8d10f30`) and Day 4–5 (`459143e`) Git checkpoints cleanly before edits;
- audited Phase 9/10/11/12 boundaries and fixed 6 discovered admission/concurrency/fault-propagation defects (`validation.py`, `publisher.py`, `caster.py`, `diagnostics.py`, `client.py`);
- added 26 Day 6 integration assurance tests (`services/correction-service/tests/test_day6_integration_assurance.py`; 55 Phase 12 tests total) covering multi-client byte-exact isolation, irregular TCP splits, recovery+RTKLIB decode, all 12 admission gates, all 14 fault scenarios, 5 distinct diagnostic categories, and 10-step resource cleanup;
- enhanced `pipeline.py` and `scripts/run_phase12_lab_demo.py` with 10-stage human + machine-readable output carrying the explicit synthetic data notice;
- ran focused `RTKLIB_SOURCE` verification (`350 passed, 0 skipped`), CLI demo, `make check` (`817 passed, 13 skipped`), and `git diff --check`.

**Deliverables**

- `docs/sprints/14-day-beta-sprint/11-day6-integration-assurance.md`;
- `services/correction-service/tests/test_day6_integration_assurance.py`;
- targeted hardening in `services/correction-service/src/nlgcp_correction_service/{validation,publisher,caster,diagnostics,client,pipeline}.py` and `scripts/run_phase12_lab_demo.py`;
- updated `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`, and `02-phase-readiness-matrix.md`.

**Acceptance evidence**

- all 20 Day 6 acceptance criteria (AC-01–AC-20) PASS;
- focused Phase 9/10/11/12 suite with `RTKLIB_SOURCE=/home/excellence/RTKLIB`: `350 passed, 0 skipped`;
- `make check`: PASS (`817 passed, 13 skipped`, mypy 238 source files, Ruff, ESLint, TypeScript, Go vet/tests, CTest, Next.js build);
- no external network connection, no operational/VRS/accuracy claim, no commit or push created.

### Day 7 - Backend checkpoint

**Objective**

Stop and review before building the status surface.

**Tasks**

- run focused Python/Go/web tests relevant to the beta;
- review the Day 6 transcript and any gaps;
- confirm the local caster is genuinely loopback-only;
- decide: continue, reduce scope, or stop.

**Deliverable**

- checkpoint record with test results, open gaps, and decision.

**Acceptance criteria**

- no open Must failure;
- no accidental operational capability;
- scope remains synthetic-only.

### Day 8 - Read-only Phase 13 status surface

**Objective**

Expose local service state without creating a production control plane.

**Tasks**

- add versioned read-only status routes under `/api/v1`;
- type the response schemas;
- show service state, mountpoint state, classification, and scientific-validity status;
- update the local web page to display the same information;
- keep authentication out of scope while preventing public exposure.

**Deliverables**

- API routes, typed schemas, tests, and OpenAPI evidence;
- local UI state page;
- explicit synthetic/blocked labels.

**Acceptance criteria**

- only synthetic/blocked status is possible;
- no real user data, entitlement, or credential flow;
- no claim that process health equals correction availability;
- UI/API make the scientific limitation obvious.

### Day 9 - Integration of status and diagnostics

**Objective**

Connect the local caster, API, and diagnostics into one reproducible local flow.

**Tasks**

- expose session/mountpoint summaries from the caster to the status surface;
- correlate local session/request identifiers in logs;
- test API/caster failure and recovery paths;
- record a complete local walkthrough.

**Deliverables**

- integration test and walkthrough;
- updated architecture/status notes.

**Acceptance criteria**

- no silent state divergence between caster and status surface;
- failed/stale sessions are visible;
- scientific validity remains `NOT_ASSESSED`.

### Day 10 - Local observability and security hardening

**Objective**

Add the minimum diagnostics and guardrails needed for an internal beta.

**Tasks**

- add structured logs and counters for connections, bytes, frames, CRC failures, buffer high-water marks, and rejects;
- ensure logs do not contain credentials;
- review container users, port bindings, and Compose exposure;
- add or verify secret scanning and dependency/security checks;
- document the absence of full Phase 14 SLOs and Phase 15 production controls.

**Deliverables**

- diagnostics evidence and configuration review;
- phase-gap note.

**Acceptance criteria**

- no secrets in source/logs/images;
- no public port;
- transport success is never labelled scientific validity;
- no invented SLO or availability value.

### Day 11 - Deployment and field-readiness preparation

**Objective**

Make the local stack reproducible and record field prerequisites without inventing them.

**Tasks**

- add the local correction service to a Compose profile or document why it stays outside Compose;
- run healthchecks and clean shutdown;
- record hardware/rover/receiver/antenna/firmware availability as `UNKNOWN` unless evidence exists;
- create a field no-go checklist tied to the scientific and security gates.

**Deliverables**

- Compose/deployment evidence;
- `hardware-and-field-readiness` note with explicit unknowns;
- no fabricated hardware inventory.

**Acceptance criteria**

- reproducible local startup/stop;
- no production deployment claim;
- field prerequisites are explicit and unmet where evidence is absent.

### Day 12 - Initial field test or documented no-go

**Objective**

Either execute an authorized field test with documented controls, or record a formal no-go.

**Tasks**

- verify hardware, site permission, control coordinates, correction source, and safety prerequisites;
- if any prerequisite is missing, do not test; record `NO_GO` with reasons;
- if authorized, execute a bounded test using only approved data and record raw evidence.

**Deliverables**

- field test record or no-go record;
- evidence manifest;
- no synthetic substitution.

**Acceptance criteria**

- no field action without authorization and controls;
- no accuracy/FIX/availability claim from a non-field or synthetic test;
- every field observation traceable to authentic data.

**Default status**

- Blocked. Hardware is `UNKNOWN`; authentic correction and coordinate gates are unresolved.

### Day 13 - Field validation/troubleshooting or lab fault closure

**Objective**

If Day 12 was a no-go, close remaining lab failure modes and document the field gap. If a field test occurred, validate only the recorded evidence.

**Tasks**

- run the frozen lab fault matrix: disconnect, stale stream, CRC failure, malformed frame, buffer pressure, caster restart, client reconnect;
- record outcomes and residual risks;
- if field evidence exists, compare against documented criteria without inventing thresholds;
- update blockers and handover.

**Deliverables**

- fault-matrix results;
- field-validation note or explicit `NOT_PERFORMED` statement;
- updated risk register.

**Acceptance criteria**

- no test result is extrapolated beyond its data;
- no scientific threshold is added without evidence and review;
- unresolved prerequisites remain visible.

### Day 14 - Beta review, acceptance decision, and handover

**Objective**

Decide whether the internal engineering beta is accepted, accepted with gaps, or rejected.

**Tasks**

- verify every Must acceptance criterion against evidence;
- confirm all scientific/operational claims remain blocked;
- record residual Phase 12-16 gaps;
- provide a reproducible handover: commands, architecture, evidence, known failures, and stop conditions;
- update status/evidence documents.

**Deliverables**

- beta review record;
- acceptance decision;
- handover and residual-risk register;
- final git status report.

**Acceptance criteria**

- decision uses the Day 1 acceptance criteria;
- no operational promotion;
- no real-user, field, or accuracy claim;
- all evidence paths and limitations are recorded.

## 3. Dependency graph

```text
Day 1 audit
  |
  +--> Day 2-3 RTCM implementation and review
  |        |
  |        +--> Day 4-5 local caster --> Day 6 loopback --> Day 7 checkpoint
  |                                                          |
  |                                                          +--> Day 8 status API/UI
  |                                                                    |
  |                                                                    +--> Day 9 integration
  |                                                                              |
  |                                                                              +--> Day 10 diagnostics/security
  |                                                                                        |
  |                                                                                        +--> Day 11 deployment/field prep
  |                                                                                                  |
  |                                                                                                  +--> Day 12 field/no-go
  |                                                                                                            |
  |                                                                                                            +--> Day 13 validation/fault closure
  |                                                                                                                      |
  |                                                                                                                      +--> Day 14 review
  |
  +--> scientific/operational gates (coordinate evidence, authentic input, promoted model,
       independent validation, hardware/field acceptance) --> required for any operational beta,
       independent of the engineering track
```

## 4. Global stop conditions

Stop and reassess if any of the following occurs:

- a request would emit `OPERATIONAL_APPROVED`;
- a real mountpoint, real credential, or external user is introduced;
- synthetic data is proposed as a substitute for authentic observations;
- a field/accuracy/availability claim is requested without evidence;
- the caster would need a public bind or production authentication;
- Phase 9/10/11 evidence conflicts with this audit;
- the implementation requires an architecture change not covered by the baseline or an ADR.
