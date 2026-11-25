# Day 6 — End-to-End Synthetic Loopback Integration and Fault Verification

- **Sprint:** NLGCP 14-Day Beta Sprint
- **Day:** 6
- **Date:** 2026-11-25
- **Branch:** `research/nlgcp-14-day-beta-sprint`
- **Base Commit:** `459143e` (`Complete Phase 12 local synthetic NTRIP service`, parent `8d10f30`)
- **Data Classification:** `SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.`

---

## 1. Day 6 Objective

Execute a rigorous cross-phase integration assurance and fault-verification exercise across:

- **Phase 9:** RTCM 3.x framing and CRC-24Q validation (`research/rtcm_replay`).
- **Phase 10:** Shared NTRIP handshake parsing, streaming framing, credential redaction, and bounded exponential backoff (`research/ntrip_ingestion`).
- **Phase 11:** Synthetic RTCM 1005/1074/1084 correction generation, fail-closed admission gates, message-family registry, `CorrectionStreamArtifact` handoff, and independent RTKLIB v2.4.2-p13 decoders (`research/rtcm_generation`).
- **Phase 12:** Loopback-only (`127.0.0.1`) NTRIP v2/v1 caster, bounded broker, publication gate, authenticated client, and five-dimension diagnostics (`services/correction-service`).

The goal is verification and minimal defect remediation — not expansion of the correction engine, not Phase 13 dashboard work, and not operational readiness.

---

## 2. Initial Git State and Checkpoint Verification

Mandatory pre-implementation gate checks executed prior to any Day 6 edits:

| Gate Check | Observed Result | Status |
|---|---|---|
| Current branch | `research/nlgcp-14-day-beta-sprint` | PASS |
| Day 1–3 checkpoint in history | `8d10f30` (`Secure NLGCP Day 1-3 RTCM engineering checkpoint`) above `d789da0` | PASS |
| Day 4–5 commit message | `459143e` — `Complete Phase 12 local synthetic NTRIP service` | PASS |
| Day 4–5 commit parent | `8d10f30360a9c10a06f3c89ee890668d2b954dbd` (`8d10f30`) | PASS |
| Day 4–5 committed file count | Exactly the 22 approved files (`git show --name-only HEAD`) | PASS |
| Working tree clean at start | Clean (`ahead 1` of `origin/research/nlgcp-14-day-beta-sprint`) | PASS |
| Unexpected staged/unstaged/untracked files | None | PASS |
| No push performed | `origin/research/nlgcp-14-day-beta-sprint` remains at `8d10f30` | PASS |

---

## 3. Components Inspected

- **Phase 11:** `models.py` (`CorrectionGenerationRequest`, `CorrectionGenerationResult`, `GeneratedCorrectionFrame`, `GenerationMode`, `GenerationStatus`, `OutputClassification`, `ReasonCode`), `admission.py` (`admit_request`), `generator.py` (`CorrectionGenerator`), `handoff.py` (`CorrectionStreamArtifact`), `registry.py` (`MessageFamilyRegistry`, `MessageFamilyStatus`), `provenance.py` (`fingerprint`), `independent_decoder.py` (`decode_with_convbin`, `decode_with_rtklib_native`).
- **Phase 12:** `config.py` (`CasterConfig`, `ClientConfig`), `auth.py` (`CredentialStore`, `basic_auth_header`, `redact_text`), `mountpoints.py` (`MountpointDefinition`, `MountpointRegistry`), `validation.py` (`validate_rtcm_bytes`, `validate_generated_frame`), `publisher.py` (`MountpointBroker`), `caster.py` (`LocalNtripCaster`), `client.py` (`LocalNtripClient`), `diagnostics.py` (`CasterDiagnostics`, `ClientDiagnostics`, `StructuredEventLogger`), `pipeline.py` (`run_local_end_to_end_demo`), `scripts/run_phase12_lab_demo.py`.
- **Phase 9 & Phase 10 Shared Utilities:** `nlgcp_rtcm_replay.{crc,framing}`, `nlgcp_ntrip_ingest.{auth,backoff,framing,handshake,models}`.
- **Existing Tests:** `services/correction-service/tests/test_caster_unit.py` (18 collected test cases) and `services/correction-service/tests/test_end_to_end_and_negative.py` (11 collected test cases).

---

## 4. Existing Tests Reused

Without unnecessary duplication, Day 6 reuses and verifies the full existing regression suites:

- **Phase 12 (`29` existing tests):** loopback host rejection (`0.0.0.0`, `::`, `localhost`, external IPs), env loading, constant-time auth & redaction, synthetic-only mountpoint registry, basic `validate_rtcm_bytes` CRC/preamble/length/operational checks, v2/v1 source tables, v2/v1 source push, basic 2-client test, NTRIP v2 & v1 end-to-end `convbin` decode, native RTKLIB `input_rtcm3` semantic verification, 1-byte TCP split, invalid credentials, unknown mountpoint, unavailable caster backoff, abrupt disconnect/shutdown, basic reconnection, truncated/corrupt/bad-preamble/empty stream wire tests, malformed HTTP requests.
- **Phase 11 (`127` tests):** RTCM 1005/1074/1084 bit-level vectors, admission gates, scaffold contracts, and independent RTKLIB `convbin` + native `input_rtcm3` decoding.
- **Phase 9 (`74` tests):** CRC-24Q, framing, replay, buffering, checkpointing, and Phase 8 handoff gating.
- **Phase 10 (`94` tests):** shared NTRIP handshake, streaming framer, backoff, redaction, capture, and operational hardening.

---

## 5. New Tests Added

Added [`services/correction-service/tests/test_day6_integration_assurance.py`](file:///home/excellence/NLGCP/services/correction-service/tests/test_day6_integration_assurance.py) (`26` parametrized test cases across 19 test functions) covering every Day 6 gap and every defect fixed:

1. Multi-client concurrent byte-exact integrity (4 clients on `NLGCP_TEST` + 1 on `NLGCP_TEST_ALT` verifying SHA-256 identity and mountpoint isolation).
2. Irregular TCP fragmentation across 1-, 3-, 7-, and 13-byte chunks (`4` cases).
3. Mid-stream interruption, reconnection, byte-exact recovery of 1005/1074/1084, and post-recovery RTKLIB `convbin` decode.
4. Valid synthetic publication to `NLGCP_TEST`.
5. Rejection of `NO_CORRECTION`, Phase 11 `BLOCKED`, crafted empty `ACCEPTED`, and crafted `ENCODED` results carrying non-empty `reason_codes`.
6. Rejection of missing (`None`) and 12 invalid/mismatched `CorrectionStreamArtifact` variants.
7. Rejection of invalid preamble, non-zero reserved bits, truncated frame, SHA-256 mismatch, message-number mismatch, family/payload mismatch, and 1-bit CRC-24Q corruption.
8. Rejection of `DIAGNOSTIC_ONLY`, `RESEARCH_VALIDATION`, `OPERATIONAL_APPROVED` (request/result/frame/artifact/raw), and both Phase 11 and crafted `GenerationMode.VRS` results.
9. Rejection of unsupported registry statuses (`DECLARED`, `SCAFFOLDED`, `BLOCKED`, `REAL_INPUT_VALIDATED`, `OPERATIONALLY_APPROVED` — `5` cases), unknown families, unregistered mountpoints, and atomic multi-frame batch rejection.
10. Fault propagation for RTCM generator missing/out-of-range fields, bounded per-client queue saturation with fast-client isolation, `max_clients` HTTP `503` enforcement and slot recovery, HTTP `405`/malformed `SOURCE`/corrupt v1 source push, prolonged inactivity read timeout with bounded reconnection exhaustion, and full log/snapshot credential redaction audit.
11. Five-dimension diagnostic category independence across lifecycle and fault states.
12. Complete 10-step service lifecycle verifying OS `getsockname() == ('127.0.0.1', port)` and full socket/thread/subscription release on shutdown.
13. Reproducible CLI demonstration stage checklist and human + machine-readable output verification.

---

## 6. Integration Architecture Verified

Verified end-to-end loopback dataflow with zero external network connections:

```text
Synthetic GNSS Fixtures (1005 / 1074 / 1084)
  -> Phase 11 CorrectionGenerator + admit_request() + CorrectionStreamArtifact
  -> Phase 12 MountpointBroker.publish_phase11_result() + validate_generated_frame() [Phase 9 CRC-24Q]
  -> LocalNtripCaster (127.0.0.1 loopback, NTRIP v2/v1, constant-time Basic auth, NLGCP_TEST)
  -> LocalNtripClient (authenticated, Phase 10 handshake + StreamingFramer + ReconnectPolicy)
  -> Independent Unmodified RTKLIB v2.4.2-p13 (convbin + native input_rtcm3)
```

- All 3 message types (`1005`, `1074`, `1084`, 135 bytes total) traversed the pipeline byte-exact (`sent_raw == recv_raw`, identical per-frame SHA-256) with zero loss, duplication, reordering, or cross-client contamination.
- Irregular TCP splits (1/3/7/13 bytes) and mid-stream interruption/reconnection preserved CRC-24Q integrity and RTKLIB semantic decoding.

---

## 7. Admission-Control Results

| Case | Gate / Component Detecting | Expected | Observed |
|---|---|---|---|
| Valid synthetic `1005/1074/1084` + handoff artifact | Phase 11 + Phase 12 `MountpointBroker` | Published to `NLGCP_TEST` | PASS — published byte-exact |
| Rejected result (`NO_CORRECTION`, empty `ACCEPTED`, `reason_codes` present) | Phase 12 `MountpointBroker` | Fail closed (`PublicationError`) | PASS — 0 frames enter stream |
| Blocked Phase 11 result (unverified coord/model/missing field) | Phase 11 `admit_request` + Phase 12 `MountpointBroker` | Fail closed (`PublicationError`) | PASS — 0 frames enter stream |
| Missing (`None`) or invalid/tampered `CorrectionStreamArtifact` | Phase 12 `MountpointBroker` | Fail closed (`PublicationError`) | PASS — 13/13 invalid cases rejected |
| Invalid RTCM frame (preamble, reserved bits, truncation, SHA-256 mismatch) | Phase 12 `validate_generated_frame` / `validate_rtcm_bytes` | Fail closed (`PublicationError`) | PASS — 0 frames enter stream |
| Incorrect message number / family-number mismatch | Phase 12 `validate_generated_frame` | Fail closed (`PublicationError`) | PASS — rejected |
| Invalid CRC-24Q (1-bit flip) | Phase 12 `validate_rtcm_bytes` (Phase 9 `crc24q`) | Fail closed + `crc_failures`++ | PASS — rejected & counted |
| Non-synthetic classification (`DIAGNOSTIC_ONLY`, `RESEARCH_VALIDATION`) | Phase 12 `MountpointDefinition` + `validate_rtcm_bytes` | Fail closed | PASS — rejected |
| Unsupported registry status (`DECLARED`, `SCAFFOLDED`, `BLOCKED`, `REAL_INPUT_VALIDATED`, `OPERATIONALLY_APPROVED`, unknown) | Phase 12 `validate_generated_frame` | Fail closed | PASS — all 6 rejected |
| `OPERATIONAL_APPROVED` classification | Phase 11 `admit_request` + Phase 12 `validate_rtcm_bytes` + `MountpointDefinition` | Forbidden / fail closed | PASS — blocked at all layers |
| Operational VRS result (Phase 11 or crafted `ENCODED` `GenerationMode.VRS`) | Phase 11 `admit_request` + Phase 12 `MountpointBroker` | Blocked / fail closed | PASS — rejected at both layers |
| Publication to unregistered mountpoint | Phase 12 `MountpointBroker._require_mountpoint` | Fail closed (`PublicationError`) | PASS — rejected |
| Multi-frame batch containing 1 valid + 1 corrupt frame | Phase 12 `MountpointBroker` (atomic pre-validation) | Fail closed, 0 frames published | PASS — 0 frames published |

---

## 8. Fault-Propagation Results

| # | Fault Scenario | Detecting Component | Connection Disposition | Invalid Data | Retry Behavior | Resource Limits | Diagnostic Event / Counter | Secret Leakage |
|---|---|---|---|---|---|---|---|---|
| 1 | RTCM generator failure (missing/out-of-range fields) | Phase 11 `CorrectionGenerator` -> Phase 12 `MountpointBroker` | N/A (pre-transport) | Discarded (0 frames) | None | Respected | `BLOCKED` reason codes; `rejected_frames`++ | None |
| 2 | Invalid generation result / missing artifact | Phase 12 `MountpointBroker` | N/A | Discarded | None | Respected | `PublicationError`; `rejected_frames`++ | None |
| 3 | Caster unavailable | Phase 12 `LocalNtripClient` | Closed / not established | None | Bounded exponential backoff (`max_attempts`) | Bounded retries | `FailureClass.CONNECTION_LOST`, `reconnection_attempts`, `connection_errors` | None |
| 4 | Invalid client credentials | Phase 12 `LocalNtripCaster` (`CredentialStore`) + `LocalNtripClient` | Terminated (`401`) | None streamed | **No retry** (terminal `AUTH_FAILURE`) | Respected | `failed_auth_attempts`++, `client_auth_failed` | None (redacted) |
| 5 | Unknown mountpoint | Phase 12 `LocalNtripCaster` + `LocalNtripClient` | Terminated (`404`) | None streamed | **No retry** (terminal `MOUNTPOINT_NOT_FOUND`) | Respected | `unknown_mountpoint_requested`, `requested_mountpoints` | None |
| 6 | Client disconnection | Phase 12 `LocalNtripCaster` (`_peer_closed` / write error) | Closed & unsubscribed | None | Client-controlled | `active_clients` returns to 0 | `client_disconnected` | None |
| 7 | Publisher queue saturation | Phase 12 `MountpointBroker` | Healthy clients unaffected; slow queue bounded | Excess not buffered unboundedly | None | `maxsize=max_queue_frames` enforced | `queue_overflow_drops`++ | None |
| 8 | Maximum client capacity reached | Phase 12 `LocalNtripCaster` (`try_acquire_client_slot`) | Excess rejected (`503`) | None streamed | Transient; recovers after slot freed | Atomic lock enforces `active_clients <= max_clients` | `connection_errors`++ | None |
| 9 | Malformed NTRIP request / bad method / oversized header | Phase 12 `LocalNtripCaster` (`_read_request_head` / `_handle_connection`) | Terminated (`400` / `405`) | Discarded | None | `max_request_bytes` enforced | `connection_errors`++ | None |
| 10 | Truncated RTCM frame | Phase 12 `validate_rtcm_bytes` (publish) / `LocalNtripClient` (`StreamingFramer`) | Terminated / `ok=False` | Discarded (not emitted valid) | Per policy | Respected | `truncated_trailing_bytes`, `TRUNCATED_TRAILING_BYTES` | None |
| 11 | CRC-corrupted RTCM frame | Phase 12 `validate_rtcm_bytes`, `_ingest_source_stream`, `LocalNtripClient` | Source/client quarantined; invalid frame never forwarded | Quarantined / discarded | Per policy | Respected | `crc_failures`++, `CORRUPTION_OR_TRUNCATION_OBSERVED` | None |
| 12 | Unexpected caster shutdown | Phase 12 `LocalNtripClient` | Closed cleanly (`EOF`) | None | Bounded or stopped if disabled | Sockets & threads released | `FailureClass.CONNECTION_LOST`, `caster_stopped` | None |
| 13 | Reconnection exhaustion | Phase 12 `LocalNtripClient` (`ReconnectPolicy`) | Closed (`DISCONNECTED`) | None | Stops cleanly at `max_attempts` | Bounded (`max_attempts <= 20`) | `reconnection_attempts == max_attempts`, `client_reconnecting` | None |
| 14 | Empty stream / prolonged inactivity | Phase 12 `LocalNtripClient` (`read_timeout_s` / EOF) | Closed cleanly (`ok=False`) | None | Bounded retries then stops | Read timeout bounded | `FailureClass.TIMEOUT` / `STREAM_HEALTH=EMPTY`, `RTCM_FRAME_HEALTH=NO_FRAMES` | None |

---

## 9. Diagnostics Results

Verified all five diagnostic dimensions remain distinct on both `CasterDiagnostics` and `ClientDiagnostics`:

- `SERVICE_HEALTH` (`STOPPED` / `HEALTHY` / `CONNECTED` / `COMPLETED` / `DISCONNECTED`)
- `CONNECTION_HEALTH` (`IDLE` / `ACTIVE_CLIENTS` / `DEGRADED_ERRORS_OBSERVED` / `HEALTHY` / `ERROR`)
- `STREAM_HEALTH` (`IDLE` / `PUBLISHED_WAITING_CLIENTS` / `STREAMING` / `EMPTY` / `FRAMES_RECEIVED`)
- `RTCM_FRAME_HEALTH` (`NO_FRAMES` / `VALID_TRANSPORT_FRAMES` / `CRC_FAILURES_OBSERVED` / `CORRUPTION_OR_TRUNCATION_OBSERVED`)
- `SCIENTIFIC_READINESS` (invariantly `NOT_VALID_SYNTHETIC_TEST_ONLY — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS`)

Proven transitions:
- Caster running with 0 frames reports `SERVICE_HEALTH=HEALTHY` alongside `STREAM_HEALTH=IDLE` and `RTCM_FRAME_HEALTH=NO_FRAMES` (caster availability is not stream availability).
- Active client connected on an empty mountpoint reports `CONNECTION_HEALTH=ACTIVE_CLIENTS` alongside `STREAM_HEALTH=IDLE` and `RTCM_FRAME_HEALTH=NO_FRAMES` (connected client is not valid RTCM).
- Valid CRC-24Q reception reports `RTCM_FRAME_HEALTH=VALID_TRANSPORT_FRAMES` while `SCIENTIFIC_READINESS` remains `NOT_VALID_SYNTHETIC_TEST_ONLY — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS`.
- Observed CRC failure switches `RTCM_FRAME_HEALTH` to `CRC_FAILURES_OBSERVED` while `SERVICE_HEALTH` remains `HEALTHY`.

---

## 10. Lifecycle and Resource-Safety Results

Verified the complete 10-step service lifecycle in `test_full_ten_step_lifecycle_loopback_and_resource_cleanup`:

1. Loaded configuration via `CasterConfig.from_env`.
2. Confirmed loopback-only validation rejects `0.0.0.0`, `::`, `192.168.0.10`, and `localhost`.
3. Started caster and verified OS socket `getsockname() == ("127.0.0.1", port)`.
4. Confirmed synthetic mountpoint `NLGCP_TEST` registered and exposed via NTRIP source table.
5. Connected authenticated client.
6. Published Phase 11 synthetic `1005`/`1074`/`1084` frames with verified `CorrectionStreamArtifact`.
7. Received and validated all 3 frames byte-exact with 0 CRC failures.
8. Disconnected client and observed `active_clients == 0`.
9. Stopped caster cleanly (`caster.stop()`).
10. Verified `_listen_sock is None`, `_accept_thread is None`, `_active_sockets` empty, `_worker_threads` empty, broker `_subscribers` empty, zero `nlgcp-caster-*` threads alive, and subsequent TCP connection attempts to the former port fail with `OSError`.

---

## 11. End-to-End Demonstration Results

Executed:

```bash
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python scripts/run_phase12_lab_demo.py
```

Observed human-readable summary (`stderr`) and machine-readable JSON (`stdout`):

- `data_notice`: `SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.`
- `ok`: `true`, `mountpoint`: `NLGCP_TEST`, `byte_exact_match`: `true` (`135/135` bytes), `sent_message_numbers == received_message_numbers == [1005, 1074, 1084]`.
- All 10 explicit `stages` reported `ok=true`: `caster_startup` (`127.0.0.1`), `mountpoint_availability` (`HTTP 200`), `authentication` (`NTRIP 2.0`, `HTTP 200`), `rtcm_publication` (`3` frames), `client_reception` (`3` frames, `135` bytes), `byte_exact_comparison`, `crc_validation` (`0` caster / `0` client failures), `message_type_identification`, `independent_rtklib_decoding` (`convbin_performed=true`, `native_input_rtcm3_performed=true`), and `clean_shutdown` (`status=STOPPED`, `active_clients=0`).
- RTKLIB `convbin` (SHA-256 `b575f81e…`) and native `input_rtcm3()` (pinned commit `71db0ffa…`): `1005` ECEF = `(111111.1111, -222222.2222, 3333333.3333)`, `1074` = `L1C,L2P`, `1084` = `L1C,L2C`.
- `scientific_readiness`: `NOT_VALID_SYNTHETIC_TEST_ONLY — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS`; `operational_readiness`: `NOT_APPROVED`.

---

## 12. Focused Test Results

Commands executed with `RTKLIB_SOURCE=/home/excellence/RTKLIB`:

```bash
.venv/bin/python -m ruff check services/correction-service scripts/run_phase12_lab_demo.py
.venv/bin/python -m mypy services/correction-service/src services/correction-service/tests scripts/run_phase12_lab_demo.py research/rtcm_generation research/rtcm_replay research/ntrip_ingestion
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest services/correction-service/tests research/rtcm_generation research/rtcm_replay research/ntrip_ingestion -q
```

Observed results:
- **Ruff:** `All checks passed!`
- **Strict mypy:** `Success: no issues found in 81 source files`
- **Focused pytest (with `RTKLIB_SOURCE=/home/excellence/RTKLIB`):** **`350 passed, 0 failed, 0 skipped`** in `54.49s`:
  - `services/correction-service/tests`: `55` passed (`29` Phase 12 baseline + `26` Day 6 integration assurance, including native RTKLIB `input_rtcm3` E2E verification)
  - `research/rtcm_generation`: `127` passed (including all `5` native RTKLIB `input_rtcm3` tests)
  - `research/rtcm_replay`: `74` passed
  - `research/ntrip_ingestion`: `94` passed

---

## 13. Full Repository Quality-Gate Results

Commands executed:

```bash
make check
git diff --check
```

Observed results:
- **Ruff:** `All checks passed!`
- **Go (`services/gnss-ingestor`):** `gofmt -d .`, `go vet ./...`, and `go test ./...` PASS
- **ESLint (`apps/web`):** PASS (0 warnings)
- **Strict mypy:** `Success: no issues found in 238 source files`
- **TypeScript (`tsc --noEmit`):** PASS
- **Full pytest (without `RTKLIB_SOURCE` / outside-workspace `NLGCP_DATA_ROOT`):** **`817 passed, 13 skipped`** in `45.35s` (0 failed). The 13 environment-dependent skips are:
  - `6` native VRS geometry tests (`research/vrs_generator/tests/test_native_geometry.py`, require `RTKLIB_SOURCE`);
  - `5` native RTKLIB `input_rtcm3` decoder tests (`research/rtcm_generation/tests/test_independent_decoder.py`, require `RTKLIB_SOURCE` — all 5 executed and PASSED in the focused run above);
  - `1` native Phase 12 `input_rtcm3` E2E test (`services/correction-service/tests/test_end_to_end_and_negative.py`, requires `RTKLIB_SOURCE` — executed and PASSED in the focused run above);
  - `1` external-data-root geometry hardening test (`research/atmospheric_spatial_model/tests/test_geometry_hardening.py`, requires external `NLGCP_DATA_ROOT`).
- **CMake / CTest (`services/nrtk-engine`):** `1/1` passed (`nrtk-health-test`)
- **Next.js production build (`apps/web`):** PASS (WASM compiler)
- **`git diff --check`:** PASS (exit 0, zero whitespace/patch errors)

---

## 14. Failures and Remediation

Six real integration/admission/fault defects were discovered during Day 6 inspection and testing, fixed with minimal targeted changes, and covered by regression tests:

1. **Missing `CorrectionStreamArtifact` bypass (`publisher.py`):** `publish_phase11_result()` previously skipped artifact checks when `artifact is None`, allowing Phase 11 publication without a handoff artifact. Fixed to require a valid `CorrectionStreamArtifact` and verify `schema_version`, `stream_id`, `provenance_fingerprint` (matching `fingerprint(result.provenance)`), `decision_id`, `mode`, `generation_status == ENCODED`, synthetic `classification`, and `message_families`.
2. **Crafted `GenerationMode.VRS` and non-empty `reason_codes` bypass (`publisher.py`):** `publish_phase11_result()` did not explicitly block crafted `ENCODED` results with `mode == GenerationMode.VRS` or non-empty `reason_codes`. Fixed fail-closed.
3. **Unchecked `MessageFamilyRegistry` status at Phase 12 boundary (`validation.py`, `publisher.py`, `caster.py`):** `validate_generated_frame()` did not validate `frame.message_family` against `MessageFamilyRegistry` (`SYNTHETICALLY_VALIDATED` only) or confirm `frame.message_number in family.message_numbers`. Fixed fail-closed and wired optional `registry` parameter through `LocalNtripCaster.publish_phase11_result` and `MountpointBroker.publish_phase11_result`.
4. **Non-atomic multi-frame batch publication (`publisher.py`):** Previously validated and published frames one-by-one, allowing an earlier valid frame to enter the stream if a later frame in the same `CorrectionGenerationResult` failed validation. Fixed to validate all frames prior to publishing any frame.
5. **Non-atomic client capacity check (`diagnostics.py`, `caster.py`):** Separate check of `active_clients >= max_clients` followed by `client_connected()` was vulnerable to concurrent connection race conditions. Replaced with atomic lock-protected `CasterDiagnostics.try_acquire_client_slot(max_clients)`.
6. **Masked post-handshake `session_err` in client (`client.py`):** In `LocalNtripClient.receive_frames()`, `elif session_err is not None:` was skipped whenever `handshake is not None`, overwriting post-handshake `FailureClass.TIMEOUT` with `handshake.failure` (`None`) and falling back to `FailureClass.CONNECTION_LOST`. Fixed by changing `elif session_err is not None:` to `if session_err is not None:`.

In addition, `pipeline.py` and `scripts/run_phase12_lab_demo.py` were minimally enhanced to verify source-table mountpoint availability, record post-shutdown state (`clean_shutdown`), and output both a human-readable stage checklist (`stderr` or `--format text`) and machine-readable JSON (`stdout` or `--format json`) carrying explicit synthetic notices.

---

## 15. Outstanding Limitations

- **Synthetic fixtures only:** No authentic CORS observations or live NTRIP sources were used; real live ingestion (Phase 10) and authentic single-base RTCM generation (Phase 11) remain BLOCKED.
- **Single independent decoder family:** Independent decoding used unmodified RTKLIB v2.4.2-p13 (`convbin` + `input_rtcm3`); no non-RTKLIB second decoder (`pyrtcm`, BKG BNC) or commercial GNSS receiver was tested.
- **GLONASS FCN limitation:** RTCM 1084 does not transport GLONASS frequency channel numbers; standalone 1084 phase cycles decode as zero without auxiliary FCNs (verified on Day 3).
- **Loopback-only laboratory transport:** Plaintext Basic auth over `127.0.0.1` only; no TLS, no public binding, no HTTP chunked transfer encoding, no NMEA GGA parsing, no Phase 13/15 production identity or entitlements.
- **Unchanged upstream scientific blocks:** Phase 6 `BEST = ZERO`, Phase 7 `VRS_STATUS = VRS_GEOMETRY_ONLY` / `VRS_GENERATION = ZERO`, Phase 8 FLOAT-only single-base fallback restrictions remain completely unchanged.

---

## 16. Acceptance Criteria Matrix

| ID | Criterion | Status | Reproducible Evidence |
|---|---|---|---|
| AC-01 | Day 1–3 and Day 4–5 Git checkpoints verified | **PASS** | Section 2: `research/nlgcp-14-day-beta-sprint`, `459143e` above `8d10f30`, 22 approved files, clean start, unpushed |
| AC-02 | Complete Phase 11 → Phase 12 → NTRIP client pipeline reproduced | **PASS** | `test_end_to_end_phase11_to_phase12_client_and_convbin`, `test_day6_integration_assurance.py`, `scripts/run_phase12_lab_demo.py` |
| AC-03 | RTCM 1005, 1074 and 1084 transported successfully | **PASS** | `sent_message_numbers == received_message_numbers == [1005, 1074, 1084]` in demo & E2E tests |
| AC-04 | Byte-exact stream integrity demonstrated | **PASS** | `byte_exact_match=true` (`135/135` bytes), `test_multi_client_concurrent_byte_exact_and_mountpoint_isolation`, `test_irregular_tcp_fragmentation_preserves_crc_and_bytes` |
| AC-05 | Independent RTKLIB decoding succeeds | **PASS** | `convbin` + native `input_rtcm3()` PASS in `scripts/run_phase12_lab_demo.py`, `test_end_to_end_native_rtklib_input_rtcm3_semantic_verification`, `test_interruption_recovery_preserves_subsequent_frames_and_rtklib_decode` |
| AC-06 | Invalid or blocked Phase 11 results cannot enter the caster | **PASS** | `test_admission_rejects_rejected_blocked_and_reason_coded_results`, `test_fault_rtcm_generator_failure_propagates_fail_closed` |
| AC-07 | Invalid artifacts and unsupported classifications fail closed | **PASS** | `test_admission_rejects_missing_or_invalid_stream_artifact`, `test_admission_rejects_non_synthetic_operational_approved_and_vrs`, `test_admission_rejects_unsupported_registry_statuses` |
| AC-08 | `OPERATIONAL_APPROVED` remains forbidden | **PASS** | `test_admission_rejects_non_synthetic_operational_approved_and_vrs`, `test_frame_validation_accepts_valid_and_rejects_corrupt_or_operational` |
| AC-09 | Operational VRS publication remains blocked | **PASS** | `test_admission_rejects_non_synthetic_operational_approved_and_vrs` (both Phase 11 VRS request and crafted `ENCODED` VRS result rejected) |
| AC-10 | Client disconnection and reconnection behave correctly | **PASS** | `test_negative_client_disconnect_and_caster_shutdown`, `test_negative_reconnection_after_interruption`, `test_interruption_recovery_preserves_subsequent_frames_and_rtklib_decode`, `test_fault_prolonged_inactivity_timeout_and_reconnection_exhaustion` |
| AC-11 | Queue saturation and client capacity are handled safely | **PASS** | `test_fault_publisher_queue_saturation_is_bounded_and_isolated`, `test_fault_max_client_capacity_enforced_with_503_and_recovers` |
| AC-12 | Malformed NTRIP requests are rejected safely | **PASS** | `test_negative_malformed_client_requests_return_400`, `test_fault_unsupported_method_malformed_source_and_v1_corrupt_source_push` |
| AC-13 | Invalid, truncated and corrupted RTCM frames are rejected | **PASS** | `test_admission_rejects_invalid_rtcm_frame_message_number_and_crc`, `test_negative_truncated_corrupted_crc_bad_preamble_and_empty_stream`, `test_admission_rejects_unknown_family_unregistered_mountpoint_and_partial_batch` |
| AC-14 | Diagnostic categories accurately represent observed system states | **PASS** | `test_diagnostics_five_categories_remain_distinct_across_states` |
| AC-15 | Caster and client shutdown release resources cleanly | **PASS** | `test_full_ten_step_lifecycle_loopback_and_resource_cleanup` |
| AC-16 | Loopback-only network restrictions remain enforced | **PASS** | `test_caster_config_rejects_non_loopback_hosts`, `test_client_config_rejects_non_loopback_hosts`, `test_full_ten_step_lifecycle_loopback_and_resource_cleanup` (`getsockname == ('127.0.0.1', port)`) |
| AC-17 | Reproducible demonstration completes successfully | **PASS** | `RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python scripts/run_phase12_lab_demo.py` (exit 0, all 10 stages PASS, synthetic notice present), `test_reproducible_demo_stages_and_cli_human_and_json_output` |
| AC-18 | Focused tests, full repository quality gates and whitespace checks pass | **PASS** | Focused `350 passed, 0 skipped` (with `RTKLIB_SOURCE`); `make check` PASS (`817 passed, 13 skipped`, mypy 238 files, Ruff, Go, CTest, ESLint, tsc, Next.js); `git diff --check` PASS |
| AC-19 | Documentation accurately records the evidence and limitations | **PASS** | This report (`11-day6-integration-assurance.md`) + updates to `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`, `02-phase-readiness-matrix.md`, `06-fourteen-day-tracker.md` |
| AC-20 | No work outside the Day 6 scope is initiated | **PASS** | Zero Phase 6/7/13/14/15/16 changes, zero historical Day 1–5 report rewrites, zero commits/pushes |

---

## 17. Final Scientific and Operational Readiness Assessment

- **Scientific Readiness:** **NOT READY / BLOCKED.** All Phase 11/12 streams verified on Day 6 use deterministic synthetic fixtures (`SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.`). Upstream boundaries remain unchanged: Phase 6 `BEST = ZERO`, Phase 7 `VRS_STATUS = VRS_GEOMETRY_ONLY` / `VRS_GENERATION = ZERO`, Phase 8 FLOAT-only single-base fallback restrictions, Phase 11 registry `SYNTHETICALLY_VALIDATED`, `OPERATIONAL_APPROVED` **FORBIDDEN**.
- **Operational Readiness:** **NOT APPROVED.** Loopback-only (`127.0.0.1`) laboratory engineering assurance only. Public caster exposure, TLS, production authentication/entitlements, authentic CORS/RTCM ingestion, commercial receiver interoperability, and field validation remain blocked and unattempted.
