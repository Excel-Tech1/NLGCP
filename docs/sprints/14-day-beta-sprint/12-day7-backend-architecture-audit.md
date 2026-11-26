# Day 7 — Backend Architecture Audit and Phase 9–12 Integration Review

- **Sprint:** NLGCP 14-Day Beta Sprint (Local Engineering Integration Beta)
- **Day:** 7 — Backend Checkpoint and Scope Review
- **Date:** 2026-11-25
- **Branch:** `research/nlgcp-14-day-beta-sprint`
- **HEAD Commit:** `0cea5ba` (`Complete Day 6 synthetic integration assurance`)
- **Prior Checkpoints:** `459143e` (`Complete Phase 12 local synthetic NTRIP service`), `8d10f30` (`Secure NLGCP Day 1-3 RTCM engineering checkpoint`)
- **Data Classification:** `SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.`

---

## 1. Mandatory Git Preflight Verification

| Preflight Check | Observed Result | Status |
|---|---|---|
| Working directory | `/home/excellence/NLGCP` | PASS |
| Active branch | `research/nlgcp-14-day-beta-sprint` | PASS |
| Day 1–3 checkpoint | `8d10f30` (`Secure NLGCP Day 1-3 RTCM engineering checkpoint`) above `d789da0` | PASS |
| Day 4–5 checkpoint | `459143e` (`Complete Phase 12 local synthetic NTRIP service`), parent `8d10f30` | PASS |
| Day 6 checkpoint | `0cea5ba` (`Complete Day 6 synthetic integration assurance`), parent `459143e` | PASS |
| Working tree at start | Clean (0 staged, 0 unstaged, 0 untracked) | PASS |
| Remote tracking | `origin/research/nlgcp-14-day-beta-sprint` at `8d10f30` (`ahead 2`, unpushed) | PASS |

---

## 2. Workstream A — Backend Architecture Audit (End-to-End Pipeline Map)

The table and architecture map below distinguish **implemented, tested code** from **research-only offline tooling**, **health-only service shells**, and **unimplemented/blocked stages**.

```text
IMPLEMENTED / VERIFIED SYNTHETIC LAB PATH (LOCAL LOOPBACK ONLY):
  Synthetic GNSS Fixtures (deterministic 1005 / 1074 / 1084 vectors)
    -> Phase 11 CorrectionGenerator + admit_request() + CorrectionStreamArtifact
    -> Phase 12 MountpointBroker + validate_generated_frame() [reuses Phase 9 CRC-24Q]
    -> Phase 12 LocalNtripCaster (127.0.0.1, NTRIP v2/v1, NLGCP_TEST, Basic auth)
    -> Phase 12 LocalNtripClient [reuses Phase 10 handshake/StreamingFramer/ReconnectPolicy]
    -> Independent Unmodified RTKLIB v2.4.2-p13 (convbin + native input_rtcm3)

OFFLINE RESEARCH PATH (HISTORICAL 2024 DOY 026 RINEX ONLY; NOT RUNTIME-WIRED):
  Archived RINEX 2.11 + BKG/IGS BRDC -> Phase 4 QC -> Phase 3/5 RTKLIB ->
  Phase 6 Atmospheric (BEST=ZERO) -> Phase 7 VRS (VRS_GEOMETRY_ONLY) ->
  Phase 8 Hybrid Decision (SINGLE_BASE fallback; VRS BLOCKED)

UNWIRED / PLACEHOLDER / BLOCKED PATHS:
  Authorized Live CORS -> [BLOCKED: no admitted source]
  services/gnss-ingestor/cmd/ingestor -> [HEALTH SHELL ONLY: does not dial streams]
  services/nrtk-engine -> [HEALTH SHELL ONLY: no GNSS processing]
  services/station-monitor -> [PLACEHOLDER README ONLY]
  apps/api -> [GET /health ONLY; Phase 2 metadata libraries not mounted as HTTP routes]
  NATS JetStream / PostgreSQL / Redis -> [LOCAL COMPOSE INFRA; not wired to Phase 11/12]
  Commercial GNSS Rover / Field Receiver -> [NOT TESTED / HARDWARE UNKNOWN]
```

### 2.1 Stage-by-Stage Component Inventory

| Pipeline Stage | Actual Component(s) | Purpose & Implementation Location | Main Interfaces | Dependencies | Input Data | Output Data | Validation Status | Known Limitations | Integration Status |
|---|---|---|---|---|---|---|---|---|---|
| **1. GNSS Observation Input** | Phase 2 metadata/RINEX inventory (`apps/api/src/nlgcp_api/{rinex_inventory,data_manifest,phase2_dataset}.py`, `station_metadata/`), Phase 10 Go NTRIP library (`services/gnss-ingestor/internal/ntrip/`), Phase 10 Python bridge (`research/ntrip_ingestion/`), Phase 9 replay (`research/rtcm_replay/`) | Offline RINEX cataloging + live NTRIP client libraries (Go + Python) + recorded RTCM replay | `NtripClient.{probe,capture_stream}` (Python); `ntrip.Client` (Go); `run_rtcm_replay.py`; `run_ntrip_ingest.py` | Python stdlib, Phase 9 CRC-24Q, Go stdlib (`net`, `crypto/tls`) | Archived RINEX 2.11 / BKG BRDC (offline); synthetic loopback RTCM fixtures (Phase 9/10) | Manifests, immutable raw RTCM captures, `LiveFrame`, Phase 9 `CorrectionFrame` | Offline RINEX/BRDC validated on 2024 archive; Phase 9/10 transport **SYNTHETICALLY VALIDATED**; live CORS **BLOCKED** | Zero authorized live CORS sources; `cmd/ingestor` does not start live streaming; zero authentic RTCM captures admitted | **Unwired** to Phase 11/12 runtime; shared Phase 9/10 utility modules ARE imported directly by Phase 11/12 |
| **2. Data Validation & Quality Control** | Phase 4 GNSS QC Engine (`research/gnss_qc/src/nlgcp_gnss_qc/`) | Deterministic RINEX session QC (`archive`, `single_base_rtk`, `network_rtk` profiles) | `run_gnss_qc.py` CLI, `engine.py`, `classify.py`, `aggregate.py` | Python stdlib, Phase 2 manifests, external `NLGCP_DATA_ROOT` | Canonical RINEX observation files + verified coordinate & nav inventory | Session QC classifications (`ACCEPT`/`WARN`/`REJECT`/`BLOCKED`), reports, CSV/SVG | Full 2024 dataset run complete (`1290` sessions); `43` synthetic unit tests; thresholds **PROVISIONAL** | Offline RINEX-only (no real-time epoch-by-epoch RTCM observation QC); only DOY 026 admits 4 stations | Consumed offline by Phases 5, 6, 7, 8; **not wired** to live RTCM streams |
| **3. Correction Decision Engine** | Phase 8 Hybrid Decision Engine (`research/hybrid_decision_engine/src/nlgcp_hybrid_decision/`) + upstream Phase 6 (`research/atmospheric_spatial_model/`) & Phase 7 (`research/vrs_generator/`) | Fail-closed mode routing (`VRS` -> `SINGLE_BASE` -> `NO_CORRECTION`) under versioned policy `v1.0` | `DecisionRequest`, `DecisionResponse`, `CorrectionDecisionPhase9`, `run_hybrid_decision.py` | Phase 4 QC outputs, reviewed Phase 6/7 assessments (`geometry-v3`) | Target station/coords, QC admissions, Phase 6/7 assessment contracts | Mode decision, reason codes, provenance fingerprint, `CorrectionDecisionPhase9` handoff | `59` synthetic tests + real DOY 026 pilot (`AUTO` -> `SINGLE_BASE` EKAK, `VRS` BLOCKED) | Offline CLI/library; Phase 6 `BEST=ZERO`, Phase 7 `VRS_GEOMETRY_ONLY` keep VRS blocked; FLOAT-only history | Consumed by Phase 9 replay handoff; **no runtime adapter** yet maps `DecisionResponse` directly into live Phase 11 requests |
| **4. RTCM Message Generation** | Phase 11 Correction Generation (`research/rtcm_generation/src/nlgcp_rtcm_generation/`) | Fail-closed scientific admission + bit-level encoders for RTCM `1005`, GPS MSM4 `1074`, GLONASS MSM4 `1084`, and lab `4095` | `CorrectionGenerator.{generate,handoff}`, `admit_request`, `MessageFamilyRegistry`, `CorrectionStreamArtifact` | Phase 9 `crc24q`/`framing`, Python stdlib | `CorrectionGenerationRequest` + deterministic synthetic fixture fields/observations | `CorrectionGenerationResult`, `GeneratedCorrectionFrame`, `CorrectionStreamArtifact` | **SYNTHETICALLY VALIDATED** (`127` tests incl. unmodified RTKLIB `convbin` + `input_rtcm3`) | Synthetic fixtures only; GLONASS FCN not carried in 1084; no antenna/ephemeris/MSM7/SSR messages; no authentic input | **Directly integrated** with Phase 12 `MountpointBroker` and `pipeline.py` |
| **5. RTCM Validation** | Phase 9 framing (`nlgcp_rtcm_replay.{crc,framing}`), Phase 11 validation & independent decoder (`nlgcp_rtcm_generation.{validation,independent_decoder}`), Phase 12 publication gate (`nlgcp_correction_service.validation`) | Fail-closed `0xD3` preamble, reserved-bit, 10-bit length, CRC-24Q, SHA-256, registry status, and independent RTKLIB decoding | `validate_frame`, `validate_rtcm_bytes`, `validate_generated_frame`, `decode_with_convbin`, `decode_with_rtklib_native` | Phase 9 CRC-24Q, external RTKLIB v2.4.2-p13 (`convbin` + C source) | Raw RTCM frames / `GeneratedCorrectionFrame` | `ValidatedRtcmFrame`, `ValidationReport`, RTKLIB decoded ECEF/obs/MSM metadata | **SYNTHETICALLY VALIDATED** against RTKLIB v2.4.2-p13 | Single external decoder family (RTKLIB only; no `pyrtcm`, BKG BNC, or hardware receiver) | **Directly enforced** at Phase 12 publish boundary and client receive boundary |
| **6. NTRIP Caster** | Phase 12 Local Lab Caster (`services/correction-service/src/nlgcp_correction_service/{caster,publisher,mountpoints,auth,config,diagnostics}.py`) | Loopback-only (`127.0.0.1`) NTRIP v2/v1 caster, bounded broker, constant-time Basic auth, `NLGCP_TEST` mountpoint | `LocalNtripCaster`, `MountpointBroker`, `MountpointRegistry`, `CredentialStore`, `CasterDiagnostics` | Phase 9 CRC/framing, Phase 10 handshake/StreamingFramer/auth, Phase 11 models/handoff/registry | Phase 11 `CorrectionGenerationResult` + `CorrectionStreamArtifact` or authenticated source push | NTRIP v2/v1 source table and raw RTCM binary streams on `127.0.0.1` | **SYNTHETICALLY VALIDATED** (`55` Phase 12 tests incl. 26 Day 6 integration/fault tests) | Loopback-only; plaintext Basic auth (no TLS); no chunked transfer encoding; no NMEA GGA/VRS routing; no pre-auth rate limits | **Fully integrated** with Phase 11 and Phase 12 client; not yet wired into `compose.yml` or `apps/api` |
| **7. NTRIP Client** | Phase 12 Local Lab Client (`services/correction-service/src/nlgcp_correction_service/client.py`) | Authenticated loopback NTRIP v2/v1 client with streaming reconstruction, CRC validation, and bounded exponential backoff | `LocalNtripClient.{fetch_sourcetable,receive_frames}`, `ClientReceiveResult`, `ClientDiagnostics` | Phase 10 `StreamingFramer`, `handshake`, `ReconnectPolicy`, `FailureClass` | TCP byte stream from loopback caster | `ClientReceiveResult` (`valid_frames`, `invalid_frames`, `findings`, 5-dimension diagnostics) | **SYNTHETICALLY VALIDATED** (`55` Phase 12 tests) | Loopback-only (`127.0.0.1`); no TLS; no GGA uplink; synthetic test client (not a GNSS receiver) | **Fully integrated** with Phase 12 caster and RTKLIB demo pipeline |
| **8. GNSS Rover / Receiver** | **NOT IMPLEMENTED / NOT TESTED** | Physical or hardware-in-loop GNSS rover validation (Phase 16) | None | Authorized authentic corrections, receiver hardware, control points | Real RTCM correction stream | Surveyed rover position / RTK solution | **NOT STARTED / BLOCKED** (hardware availability `UNKNOWN`) | No commercial receiver (Leica, Trimble, Topcon, Emlid, u-blox, CHCNAV, etc.) tested | Absent |

### 2.2 Non-GNSS Control Plane and Supporting Services Audited

- **`apps/api` ([main.py](file:///home/excellence/NLGCP/apps/api/src/nlgcp_api/main.py)):** Exposes ONLY `GET /health` returning `{"status": "ok", "service": "nlgcp-api"}`. Phase 2 metadata/RINEX Python libraries exist under `apps/api/src/nlgcp_api/` (`26` tests) but are not wired into HTTP routes. Zero `/api/v1` endpoints exist.
- **`services/gnss-ingestor` ([main.go](file:///home/excellence/NLGCP/services/gnss-ingestor/cmd/ingestor/main.go)):** Hosts HTTP health/readiness endpoints (`GET /health`, `/live`, `/ready`, `/status`) on `:8081` (loopback-mapped via `compose.yml`). Contains a tested `internal/ntrip` Go client library (`30` Go tests), but `cmd/ingestor` explicitly does NOT initiate any live NTRIP stream.
- **`services/nrtk-engine` ([main.cpp](file:///home/excellence/NLGCP/services/nrtk-engine/src/main.cpp)):** Phase 1 C/C++ health executable only (`1` CTest); zero GNSS math implemented.
- **`services/station-monitor`:** Placeholder `README.md` only; zero code.
- **Infrastructure (`compose.yml`):** Local PostgreSQL/PostGIS (`127.0.0.1:15432`), NATS JetStream (`127.0.0.1:4222`/`8222`), and Redis (`127.0.0.1:16379`) run on loopback; `database/migrations/` contains only `001_enable_postgis.sql`; neither NATS nor PostgreSQL is wired to Phase 11/12 yet.

---

## 3. Workstream B — Phase 9–12 Detailed Integration Review

### 3.1 Phase 9 — Recorded RTCM Replay (`research/rtcm_replay`)

- **Implemented:** RTCM 3.x framing (`0xD3` preamble, 6 zero reserved bits, 10-bit length, 12-bit message number), CRC-24Q (`0x1864CFB` over preamble+header+payload), frame validation, fail-closed admission (`ACCEPT`/`WARN`/`REJECT`/`BLOCKED`), observed-only message inventory, honest timing classes (`EXACT`/`EPOCH-DERIVED`/`APPROXIMATE`/`UNAVAILABLE`), deterministic paced playback with `FakeClock`, pause/resume/stop, fingerprint-gated checkpoints, bounded buffering with explicit backpressure, Phase 8 handoff gating, and `correction.replay.*` consumer contracts (`74` unit tests).
- **Independently validated vs internally tested:**
  - **Independently validated (indirectly via Phase 11/12):** Phase 9's `crc24q()` and framing layout were exercised on synthetic RTCM `1005`/`1074`/`1084` frames decoded by unmodified RTKLIB v2.4.2-p13 (`convbin` and `input_rtcm3()`), confirming wire-level CRC-24Q and framing compatibility with RTKLIB.
  - **Internally tested only:** Replay pacing, checkpoint resume, backpressure policies, and recorded-stream admission have been exercised ONLY on synthetic fixtures (`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`); **zero authentic recorded RTCM captures** exist under `${NLGCP_DATA_ROOT}` (`REAL PILOT = BLOCKED`).

### 3.2 Phase 10 — Live CORS Ingestion (`services/gnss-ingestor`, `research/ntrip_ingestion`)

- **Implemented:** Dual Go (`services/gnss-ingestor/internal/ntrip`, `30` tests) and Python (`research/ntrip_ingestion`, `94` tests) NTRIP v2/v1 client libraries covering TLS-by-default dialing, Basic auth with header/log redaction, source-table parsing, fail-closed handshake validation (`401`/`403`/`404` terminal, HTML/empty/malformed rejection), incremental `StreamingFramer`, CRC-24Q quarantine, arrival timing, bounded exponential backoff (`ReconnectPolicy`), mountpoint-to-station admission (`NMEA_POSITION_REQUIRED` fail-closed), immutable capture writing with frame-safe rotation and disk-space guards, and operational `/health`/`/live`/`/ready`/`/status` endpoints.
- **Authentic CORS ingestion status:** **NOT DEMONSTRATED (BLOCKED).** No authorized live CORS or NTRIP provider endpoint exists in this repository or environment (`NLGCP_NTRIP_*` unset; home-directory `cors-*.rtcm3` files lack capture provenance and remain excluded). `cmd/ingestor` is a health shell only and does not open live connections. Implementation of an ingestion interface does **not** equate to operational CORS connectivity.

### 3.3 Phase 11 — RTCM Correction Generation (`research/rtcm_generation`)

- **Implemented:** `CorrectionGenerator`, `MessageFamilyRegistry`, `CorrectionGenerationRequest`/`Result`, `GeneratedCorrectionFrame`, `CorrectionStreamArtifact`, fail-closed `admit_request()` (14 distinct reason codes), bit-level encoders for RTCM `1005`, GPS MSM4 `1074`, GLONASS MSM4 `1084`, and lab `4095`, Phase 9 framing integration, deterministic provenance fingerprinting, and unmodified RTKLIB v2.4.2-p13 validation harnesses (`127` tests).
- **Independent RTKLIB reproducibility (re-verified Day 7):** Fresh execution with `RTKLIB_SOURCE=/home/excellence/RTKLIB` passed all `127/127` Phase 11 tests (`0` skipped) and reproduced `convbin` (SHA-256 `b575f81e…`) and native `input_rtcm3()` (pinned commit `71db0ffa…`) decoding of `1005` (`(111111.1111, -222222.2222, 3333333.3333)`), `1074` (`L1C,L2P`), and `1084` (`L1C,L2C`).
- **Single-decoder and encoding limitations:**
  - The RTCM bit layouts in `messages.py` were authored against RTKLIB `src/rtcm3e.c`/`src/rtcm3.c` and validated against RTKLIB `convbin` + `input_rtcm3()`. While unmodified RTKLIB catches encoding/sign/scale/signal-ID defects (and caught the Day 2 off-by-one signal-ID bug on Day 2/3), **no second independent non-RTKLIB decoder** (`pyrtcm`, BKG BNC, or commercial receiver firmware) is available to rule out shared RTKLIB-specific interpretations.
  - Standalone RTCM `1084` does not transport GLONASS frequency channel numbers (FCN); carrier phase decodes as zero without external FCN context (e.g., RTCM 1020/1230 or broadcast GLONASS ephemeris).
  - Registry status remains `SYNTHETICALLY_VALIDATED`; `OPERATIONAL_APPROVED` remains forbidden; authentic single-base input and operational VRS remain blocked.

### 3.4 Phase 12 — NTRIP Correction Distribution (`services/correction-service`)

- **Implemented:** Loopback-only (`127.0.0.1`) `LocalNtripCaster` (NTRIP v2 `GET /`, `GET /<mp>`, `POST /<mp>`; NTRIP v1 `GET /`, `GET /<mp>`, `SOURCE <pw> /<mp>`), `MountpointBroker` (bounded FIFO per-client queues, explicit overflow accounting, mandatory validated `CorrectionStreamArtifact`, atomic multi-frame validation, `MessageFamilyRegistry` status enforcement, VRS and `OPERATIONAL_APPROVED` blocking), `MountpointRegistry` (`NLGCP_TEST` synthetic-only), `CredentialStore` (constant-time `hmac.compare_digest`), `LocalNtripClient` (authenticated, `StreamingFramer`, bounded exponential backoff, fixed post-handshake `session_err` propagation), five-dimension `CasterDiagnostics` / `ClientDiagnostics` + `StructuredEventLogger`, and reproducible 10-stage CLI demo (`55` Phase 12 tests).
- **Fresh Day 7 end-to-end verification:** `RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python scripts/run_phase12_lab_demo.py` exited `0` with `ok=true`, `byte_exact_match=true` (`135/135` bytes), `0` CRC failures, RTKLIB `convbin` + native `input_rtcm3()` PASS, and `clean_shutdown=true` (`status=STOPPED`, `active_clients=0`).

---

## 4. Workstream C — End-to-End Backend Integration Verification

### 4.1 Ten-Point Integration Checklist

| # | Verification Requirement | Result | Evidence |
|---|---|---|---|
| 1 | Compatible interfaces across Phase 11 -> Phase 12 -> Client -> RTKLIB | **PASS** | Strict `mypy` clean across all 238 source files; `pipeline.py` and `test_day6_integration_assurance.py` |
| 2 | Provenance preserved across component boundaries | **PASS** | `MountpointBroker.publish_phase11_result()` requires `CorrectionStreamArtifact` with matching `schema_version`, `stream_id`, `decision_id`, `mode`, `message_families`, and `provenance_fingerprint == fingerprint(result.provenance)` |
| 3 | Synthetic classification preserved end-to-end | **PASS** | Enforced at Phase 11 `admit_request`, `MountpointDefinition.accepts_classification`, `validate_rtcm_bytes`, NTRIP source table `STR` record, and demo/diagnostics output |
| 4 | Invalid artifacts cannot bypass admission controls | **PASS** | `test_admission_rejects_missing_or_invalid_stream_artifact` (13 invalid/missing artifact variants fail closed) |
| 5 | Unsupported message families rejected | **PASS** | `test_admission_rejects_unsupported_registry_statuses` + unknown family test (`SYNTHETICALLY_VALIDATED` only) |
| 6 | VRS generation cannot bypass existing restrictions | **PASS** | Blocked at both Phase 11 `admit_request` (`VRS_OPERATIONAL_NOT_APPROVED`) and Phase 12 `MountpointBroker` (explicit `GenerationMode.VRS` & `artifact.mode == "VRS"` check) |
| 7 | Corrupt frames rejected | **PASS** | Rejected at publish (`validate_generated_frame` / `validate_rtcm_bytes`), NTRIP `POST`/`SOURCE` ingest, and client `StreamingFramer`; atomic multi-frame batch rejection verified |
| 8 | Client disconnections handled cleanly | **PASS** | `_peer_closed` (`select` + `MSG_PEEK`) and socket error cleanup return `active_clients` to `0`; verified in Day 5 and Day 6 suites |
| 9 | Resource limits remain enforced | **PASS** | Lock-atomic `try_acquire_client_slot(max_clients)` returning HTTP `503`, bounded `max_queue_frames`, `max_request_bytes`, positive timeouts, bounded `max_attempts <= 20` |
| 10 | Diagnostics accurately represent system conditions | **PASS** | 5 independent categories (`SERVICE_HEALTH`, `CONNECTION_HEALTH`, `STREAM_HEALTH`, `RTCM_FRAME_HEALTH`, `SCIENTIFIC_READINESS`) verified across state transitions |

### 4.2 Review of Day 6 Coverage and Remaining Uncovered Integration Risks

The 55 Phase 12 tests (29 Days 4–5 + 26 Day 6) thoroughly cover single-process loopback protocol compliance, admission gates, all 14 fault scenarios, diagnostics independence, and resource cleanup. **Meaningful uncovered integration risks that remain for later phases:**

1. **No Phase 8 -> Phase 11 runtime bridge:** Phase 8 `DecisionResponse` / `CorrectionDecisionPhase9` is not yet mapped programmatically into a live Phase 11 `CorrectionGenerationRequest`; current Phase 11/12 integration constructs synthetic requests directly in `pipeline.py`.
2. **No Phase 10 -> NATS -> Phase 11/12 multi-process bus wiring:** `services/gnss-ingestor` does not publish frames to NATS JetStream, and `services/correction-service` does not consume from NATS or run as a standalone Compose daemon.
3. **No long-duration soak / sustained multi-epoch streaming test:** Current tests verify 1–3 frame bursts and immediate queue saturation, not multi-hour continuous 1 Hz multi-client streaming, memory stability, or socket FD leak trends under sustained load.
4. **No slow-write TCP kernel-buffer stall test on caster:** While subscriber queue saturation is tested at the broker layer, a client that stops calling `recv()` until the OS TCP send buffer fills (exercising `client_write_timeout_s` eviction) has not yet been stress-tested.
5. **No NTRIP v2 chunked transfer encoding or NMEA GGA uplink testing:** Intentionally out of scope for Phase 12 lab mode, but required before commercial rover compatibility or future VRS routing.
6. **No cross-decoder / hardware receiver interoperability:** Only RTKLIB v2.4.2-p13 has decoded the emitted bytes.

---

## 5. Workstream G — Dashboard Deferral and Future API-Readiness Assessment

**Phase 13 Dashboard Deferral Confirmed:** Per project-owner direction, Phase 13 frontend/dashboard development is **DEFERRED**. Zero frontend files, UI components, dashboard pages, or frontend dependencies were modified or added on Day 7.

### 5.1 Backend API-Readiness Assessment for a Future Control Plane

Today `apps/api` exposes only `GET /health`. Before any future Phase 13 dashboard is built, a versioned read-only backend API under `/api/v1` (strictly keeping the control plane separate from real-time RTCM correction transport) will need the following interfaces:

| # | Required Capability | Proposed Read-Only Interface | Current Backend State | Gap / Prerequisite |
|---|---|---|---|---|
| 1 | Platform health | `GET /api/v1/health/summary` | Only `GET /health` on `apps/api` and `/health`/`/ready`/`/status` on `gnss-ingestor` | Aggregate process health separately from scientific validity (`scientific_validity: NOT_ASSESSED`) |
| 2 | Reference station status | `GET /api/v1/stations` and `GET /api/v1/stations/{station_id}` | Phase 2 metadata repository exists as Python library; no HTTP route; no live station monitor | Wire read-only FastAPI endpoints to metadata repo; add provenance & coordinate verification-state fields |
| 3 | Correction engine status | `GET /api/v1/correction/engine/status` | Phase 8 decision engine & Phase 11 generator exist as offline/in-process libraries | Expose current policy version, Phase 6/7 gate states (`BEST=ZERO`, `VRS_GEOMETRY_ONLY`), and blocked reason codes |
| 4 | RTCM generation statistics | `GET /api/v1/correction/rtcm/stats` | `MessageFamilyRegistry.as_dict()` exists; no persistent counter store | Expose per-family registry statuses (`SYNTHETICALLY_VALIDATED`), frame counts, and admission rejection counts |
| 5 | NTRIP caster status | `GET /api/v1/caster/status` | `LocalNtripCaster.status_snapshot()` exists in-process only | Expose read-only IPC/HTTP status endpoint from correction-service daemon (loopback-only) |
| 6 | Connected clients | `GET /api/v1/caster/clients` | `CasterDiagnostics` tracks `active_clients` count only; no sanitized active-session listing | Add secret-free session summary list (`client_id`, `mountpoint`, `connected_utc`, `frames_sent`, never credentials) |
| 7 | Mountpoint status | `GET /api/v1/caster/mountpoints` | `MountpointRegistry` exists in-process | Expose structured JSON metadata including `synthetic_only`, `label`, active subscribers, and last activity |
| 8 | Diagnostics | `GET /api/v1/diagnostics` | 5-dimension `health` dict exists on `CasterDiagnostics` and `ClientDiagnostics` | Aggregate caster + ingestor diagnostics without collapsing distinct health dimensions |
| 9 | Error reporting | `GET /api/v1/diagnostics/errors` | Counters exist (`crc_failures`, `rejected_frames`, `queue_overflow_drops`, `connection_errors`, `failed_auth_attempts`) | Add bounded in-memory ring buffer of redacted recent fault events with UTC timestamps and reason codes |
| 10 | Scientific readiness | `GET /api/v1/readiness/scientific` | Hardcoded constant `SCIENTIFIC_READINESS_STATUS` in Phase 12 | Expose explicit structured gate ledger (Phase 6/7/8/10/11/12/16 states, `OPERATIONAL_APPROVED: FORBIDDEN`, explicit blockers) |

None of these `/api/v1` endpoints have been implemented on Day 7; they remain documented prerequisites for a future phase only after higher-priority backend and scientific milestones are addressed.
