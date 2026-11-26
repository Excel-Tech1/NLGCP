# Day 7 — Scientific Readiness, Beta Readiness Assessment, and Technical Debt Matrix

- **Sprint:** NLGCP 14-Day Beta Sprint (Local Engineering Integration Beta)
- **Day:** 7 — Backend Checkpoint and Scope Review
- **Date:** 2026-11-25
- **Branch:** `research/nlgcp-14-day-beta-sprint`
- **HEAD Commit:** `0cea5ba` (`Complete Day 6 synthetic integration assurance`)
- **Assessed Release Class:** `NLGCP Local Engineering Integration Beta v0.1` (internal, local, fixture-fed engineering beta — **NOT** an operational correction service)

---

## 1. Workstream E — Scientific Readiness Review

### 1.1 Preserved Authoritative Scientific Controls (Unchanged)

No scientific thresholds, atmospheric models, VRS algorithms, reference frames, or raw GNSS observations were modified during Days 1–7:

- **Phase 6 (Atmospheric & Spatial Error Model):** `BEST = ZERO` (identical-sample LOOCV `n=15,948` on DOY 2024/026 `*-geometry-v3`: zero RMSE `3.076 m` beats IDW `3.352 m`, nearest `3.757 m`, planar `14.373 m`; all four folds proven `EXTRAPOLATION`; no spatial interpolator promoted).
- **Phase 7 (Offline VRS Generator):** `VRS_STATUS = VRS_GEOMETRY_ONLY`, `VRS_GENERATION = ZERO` (scientific review `APPROVED_WITH_PROVISIONAL_LIMITATIONS`; `78,060` virtual observations across 4 DOY 026 rotations; positioning validation not performed; operational corrected VRS NOT APPROVED).
- **Phase 8 (Hybrid Decision Engine):** Reviewed DOY 026 policy blocks automatic VRS (`VRS_MODEL_NOT_VALIDATED`); single-base fallback remains restricted by FLOAT-only historical evidence (`105.553 km` EKAK->PHRI control `0.968 m` horiz RMSE, `fix_rate = 0.0`; no centimetre claim).
- **Phase 11 (RTCM Correction Generation):** Registry status for `1005`, `1074`, `1084`, and `4095` remains `SYNTHETICALLY_VALIDATED`. Zero families are `REAL_INPUT_VALIDATED` or `OPERATIONALLY_APPROVED`.
- **Operational Approval Gate:** `OPERATIONAL_APPROVED = FORBIDDEN` across Phase 11 admission, Phase 12 validation, and Phase 12 mountpoint policy.

### 1.2 Backend Architectural Preparedness for Future Atmospheric Modelling & VRS

**Assessment:** The current modular separation (`Phase 6/7 science -> Phase 8 decision contracts -> Phase 11 generation/handoff -> Phase 12 broker/caster`) **is structurally sound and can accommodate future atmospheric modelling and VRS generation without major architectural restructuring**, provided new typed interfaces are added at the boundaries below.

| Gap Category | What Exists Today | What Is Missing for Future Authentic / VRS Operation |
|---|---|---|
| **1. Atmospheric model interfaces** | Offline Phase 6 `SpatialCorrectionAssessment` summary contract consumed by Phase 8 (`models.py`) | Real-time epoch-level ionospheric/tropospheric correction payload interface (per-satellite slant/dispersive & non-dispersive terms, uncertainty/validity horizon, age-of-model, and extrapolation flag) passed from an online estimator to Phase 7/11 |
| **2. Correction metadata** | `CorrectionStreamArtifact` carries `stream_id`, `decision_id`, `mode`, `station_id`, `virtual_station_id`, `message_families`, `classification`, `provenance_fingerprint` | Datum/ITRF realization epoch, antenna phase-center/ARP offset metadata, correction age/latency, atmospheric model ID & applicability domain, and per-epoch GNSS time validity windows (`validity_start`/`validity_end` are currently `None`) |
| **3. Observation provenance** | Static string fingerprints (`input_source_fingerprint`) in Phase 11 requests | Cryptographically linked real-time capture/epoch lineage tracing every emitted RTCM frame back to authenticated Phase 10 live CORS frame hashes, arrival timestamps, and Phase 4 online QC status |
| **4. Station-coordinate dependencies** | `CoordinateProvenance` requires `verification_state == SYNTHETIC_TEST_ONLY` for synthetic runs or `VERIFIED` for real runs | Authoritative multi-epoch verified IGS20/ITRF coordinate registry with formal uncertainty, monument/ARP identity, and observation-epoch realization (currently only 4 stations on DOY 2024/026 have verified PRIDE PPP-AR coordinates; Southern 2011 stations remain provisional) |
| **5. VRS observation-generation interfaces** | Offline Phase 7 `nlgcp_vrs` generates zero-correction synthetic observations from RINEX files (`geometry-v3`) | Real-time epoch-streaming VRS observation synthesizer accepting rover approximate ECEF/LLH + multi-reference synchronized epochs + validated atmospheric corrections, emitting per-epoch double-difference-consistent observables into Phase 11 encoders |
| **6. RTCM message families & capabilities** | Bit-level synthetic encoders for `1005`, GPS MSM4 `1074`, GLONASS MSM4 `1084`, and lab `4095` | Station/antenna descriptors (`1006` ARP+height, `1007`/`1008`/`1033` antenna/receiver), GLONASS code-phase bias `1230` & ephemerides (`1019`/`1020`, solving standalone 1084 FCN absence), Galileo/BeiDou MSM4/MSM7 (`1094`/`1124`/`1077`/`1087`), and optional SSR/network residual messages |
| **7. NTRIP routing for future VRS** | Static mountpoint fan-out (`MountpointBroker` broadcasts identical frames to all subscribers on `NLGCP_TEST`) | Rover NMEA-0183 GGA sentence parsing on client uplink, per-rover dynamic virtual-station session routing (unicast per-client VRS queues rather than shared broadcast), and stale-GGA fallback policy |
| **8. Independent validation interfaces** | Unmodified RTKLIB v2.4.2-p13 (`convbin` + native `input_rtcm3`) on synthetic bytes | Second non-RTKLIB RTCM decoder (`pyrtcm` or BKG BNC), automated real-time RTKLIB `rtkrcv` / commercial-receiver HIL positioning harness, and formal zero-baseline/short-baseline RTK FIX acceptance pipeline |

---

## 2. Workstream F — Beta Readiness Assessment (`NLGCP Local Engineering Integration Beta v0.1`)

Allowed classifications: `COMPLETE`, `IMPLEMENTED`, `PARTIALLY IMPLEMENTED`, `SYNTHETICALLY VALIDATED`, `NOT VALIDATED`, `BLOCKED`, `NOT STARTED`. (`COMPLETE` never implies operational approval.)

| Category | Assessment | Supporting Evidence (Observed Day 7) |
|---|---|---|
| **Backend architecture** | `IMPLEMENTED` | Clear separation across Phases 2–12 (`apps/api`, `services/gnss-ingestor`, `services/correction-service`, `research/*`); Phase 11->12 path integrated; Phase 8->11 and NATS/API runtime bridges remain unwired (`12-day7-backend-architecture-audit.md`) |
| **GNSS processing integration** | `PARTIALLY IMPLEMENTED` | Offline Phases 3–8 pipelines complete and evidenced on DOY 2024/026 (`rnx2rtkp v2.4.2-p13`, PRIDE PPP-AR); live real-time GNSS processing loop and `services/nrtk-engine` C++ core remain unimplemented |
| **RTCM generation** | `SYNTHETICALLY VALIDATED` | Phase 11 bit-level encoders for `1005`, `1074`, `1084` (+ lab `4095`) with fail-closed admission gates (`127` tests passed with `RTKLIB_SOURCE`); authentic input and VRS blocked; GLONASS FCN absent in standalone `1084` |
| **Independent RTCM decoding** | `SYNTHETICALLY VALIDATED` | Unmodified RTKLIB v2.4.2-p13 (`convbin` SHA-256 `b575f81e…` + native `input_rtcm3` commit `71db0ffa…`) decodes all 3 message types within quantization tolerances; no second non-RTKLIB decoder installed |
| **NTRIP caster** | `SYNTHETICALLY VALIDATED` | Loopback-only (`127.0.0.1`) NTRIP v2/v1 caster (`NLGCP_TEST`), bounded broker, mandatory artifact/registry/VRS gates, atomic capacity checks (`55` Phase 12 tests); not safe for non-loopback networks (`13-day7-backend-security-review.md`) |
| **NTRIP client** | `SYNTHETICALLY VALIDATED` | Authenticated loopback NTRIP v2/v1 client reusing Phase 10 `StreamingFramer`/handshake/`ReconnectPolicy`; terminal 401/404 non-retry, timeout propagation, and truncation/CRC quarantine verified (`55` Phase 12 tests) |
| **Synthetic end-to-end integration** | `SYNTHETICALLY VALIDATED` | Full Phase 11 -> Phase 12 -> Client -> RTKLIB pipeline verified byte-exact (`135/135` B), multi-client isolated, fragmentation-safe, interruption-recoverable; `scripts/run_phase12_lab_demo.py` passes all 10 stages (`350` focused Phase 9–12 tests passed, `0` skipped) |
| **Authentication** | `PARTIALLY IMPLEMENTED` | Constant-time Basic auth (`hmac.compare_digest`) + log redaction works for local loopback lab credentials; lacks TLS, credential hashing, rotation, revocation, RBAC, and API auth (`SEC-01`, `SEC-02`) |
| **Security** | `PARTIALLY IMPLEMENTED` | Strong loopback-only isolation, secret redaction, non-root Dockerfiles, CI CodeQL/dependency review; 2 CRITICAL and 4 HIGH blockers remain before any controlled-network exposure (`13-day7-backend-security-review.md`) |
| **Diagnostics** | `IMPLEMENTED` | Five separated health dimensions (`SERVICE_HEALTH`, `CONNECTION_HEALTH`, `STREAM_HEALTH`, `RTCM_FRAME_HEALTH`, `SCIENTIFIC_READINESS`) and structured redacted JSON logs verified across fault scenarios; in-process only (not yet exported via API/Prometheus) |
| **Monitoring** | `NOT STARTED` | No Prometheus metrics exporter, Grafana dashboards, Alertmanager rules, central log aggregation, or Phase 14 operational alerting (`services/station-monitor` is a placeholder README) |
| **Scientific readiness** | `BLOCKED` | Phase 6 `BEST = ZERO`, Phase 7 `VRS_GEOMETRY_ONLY` / `VRS_GENERATION = ZERO`, DOY 026 single-day verified coordinate scope, no authentic CORS/RTCM stream, `OPERATIONAL_APPROVED = FORBIDDEN` |
| **Operational readiness** | `BLOCKED` | Synthetic-only, loopback-only lab implementation; lacks authentic data, promoted science, TLS/auth/security hardening, multi-decoder/receiver validation, monitoring, and field acceptance |
| **Field readiness** | `NOT STARTED` | Hardware availability `UNKNOWN`; zero field plan, receiver inventory, control-point validation, or interoperability records |

### 2.1 Alignment Against Day 1 Beta Acceptance Criteria (`05-beta-acceptance-criteria.md`)

- **Met for backend/lab scope (11 of 16 Must criteria):** `AC-01` (synthetic labels), `AC-02` (`OPERATIONAL_APPROVED` forbidden), `AC-03` (Phase 11 fail-closed admission), `AC-04` (CRC-24Q/framing), `AC-05` (loopback caster + synthetic mountpoint + source table), `AC-06` (local test client), `AC-07` (faults/buffer/disconnect/stale), `AC-10` (isolated non-production local auth), `AC-11` (loopback-only), `AC-12` (no real/field/accuracy claims), `AC-13` (focused deterministic tests pass), `AC-14` (`make check` passes), `AC-15` (provenance preserved, raw data untouched) — *13 Must criteria satisfied at backend checkpoint*.
- **Deferred / Pending by design (3 of 16 Must criteria):** `AC-08` and `AC-09` (versioned `/api/v1` status surface & UI — **deferred** with Phase 13 dashboard deferral), and `AC-16` (Day 14 formal beta exit decision — future milestone).

---

## 3. Workstream H — Consolidated Technical Debt and Priority Matrix

### A. Backend Engineering Debt

| ID | Item | Priority | Phase | Dependencies | Complexity | Scientific Significance | Operational Significance |
|---|---|---|---|---|---|---|---|
| BE-01 | Build Phase 8 `DecisionResponse` -> Phase 11 `CorrectionGenerationRequest` runtime adapter | P1 | 8 -> 11 | Phase 8 & 11 contracts | Low-Medium | Medium (enforces live scientific gating) | High |
| BE-02 | Wire `services/gnss-ingestor` runtime stream loop to NATS JetStream (`correction.live.*`) with graceful shutdown | P1 | 10 -> 12 | Authorized CORS or synthetic source; NATS auth | Medium | Medium (enables real-time ingest) | High |
| BE-03 | Add standalone daemon entrypoint + read-only local status IPC/HTTP endpoint for `services/correction-service` | P2 | 12 -> 14 | Phase 12 caster | Low-Medium | Low | High |
| BE-04 | Implement NMEA-0183 GGA parsing and per-rover unicast VRS session routing in caster/broker | P2 | 12 / 7 | Approved VRS model (GN-02) | High | High (required for real VRS) | High |
| BE-05 | Implement HTTP/1.1 chunked Transfer-Encoding and NTRIP v2 full conformance in caster & client | P3 | 12 | Phase 12 caster/client | Medium | Low | High (commercial rover compat) |
| BE-06 | Implement read-only `/api/v1` status/diagnostics routes (Phase 13 control-plane API, deferred) | P3 | 13 | BE-03, SEC-02 | Medium | Low | Medium (operator visibility) |
| BE-07 | Replace `services/nrtk-engine` C++ shell and `services/station-monitor` placeholder when real-time algorithms are validated | P3 | 5/7/14 | GN-01, GN-02 | High | High | High |

### B. GNSS Scientific Research Debt

| ID | Item | Priority | Phase | Dependencies | Complexity | Scientific Significance | Operational Significance |
|---|---|---|---|---|---|---|---|
| GN-01 | Acquire authorized live/recorded authentic Nigerian CORS/NTRIP streams and multi-day verified IGS20/ITRF station coordinates (resolving 2024 single-day DOY 026 and 2011 provisional coordinate blocks) | **P0 (Critical Path)** | 2 / 4 / 10 | External CORS / OSGoF / precise product access | High (external) | **Critical** | **Critical** |
| GN-02 | Develop and validate a dense-network / multi-day atmospheric & spatial interpolation model that demonstrably outperforms `ZERO` under strict held-out interpolation (non-extrapolating geometry) | **P0 (Critical Path)** | 6 / 7 | GN-01 (multi-day verified dense network) | Very High | **Critical** | **Critical** |
| GN-03 | Implement and validate real-time VRS observation synthesis + positioning validation (moving beyond `VRS_GEOMETRY_ONLY`) | P1 | 7 | GN-02 | High | **Critical** | **Critical** |
| GN-04 | Extend Phase 11 encoders for `1006`/`1007`/`1008`/`1033`, GLONASS `1230` & ephemerides (`1019`/`1020`), Galileo/BeiDou MSM4/MSM7 (`1094`/`1124`/`1077`/`1087`) | P1 | 11 | GN-01 (authentic RTCM reference) | High | High (fixes 1084 FCN & multi-GNSS) | High |
| GN-05 | Calibrate Phase 4 QC thresholds against reviewed multi-day Nigerian field/CORS evidence (remove PROVISIONAL status) | P2 | 4 | GN-01 | Medium | High | Medium |

### C. Security and Infrastructure Debt

| ID | Item | Priority | Phase | Dependencies | Complexity | Scientific Significance | Operational Significance |
|---|---|---|---|---|---|---|---|
| SI-01 | Remediate SEC-01/SEC-02: TLS 1.2+/1.3 termination, managed secrets, hashed/rotatable credentials, revocation, and per-mountpoint ACLs | P1 (P0 before non-loopback) | 15 | ADR for controlled-network deployment | High | Low | **Critical** |
| SI-02 | Remediate SEC-03/SEC-04/SEC-07: pre-auth worker pool/connection cap, per-IP auth rate limiting, exclusive source-push lock, cumulative header read deadline | P1 | 12 / 15 | Phase 12 caster | Medium | Low | High |
| SI-03 | Remediate SEC-05/SEC-06: Go ingestor HTTP timeouts, eliminate `CHANGE_ME` Compose password default, enable NATS/Redis auth + TLS | P1 | 10 / 15 | Compose / Go ingestor | Low-Medium | Low | High |
| SI-04 | Remediate SEC-09/SEC-11/SEC-12/SEC-13: `repr=False` on credential fields, complete audit events (`405`/source rejections), source-table error tracking, stalled-client eviction | P2 | 12 | Phase 12 code | Low | Low | Medium |
| SI-05 | Implement Phase 14 Prometheus metrics, structured log shipping, Alertmanager rules, and container/secret CI scanning (SEC-10) | P2 | 14 / 15 | BE-03 | Medium | Low | High |

### D. Testing and Interoperability Debt

| ID | Item | Priority | Phase | Dependencies | Complexity | Scientific Significance | Operational Significance |
|---|---|---|---|---|---|---|---|
| TI-01 | Validate Phase 11/12 RTCM streams with a second independent **non-RTKLIB** decoder (`pyrtcm`, BKG BNC, or equivalent) | **P1** | 11 / 12 | Approved external tool availability | Low-Medium | **High** (eliminates single-decoder bias) | High |
| TI-02 | Run real-time RTKLIB `rtkrcv` / `rnx2rtkp` rover positioning tests fed by authentic Phase 10/11/12 RTCM streams | P1 | 11 / 12 | GN-01 | Medium | **High** | High |
| TI-03 | Add sustained multi-hour soak test, slow-consumer TCP send-buffer stall test, and CI offline beta integration job | P2 | 12 | Phase 12 suite | Low-Medium | Low | Medium |

### E. Field Validation Debt

| ID | Item | Priority | Phase | Dependencies | Complexity | Scientific Significance | Operational Significance |
|---|---|---|---|---|---|---|---|
| FV-01 | Establish receiver/rover hardware inventory, antenna calibration, and surveyed Nigerian control-point network | P2 | 16 | External hardware & site authorization | High (external) | **Critical** | **Critical** |
| FV-02 | Execute controlled hardware-in-loop (HIL) and field interoperability tests (FIX rate, TTFF, ENU accuracy, GGA behavior across commercial receivers) | P2 | 16 | GN-01, GN-02, SI-01, TI-01, FV-01 | High | **Critical** | **Critical** |

### Critical Path to a Scientifically Defensible NRTK/VRS Platform

```text
GN-01 (Authorized authentic CORS + multi-day verified IGS20 coordinates)
  -> TI-01 (Second non-RTKLIB decoder) + GN-04 (Full RTCM/MSM/FCN/antenna suite)
  -> GN-02 (Multi-day non-extrapolating atmospheric model beating ZERO)
  -> GN-03 (Validated real-time VRS observation synthesis) + BE-01/BE-02/BE-04 (Live runtime wiring & GGA routing)
  -> SI-01/SI-02/SI-03 (TLS, production auth, rate limits, hardened infra)
  -> FV-01/FV-02 (Commercial receiver HIL + surveyed Nigerian field acceptance)
  -> Formal scientific & operational review (only path that can lift OPERATIONAL_APPROVED = FORBIDDEN)
```

Frontend/dashboard development (Phase 13, `BE-06`) is **not** on the scientific critical path and was appropriately deferred.

---

## 4. Fresh Day 7 Verification Results (Observed 2026-11-25)

| Verification Command | Observed Result |
|---|---|
| `RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest services/correction-service/tests research/rtcm_generation research/rtcm_replay research/ntrip_ingestion -q` | **PASS:** `350 passed in 53.75s` (`0` failed, `0` skipped: `55` Phase 12 + `127` Phase 11 + `74` Phase 9 + `94` Phase 10, including all 6 native RTKLIB `input_rtcm3` tests) |
| `cd services/gnss-ingestor && go test -v ./...` | **PASS:** All Go health and NTRIP transport tests passed (`ok ...internal/health`, `ok ...internal/ntrip`) |
| `RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python scripts/run_phase12_lab_demo.py` | **PASS:** Exit `0`, `ok=true`, `byte_exact_match=true` (`135/135` B), all 10 stages PASS, RTKLIB `convbin` + native `input_rtcm3()` PASS, `clean_shutdown=true`, explicit synthetic notice & `operational_readiness=NOT_APPROVED` |
| `make check` | **PASS:** Ruff clean; Go `gofmt`/`vet`/`test` clean; ESLint clean (0 warnings); strict `mypy` clean (`238` source files); TypeScript `tsc --noEmit` clean; pytest **`817 passed, 13 skipped`** in `67.68s` (environment-dependent skips without `RTKLIB_SOURCE` / outside-workspace `NLGCP_DATA_ROOT`: 6 native VRS + 5 Phase 11 native `input_rtcm3` + 1 Phase 12 native `input_rtcm3` + 1 external-data-root Phase 6 geometry test); CMake/CTest `1/1` passed; Next.js WASM production build clean |
| `git diff --check` | **PASS** (exit `0`) |

---

## 5. Day 7 Backend Checkpoint Decision

- **Backend Checkpoint Verdict:** **PASS FOR LOCAL SYNTHETIC LAB SCOPE (`v0.1` backend milestone consolidated).**
- **Go / No-Go Boundaries:**
  - **GO (authorized follow-on options):** Hardening `SEC-03`/`SEC-04`/`SEC-05`/`SEC-07`/`SEC-09`/`SEC-11`, integrating a second non-RTKLIB decoder (`TI-01`), adding the Phase 8 -> Phase 11 request adapter (`BE-01`), and/or pursuing authentic CORS + multi-day verified coordinate acquisition (`GN-01`).
  - **NO-GO (remains blocked):** Operational correction service, public caster exposure, VRS promotion, positioning/accuracy claims, and field testing.
- **Stop Condition:** Stopping at Day 7 boundary for project-owner review and explicit authorization.
