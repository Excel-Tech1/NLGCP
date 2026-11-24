# Days 4–5 Engineering Report — Phase 12: Local Synthetic NTRIP Correction Service

**Sprint:** NLGCP 14-Day Beta Sprint  
**Days:** 4–5 — Phase 12 NTRIP Correction Service (Local Synthetic Integration)  
**Date:** 2026-11-24  
**Branch:** `research/nlgcp-14-day-beta-sprint`  
**Base Checkpoint:** `8d10f30` (`Secure NLGCP Day 1-3 RTCM engineering checkpoint`)  
**Status:** Complete (local loopback-only synthetic caster + client + RTKLIB end-to-end verified; operational distribution remains BLOCKED)

---

## 1. Executive Summary

Days 4–5 implemented **Phase 12 (local loopback-only synthetic NTRIP correction
distribution)** under `services/correction-service/src/nlgcp_correction_service/`
and connected the existing Phase 11 synthetic RTCM `1005`/`1074`/`1084`
generation pipeline to an authenticated local NTRIP client with independent
RTKLIB decoding validation.

```text
Synthetic GNSS Fixtures (SYNTHETIC TEST DATA)
        |
        v
Phase 11 CorrectionGenerator (1005 / 1074 / 1084)
        |
        v
Phase 9 Framing + CRC-24Q Validation + Phase 11 CorrectionStreamArtifact
        |
        v
Phase 12 LocalNtripCaster (127.0.0.1 loopback only, mountpoint NLGCP_TEST)
        |
        v
Phase 12 LocalNtripClient (Basic auth, StreamingFramer, bounded reconnect)
        |
        v
Independent RTKLIB v2.4.2-p13 Validation (convbin + native input_rtcm3)
```

All outputs remain explicitly classified as **SYNTHETIC TEST DATA — NOT VALID
FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.** No operational NTRIP
service, authentic CORS distribution, receiver interoperability, RTK FIX, VRS
approval, or positioning accuracy is claimed.

---

## 2. Architecture Assessment & Reuse

### 2.1 Reused Components (Zero Duplication)

- **Phase 9 (`nlgcp_rtcm_replay`):** `crc24q`, `PREAMBLE`, `HEADER_LENGTH`,
  `CRC_LENGTH`, `MAX_RTCM_LENGTH`, `MIN_PAYLOAD_FOR_MESSAGE_NUMBER`,
  `extract_message_number`.
- **Phase 10 (`nlgcp_ntrip_ingest`):** `StreamingFramer` (incremental TCP byte
  stream framing + CRC-24Q + stray-byte accounting), `basic_auth_header`,
  `redact_text`, `redact_headers`, `split_head`, `parse_head`,
  `validate_stream_response`, `ReconnectPolicy`, `FailureClass`, `is_terminal`.
- **Phase 11 (`nlgcp_rtcm_generation`):** `CorrectionGenerator`,
  `ReferenceStation1005Encoder`, `GpsMsm4Encoder`, `GlonassMsm4Encoder`,
  `CorrectionStreamArtifact`, `GeneratedCorrectionFrame`, `OutputClassification`,
  `validate_frame`, and `independent_decoder` (`convbin` + native `input_rtcm3`).

### 2.2 New Phase 12 Components (`services/correction-service/`)

| Module | Responsibility |
|---|---|
| `__init__.py` | Service version, `LOOPBACK_HOST`, `DEFAULT_MOUNTPOINT` (`NLGCP_TEST`), synthetic/scientific labels |
| `config.py` | Fail-closed loopback-only (`127.0.0.1`) `CasterConfig` & `ClientConfig`, `from_env()`, bounded limits |
| `auth.py` | Constant-time Basic auth (`hmac.compare_digest`), v1 `SOURCE` password verification, Phase 10 redaction |
| `mountpoints.py` | `MountpointDefinition`, `MountpointRegistry`, synthetic-only gate, NTRIP `SOURCETABLE` renderer |
| `validation.py` | Phase 9 CRC-24Q / preamble / reserved-bits / length / `SYNTHETIC_TEST_ONLY` publication gate |
| `diagnostics.py` | Structured redacted JSON logger + 5-dimension health view (`SERVICE_HEALTH`, `CONNECTION_HEALTH`, `STREAM_HEALTH`, `RTCM_FRAME_HEALTH`, `SCIENTIFIC_READINESS`) |
| `publisher.py` | `MountpointBroker` with bounded FIFO per-client queues, Phase 11 `CorrectionGenerationResult` + `CorrectionStreamArtifact` ingestion |
| `caster.py` | Loopback-only NTRIP v2/v1 TCP caster (`GET /`, `GET /<mp>`, `POST /<mp>`, `SOURCE <pw> /<mp>`), partial-write loop, `select`/`MSG_PEEK` peer-close detection, clean shutdown |
| `client.py` | Local loopback NTRIP v2/v1 client, `StreamingFramer` frame reconstruction, bounded exponential backoff, terminal-error fail-fast |
| `pipeline.py` | Reproducible end-to-end synthetic Phase 11 -> Phase 12 -> RTKLIB pipeline helper |
| `scripts/run_phase12_lab_demo.py` | Reproducible CLI runner emitting JSON diagnostics & RTKLIB verification |
| `services/correction-service/.env.example` | Safe local example configuration with `CHANGE_ME` placeholders (no secrets) |

---

## 3. NTRIP Protocol Support & Explicit Limitations

### 3.1 Implemented & Tested

- **NTRIP v2 (`Ntrip-Version: Ntrip/2.0`):**
  - `GET / HTTP/1.1` -> `HTTP/1.1 200 OK`, `Ntrip-Version: Ntrip/2.0`,
    `Content-Type: gnss/sourcetable`, `Content-Length`, `SOURCETABLE` body.
  - `GET /NLGCP_TEST HTTP/1.1` + Basic auth -> `HTTP/1.1 200 OK`,
    `Ntrip-Version: Ntrip/2.0`, `Content-Type: gnss/data`, `Cache-Control: no-store`,
    `Connection: close` + raw RTCM binary frames.
  - `POST /NLGCP_TEST HTTP/1.1` + Basic source auth -> `HTTP/1.1 200 OK`,
    incremental `StreamingFramer` + CRC-24Q gate before fan-out.
- **NTRIP v1 Compatibility (no `Ntrip-Version: Ntrip/2.0` header):**
  - `GET / HTTP/1.0` -> `SOURCETABLE 200 OK`.
  - `GET /NLGCP_TEST HTTP/1.0` + Basic auth -> `ICY 200 OK` + raw RTCM frames.
  - `SOURCE <password> /NLGCP_TEST` -> `ICY 200 OK` or `ERROR - Bad Password` / `ERROR - Bad Mountpoint`.
- **Fail-Closed HTTP Errors:** `400 Bad Request` (malformed/oversized headers),
  `401 Unauthorized` + `WWW-Authenticate: Basic realm="NLGCP-LAB"`,
  `404 Not Found` (unknown mountpoint — never serves source table on unknown path),
  `405 Method Not Allowed`, `503 Service Unavailable` (capacity reached).

### 3.2 Unsupported Protocol Features (Not Claimed)

- HTTP/1.1 `Transfer-Encoding: chunked` (uses identity binary streaming);
- TLS / HTTPS termination (loopback-only lab service; Phase 15 scope);
- NMEA GGA rover position parsing and VRS mountpoint routing (operational VRS blocked);
- Digest auth, OAuth/JWT, user accounts, entitlements, or billing (Phase 13/15 scope);
- Authentic CORS station source ingestion (blocked until authorized live CORS source).

---

## 4. Security Controls

- **Explicit loopback enforcement:** `CasterConfig` and `ClientConfig` reject
  `0.0.0.0`, `::`, `localhost`, and any address other than `"127.0.0.1"`.
- **No hardcoded production credentials:** Credentials must be passed via
  environment (`CasterConfig.from_env`) or generated ephemerally per run
  (`secrets.token_urlsafe(16)` in `pipeline.py`).
- **Constant-time comparison:** `CredentialStore` verifies both username and
  password using `hmac.compare_digest` across all configured accounts.
- **Zero credential leakage:** `StructuredEventLogger` redacts `password`,
  `secret`, `token`, and `authorization` fields plus known secret values;
  diagnostics snapshots never include credentials.
- **Basic auth transport caveat:** HTTP Basic authentication sends base64
  credentials without encryption and is explicitly restricted to `127.0.0.1`
  loopback laboratory use; it is **not** suitable for untrusted networks
  without TLS and Phase 15 security controls.
- **Resource bounds:** Bounded `max_clients` (`<= 128`), `max_request_bytes`
  (`<= 65536`), `max_queue_frames` (`<= 4096`), explicit socket timeouts,
  bounded `reconnect_policy.max_attempts` (`<= 20`), and clean socket/thread
  teardown on `stop()`.
- **No silent corruption acceptance:** Both caster (`validate_rtcm_bytes` +
  `StreamingFramer`) and client (`StreamingFramer`) reject/quarantine bad
  preambles, invalid lengths, CRC-24Q failures, and truncated trailing bytes.

---

## 5. Verification & Test Results

### 5.1 Reproducible CLI End-to-End Demonstration

Command:
```bash
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python scripts/run_phase12_lab_demo.py
```

Observed output highlights:
- `ok = true`, `byte_exact_match = true`, `mountpoint = "NLGCP_TEST"`
- `sent_message_numbers = [1005, 1074, 1084]`, `received_message_numbers = [1005, 1074, 1084]`
- `bytes_received = 135`, `bytes_transmitted = 135`, `crc_failures = 0`, `stray_bytes = 0`, `truncated_trailing_bytes = 0`
- Independent RTKLIB `convbin` (SHA-256 `b575f81e…`): `1005 XYZ = [111111.1111, -222222.2222, 3333333.3333]`, `1074 = [C1C, L1C, S1C, C2P, L2P, S2P]`, `1084 = [C1C, S1C, C2C, S2C]`
- Independent native RTKLIB `input_rtcm3()` (commit `71db0ffa…`): `1005 ECEF = [111111.1111, -222222.2222, 3333333.3333]`, `1074 msmtype = "L1C,L2P"`, `1084 msmtype = "L1C,L2C"`
- `health.SCIENTIFIC_READINESS = "NOT_VALID_SYNTHETIC_TEST_ONLY — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS"`

### 5.2 Focused Phase 12 + Phase 11 + Phase 9 Test Suite (with native RTKLIB)

```text
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest \
  services/correction-service/tests research/rtcm_generation research/rtcm_replay -q
230 passed in 41.83s
(29 Phase 12 + 127 Phase 11 + 74 Phase 9; 0 failed, 0 skipped)
```

### 5.3 Full Repository Quality Gate (`make check && git diff --check`)

- Ruff (`ruff check .`): `All checks passed!`
- Go (`gofmt -d . && go vet ./...` and `go test ./...`): passed
- ESLint (`--max-warnings=0`): passed
- mypy (`strict = true`): `Success: no issues found in 237 source files`
- TypeScript (`tsc --noEmit`): passed
- pytest: **`792 passed, 12 skipped in 38.17s`** (28/29 Phase 12 tests ran in
  default `make check`; the 12 skips are the 6 native VRS + 5 native Phase 11
  + 1 native Phase 12 `input_rtcm3` tests requiring `RTKLIB_SOURCE`, all of
  which passed in the `230 passed` run above)
- CMake / CTest: `1/1 Test #1: nrtk-health-test Passed`
- Next.js production build: passed
- `git diff --check`: passed (no whitespace errors)

---

## 6. Acceptance Criteria Matrix (AC-01 through AC-18)

| ID | Criterion | Evidence | Status |
|---|---|---|---|
| AC-01 | Local caster starts successfully | `test_caster_starts_on_loopback_serves_v2_and_v1_sourcetable_and_stops_cleanly` | **PASS** |
| AC-02 | Caster binds only to `127.0.0.1` | `test_caster_config_rejects_non_loopback_hosts`, `caster.host == "127.0.0.1"` | **PASS** |
| AC-03 | Synthetic mountpoint (`NLGCP_TEST`) is available | `test_mountpoint_registry_enforces_synthetic_only_policy`, v2/v1 source table tests | **PASS** |
| AC-04 | Valid client credentials accepted | `test_credential_store_constant_time_verification_and_redaction`, E2E tests | **PASS** |
| AC-05 | Invalid credentials rejected | `test_negative_invalid_username_and_invalid_password` (`401`, 0 retries) | **PASS** |
| AC-06 | Unknown mountpoints rejected | `test_negative_unknown_mountpoint_rejected_without_retry` (`404`, 0 retries) | **PASS** |
| AC-07 | RTCM frames published through caster | `test_end_to_end_phase11_to_phase12_client_and_convbin`, `test_caster_source_push_*` | **PASS** |
| AC-08 | NTRIP client connects and receives stream | E2E tests (v2, v1, 1-byte TCP chunk split, concurrent clients) | **PASS** |
| AC-09 | Received frames pass CRC-24Q validation | `StreamingFramer` + `crc_failures == 0` on E2E; mutation rejected | **PASS** |
| AC-10 | Received frames retain original message types | `sent_message_numbers == received_message_numbers == (1005, 1074, 1084)` | **PASS** |
| AC-11 | Received RTCM messages decode through RTKLIB | `convbin` + native `input_rtcm3()` E2E tests + CLI demo | **PASS** |
| AC-12 | Decoded semantic values match synthetic fixtures within quantization tolerances | `1005` within `1e-4 m`, `1074`/`1084` PR within `±8.93 mm`, phase within `±0.28 mm` | **PASS** |
| AC-13 | Interrupted connections handled correctly | `test_negative_client_disconnect_and_caster_shutdown`, `select`/`MSG_PEEK` cleanup | **PASS** |
| AC-14 | Reconnection works within configured retry limits | `test_negative_reconnection_after_interruption`, `test_negative_caster_unavailable_respects_bounded_retries` | **PASS** |
| AC-15 | Malformed and corrupted frames rejected | `test_frame_validation_*`, `test_caster_source_push_*`, `test_negative_truncated_corrupted_crc_bad_preamble_and_empty_stream` | **PASS** |
| AC-16 | Service shutdown is clean | `caster.stop()` closes listener/client sockets, joins threads, sets `STOPPED` | **PASS** |
| AC-17 | No public network exposure possible through configuration | `CasterConfig` & `ClientConfig` reject `0.0.0.0`, `::`, hostnames, external IPs | **PASS** |
| AC-18 | Existing Day 1–3 regression tests remain passing | `230 passed` focused; `make check` `792 passed, 12 skipped` | **PASS** |

---

## 7. Scientific & Operational Readiness Assessment

- **Engineering integration readiness (Days 4–5 scope):** **COMPLETE** for local
  loopback synthetic distribution (`Phase 11 -> Phase 12 -> Client -> RTKLIB`).
- **Scientific readiness:** **NOT READY / BLOCKED.** All streamed frames are
  synthetic test fixtures. Phase 6 (`BEST = ZERO`), Phase 7 (`ZERO /
  VRS_GEOMETRY_ONLY`), and Phase 8 (`AUTO -> single-base fallback, FLOAT-only`)
  conclusions are unchanged.
- **Operational readiness:** **NOT APPROVED.** `OPERATIONAL_APPROVED` remains
  forbidden; authentic CORS/RTCM ingestion, non-RTKLIB decoder & commercial
  receiver interoperability, Phase 13–15 user/monitoring/security platforms, and
  Phase 16 field validation remain blocked/not started.

---

## 8. Stop Point

Days 4–5 stop here. Do not start Day 6, Day 7, Phase 13 dashboard, Phase 14
monitoring expansion, Phase 15 security hardening, public deployment, or field
deployment without explicit authorization. No commit or push was performed.
