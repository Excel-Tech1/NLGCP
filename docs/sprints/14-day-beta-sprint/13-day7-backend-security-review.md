# Day 7 — Backend Security and Reliability Review

- **Sprint:** NLGCP 14-Day Beta Sprint (Local Engineering Integration Beta)
- **Day:** 7 — Backend Checkpoint and Scope Review
- **Date:** 2026-11-25
- **Branch:** `research/nlgcp-14-day-beta-sprint`
- **HEAD Commit:** `0cea5ba` (`Complete Day 6 synthetic integration assurance`)
- **Scope:** Local backend services (`services/correction-service`, `services/gnss-ingestor`, `apps/api`, `research/ntrip_ingestion`, `compose.yml`, CI workflows)
- **Network Boundary:** Strictly loopback-only (`127.0.0.1`). No public exposure, TLS termination, or production auth was implemented in this review.

---

## 1. Executive Summary

Within its current **strictly loopback-only (`127.0.0.1`) synthetic laboratory boundary**, the Phase 12 NTRIP correction service enforces strong fail-closed guardrails: non-loopback binds (`0.0.0.0`, `::`, external IPs, hostnames) are rejected at config validation, Basic authentication uses constant-time `hmac.compare_digest` across all configured accounts, structured logs redact credentials, queues and client counts are bounded, and operational/VRS classifications fail closed.

However, the service is **NOT safe for deployment on any shared, campus, private-LAN, or public network** without remediating the CRITICAL and HIGH findings below (primarily TLS termination, production identity/credential lifecycle, pre-authentication connection/rate limits, total header read deadlines, and container/infrastructure secret hardening).

---

## 2. Security and Reliability Findings Register

Severity scale reflects risk if the backend were moved beyond isolated `127.0.0.1` loopback into a controlled network environment.

| ID | Severity | Area | Finding & Code Location | Current Lab Mitigation | Required Remediation Before Controlled Network Use |
|---|---|---|---|---|---|
| **SEC-01** | **CRITICAL** | Transport security & authentication | Plaintext HTTP Basic Auth and NTRIP v1 `SOURCE <password>` transmit credentials without transport encryption (`services/correction-service/src/nlgcp_correction_service/{caster,client,auth}.py`). | Strictly enforced `127.0.0.1` loopback bind (`config.py:29-34`). | Terminate TLS 1.2+/1.3 (e.g., dedicated edge/TLS proxy or native TLS with vetted certs); disable NTRIP v1 plaintext `SOURCE` on untrusted links. |
| **SEC-02** | **CRITICAL** | Identity, credential storage & authorization | Static in-memory `CredentialStore` holds plaintext passwords loaded from env vars (`config.py:93-126`, `auth.py:66-111`). No credential hashing, rotation, revocation, expiration, per-mountpoint ACLs, or separation from future user accounts. `apps/api` has zero authentication. | Ephemeral/local test credentials only; `.env` excluded by `.gitignore`. | Implement Phase 15 managed secret storage, salted password/token hashing (e.g., Argon2id/scrypt or signed device tokens), instant revocation, and per-mountpoint RBAC/entitlements. |
| **SEC-03** | **HIGH** | Pre-auth DoS & brute-force resistance | `LocalNtripCaster._accept_loop()` spawns a new `threading.Thread` for every accepted TCP socket before authentication (`caster.py:255-269`), while `max_clients` is only checked after request parsing and auth (`caster.py:420`). No concurrent pre-auth connection cap and no per-IP auth rate limiting/lockout exist. | Loopback-only listener (`listen(min(32, max_clients * 2))`). | Add a bounded worker pool / semaphore on total accepted sockets prior to auth, plus per-IP connection and failed-auth rate limiting. |
| **SEC-04** | **HIGH** | Source-push concurrency & lifecycle bounds | Authenticated `POST` and v1 `SOURCE` handlers (`caster.py:478-541`) do not enforce a maximum concurrent source count or single-writer lock per mountpoint, allowing multiple sources to interleave frames onto the same mountpoint or consume unlimited worker threads. | Single local synthetic source in lab tests. | Enforce explicit `max_sources` limit and exclusive mountpoint-publisher lease/lock per mountpoint. |
| **SEC-05** | **HIGH** | Go ingestor HTTP server timeouts & container bind | `services/gnss-ingestor/cmd/ingestor/main.go:32` constructs `&http.Server{Addr: settings.Address, Handler: mux}` with zero `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, or `IdleTimeout`, and binds `:8081` inside the container. | `compose.yml:116` binds host port strictly to `127.0.0.1:8081:8081`. | Configure explicit `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, `IdleTimeout`, and bounded shutdown context (`context.WithTimeout`) in `cmd/ingestor/main.go`. |
| **SEC-06** | **HIGH** | Infrastructure secret defaults & unauthenticated internal buses | `compose.yml:8` defaults `POSTGRES_PASSWORD` to `CHANGE_ME`; local NATS JetStream (`127.0.0.1:4222`) and Redis (`127.0.0.1:16379`) run without authentication or TLS (`compose.yml:21-46`). | All Compose host ports bind strictly to `127.0.0.1`. | Require non-default injected secrets (fail closed without defaults), enable Redis ACL/auth and NATS NKeys/JWT + TLS, and segment Compose/network zones per Phase 15 baseline. |
| **SEC-07** | **MEDIUM** | Slowloris / per-recv timeout without total header deadline | `LocalNtripCaster._read_request_head()` (`caster.py:271-287`) sets per-`recv()` `socket_timeout_s` (5.0 s) rather than a cumulative header deadline. A slow-drip client sending 1 byte every 4 s can occupy a thread indefinitely up to `max_request_bytes` (8192 B). | Loopback-only lab access. | Enforce a monotonic wall-clock deadline (`deadline = time.monotonic() + socket_timeout_s`) across the entire header read loop. |
| **SEC-08** | **MEDIUM** | Unauthenticated source-table disclosure by default | `CasterConfig.allow_unauthenticated_sourcetable` defaults to `True` (`config.py:59`), exposing mountpoint names, synthetic metadata, and bound port to unauthenticated clients. | Intentionally standard NTRIP convention on `127.0.0.1`. | Review policy for controlled networks; default to `False` or serve minimal public catalogue without internal host/port/generator metadata. |
| **SEC-09** | **MEDIUM** | Secret fields visible in dataclass `repr()` | `CasterConfig.client_credentials`, `CasterConfig.source_credentials`, and `ClientConfig.password` (`config.py:52-53,137`) do not set `repr=False`. Although `StructuredEventLogger` redacts configured secrets, an unhandled traceback or `repr(cfg)` could expose secrets. | Never logged directly in current code; Day 6 `caplog` test verified zero leaks in normal/fault logs. | Add `repr=False` to credential fields in `CasterConfig` and `ClientConfig`. |
| **SEC-10** | **MEDIUM** | Containerization, CI security scanning & dependency governance | `services/correction-service` has no Dockerfile or Compose service yet; `apps/api/Dockerfile` runs `uvicorn --host 0.0.0.0` (safe only via Compose `127.0.0.1` mapping); no container image scanning or automated secret scanning runs in `.github/workflows/` beyond CodeQL and dependency review. | Local Python package tested via `make check`; all Compose host binds are `127.0.0.1`. | Add non-root Dockerfile (if containerized), container vulnerability scanning, secret scanning (e.g., gitleaks/trufflehog), and locked dependency hashes before controlled-network deployment. |
| **SEC-11** | **LOW** | Incomplete audit logging on `405` and source-push auth/mountpoint failures | `caster.py:331-335` (`405 Method Not Allowed`), `caster.py:488-499` (`POST` 401/404), and `caster.py:525-533` (`SOURCE` bad password/mountpoint) do not emit structured audit log events (and `405` does not increment `connection_errors`). | Client GET `401`/`404` and connect/disconnect ARE logged with redaction. | Emit redacted structured audit events (`method_not_allowed`, `source_auth_failed`, `unknown_source_mountpoint`) consistently for all rejected requests. |
| **SEC-12** | **LOW** | `fetch_sourcetable()` error accounting | `LocalNtripClient.fetch_sourcetable()` (`client.py:113-142`) enforces a hardcoded `262_144`-byte cap and returns `(None, "")` on malformed response without recording an error in `ClientDiagnostics`. | Used only for local source-table probes; `receive_frames()` tracks all errors. | Record malformed/truncated source-table failures in `ClientDiagnostics` and make max source-table size configurable. |
| **SEC-13** | **LOW** | Stalled subscriber eviction vs drop accounting | On subscriber queue overflow (`publisher.py:167-170`), `MountpointBroker` explicitly increments `queue_overflow_drops` and drops the incoming frame, keeping the slow subscriber attached rather than evicting chronically stalled clients. | Bounded `maxsize=max_queue_frames` prevents unbounded memory growth; healthy clients remain unaffected. | Consider optional high-water / consecutive-overflow disconnect policy so chronically stalled TCP clients release capacity slots promptly. |
| **SEC-14** | **INFORMATIONAL** | Verified security & reliability strengths | Positive controls verified directly in source and tests: (1) strict `127.0.0.1` enforcement in `config.py`; (2) constant-time `hmac.compare_digest` iterating all accounts to avoid username timing leaks (`auth.py:81-93`); (3) Phase 10 TLS verification enabled by default (`ssl.create_default_context()` / `tls.VersionTLS12`); (4) non-root container users (`65532:65532` in API, `nlgcp` in ingestor); (5) immutable `NLGCP_DATA_ROOT` mount design; (6) lock-atomic client slot reservation (`diagnostics.py:110-117`); (7) fail-closed RTCM framing/CRC/artifact/registry/VRS admission gates; (8) zero leaked credentials across `caplog` and diagnostics snapshots. | Active and regression-tested (`55` Phase 12 tests + `94` Python / `30` Go Phase 10 tests). | Preserve all existing invariants as hard gates in future phases. |

---

## 3. Reliability & Resource-Safety Review

| Dimension | Current Implementation | Assessment |
|---|---|---|
| **Network binding** | `CasterConfig` and `ClientConfig` reject every host string other than exact `"127.0.0.1"`; OS `getsockname()` verified in Day 6 tests. | **Strong (lab scope)** |
| **Socket & thread cleanup** | `LocalNtripCaster.stop()` sets `_stop_event`, closes all broker subscribers with `None` sentinels, closes listener + active client sockets (`SHUT_RDWR`), and joins accept + worker threads (`timeout=2.0`). Day 6 verified zero leaked sockets/threads and immediate `OSError` on subsequent connects. | **Strong (lab scope)** |
| **Backpressure & queues** | Per-client `queue.Queue(maxsize=max_queue_frames)` (bounded `[1, 4096]`, default `256`) and bounded backlog ring. Overflow increments `queue_overflow_drops` explicitly without blocking healthy clients. | **Solid (see SEC-13 for chronic stalls)** |
| **Timeouts & reconnection** | Positive `connect_timeout_s`, `read_timeout_s`, `socket_timeout_s`, `client_write_timeout_s`; `ReconnectPolicy` enforces capped exponential backoff (`max_attempts <= 20`); terminal HTTP `401`/`403`/`404` never retry; post-handshake `FailureClass.TIMEOUT` now propagates accurately (fixed Day 6). | **Strong (see SEC-07 for cumulative header deadline)** |
| **Dependency hygiene** | Focused runtime dependencies (`fastapi`, `pydantic-settings`, `uvicorn`); Phase 12 correction-service relies exclusively on Python stdlib + internal Phase 9/10/11 packages (zero third-party NTRIP/RTCM libraries added). | **Strong** |

---

## 4. Minimum Prerequisites Before Any Controlled-Network Deployment

The local NTRIP service MUST remain bound to `127.0.0.1` until **all** of the following prerequisites are implemented and independently verified:

1. TLS 1.2+/1.3 transport encryption for all NTRIP client and source connections (remediating **SEC-01**).
2. Managed secret storage, hashed/rotatable credentials, revocation, and per-mountpoint authorization (remediating **SEC-02**, **SEC-06**).
3. Pre-authentication connection caps, per-IP rate limiting, cumulative header read deadlines, and exclusive source-publisher limits (remediating **SEC-03**, **SEC-04**, **SEC-07**).
4. Explicit Go HTTP server timeouts and hardened container/CI security scanning (remediating **SEC-05**, **SEC-10**).
5. Redacted credential fields (`repr=False`) and complete rejection audit logging (remediating **SEC-09**, **SEC-11**).
6. Explicit ADR and authorization superseding the Phase 12 loopback-only lab restriction.
