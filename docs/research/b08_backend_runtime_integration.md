# B-08 Backend Runtime Integration & Control-Plane API Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-08 — Backend Runtime Integration  
**Date:** 2026-11-27  
**Classification:**  
- **Implementation:** `IMPLEMENTED`  
- **Testing:** `UNIT_TESTED` & `INTEGRATION_TESTED` (Python + Go; `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`)  
- **Operational Status:** `NOT_APPROVED` (`127.0.0.1` loopback-only lab boundary strictly preserved; `OPERATIONAL_APPROVED = FORBIDDEN`)

---

## 1. Objective & Architectural Alignment

Milestone **B-08** addresses the Day 7 backend integration gaps (`BE-01`, control-plane `/api/v1` readiness, PostgreSQL/PostGIS runtime schema, bounded NATS JetStream event contracts, and low-risk Day 7 security/reliability hardening) while strictly preserving every baseline ADR:

- **ADR-005 (NATS JetStream):** Versioned event envelopes (`schema_version = "nlgcp.events.v1"`) with strict subject validation (`correction.live.*`, `correction.replay.*`, `correction.decision.*`, `correction.rtcm.*`, `audit.security.*`), bounded retention (`max_msgs`, `max_bytes`, `max_age_s`), deterministic `BoundedEventBus`, and honest `probe_nats_endpoint()` (`UNAVAILABLE` when no local broker is running).
- **ADR-006 (PostgreSQL + PostGIS):** Alembic migration [`9c4a7e2f1b08_add_b08_runtime_control_plane_tables.py`](file:///home/excellence/NLGCP/database/alembic/versions/9c4a7e2f1b08_add_b08_runtime_control_plane_tables.py) chained cleanly off Phase 2 head `5d50ff0e583d`, adding `cors_providers`, `ntrip_mountpoints` (with database-level `CHECK (operational_approved = false)`), `correction_decisions`, `rtcm_generation_runs` (with `CHECK (classification <> 'OPERATIONAL_APPROVED')`), `ingestion_sessions`, and `control_plane_audit_events`. Zero fabricated seed rows are inserted.
- **ADR-007 (Control Plane vs. Correction Plane Separation):** All 10 read-only `/api/v1` endpoints mounted on `apps/api` ([v1_router.py](file:///home/excellence/NLGCP/apps/api/src/nlgcp_api/v1_router.py)) strictly separate control-plane queries from real-time RTCM streams (zero RTCM frames transit HTTP per epoch) and preserve `GET /health` byte-identical.
- **ADR-011 & ADR-012 (Fail-Closed Integrity & Hybrid Routing):** Phase 8 → Phase 11 runtime bridge ([decision_bridge.py](file:///home/excellence/NLGCP/services/correction-service/src/nlgcp_correction_service/decision_bridge.py)) translates `CorrectionDecision` into `CorrectionGenerationRequest` fail-closed: `OPERATIONAL_APPROVED` raises `DecisionBridgeError`, `VRS` stays blocked (`VRS_OPERATIONAL_NOT_APPROVED`), and authentic single-base decisions without an admitted live stream remain honestly blocked (`AUTHENTIC_INPUT_SOURCE_UNAVAILABLE`).

---

## 2. Implemented Components

| Component | Location | Capabilities & Safety Invariants |
|---|---|---|
| Event Contracts & JetStream Boundary | [events.py](file:///home/excellence/NLGCP/services/correction-service/src/nlgcp_correction_service/events.py) | `EventEnvelope` (`nlgcp.events.v1`), SHA-256 payload digest, `NatsJetStreamConfig` (loopback-first, bounded retention), `BoundedEventBus` with overflow accounting, `probe_nats_endpoint()` |
| Phase 8 → Phase 11 Runtime Bridge (`BE-01`) | [decision_bridge.py](file:///home/excellence/NLGCP/services/correction-service/src/nlgcp_correction_service/decision_bridge.py) | `decision_to_generation_request()` and `execute_decision_to_rtcm()` preserving fail-closed VRS/operational/authentic-input gates |
| Read-Only `/api/v1` Control-Plane Router | [v1_router.py](file:///home/excellence/NLGCP/apps/api/src/nlgcp_api/v1_router.py), [main.py](file:///home/excellence/NLGCP/apps/api/src/nlgcp_api/main.py) | All 10 Day 7 endpoints (`/api/v1/health/summary`, `/stations`, `/stations/{id}`, `/correction/engine/status`, `/correction/rtcm/stats`, `/caster/status`, `/caster/clients`, `/caster/mountpoints`, `/diagnostics`, `/diagnostics/errors`, `/readiness/scientific`) |
| PostgreSQL/PostGIS Migration | [9c4a7e2f1b08_add_b08_runtime_control_plane_tables.py](file:///home/excellence/NLGCP/database/alembic/versions/9c4a7e2f1b08_add_b08_runtime_control_plane_tables.py) | Chained off `5d50ff0e583d`; reversible `upgrade()` / `downgrade()`; DB-level operational-promotion check constraints |
| Go Ingestor Timeout Hardening (`SEC-05`) | [main.go](file:///home/excellence/NLGCP/services/gnss-ingestor/cmd/ingestor/main.go), [main_test.go](file:///home/excellence/NLGCP/services/gnss-ingestor/cmd/ingestor/main_test.go) | Explicit `ReadHeaderTimeout=5s`, `ReadTimeout=10s`, `WriteTimeout=10s`, `IdleTimeout=60s`, `MaxHeaderBytes=8192`, bounded `5s` graceful shutdown context |
| Caster Lab Security Hardening (`SEC-03/04/07/09/11`) | [config.py](file:///home/excellence/NLGCP/services/correction-service/src/nlgcp_correction_service/config.py), [diagnostics.py](file:///home/excellence/NLGCP/services/correction-service/src/nlgcp_correction_service/diagnostics.py), [caster.py](file:///home/excellence/NLGCP/services/correction-service/src/nlgcp_correction_service/caster.py) | `repr=False` on secret fields (`SEC-09`); cumulative monotonic header deadline (`SEC-07`); bounded pre-auth semaphore (`SEC-03`); exclusive per-mountpoint source lease + `max_sources` (`SEC-04`); redacted audit logging & bounded fault ring buffer on `405`/source rejections (`SEC-11`); secret-free active session tracking |

---

## 3. Day 7 Security Findings Status After B-08

| Finding | Status After B-08 | Notes |
|---|---|---|
| `SEC-01` (TLS termination) | **OPEN** | Loopback `127.0.0.1` boundary remains strictly enforced; non-loopback deployment still forbidden |
| `SEC-02` (Production auth / RBAC / API auth) | **OPEN** | Deferred to Phase 15 production security hardening |
| `SEC-03` (Pre-auth connection cap) | **PARTIALLY REMEDIATED (LAB)** | Bounded `max_pre_auth_connections` semaphore added; per-IP rate limiting remains required before any non-loopback deployment |
| `SEC-04` (Source concurrency & exclusive lease) | **REMEDIATED (LAB)** | Exclusive per-mountpoint source lease + `max_sources` verified in unit/integration tests |
| `SEC-05` (Go ingestor HTTP server timeouts) | **REMEDIATED** | Explicit timeouts + bounded shutdown context verified in `cmd/ingestor/main_test.go` |
| `SEC-06` (Compose secret defaults & bus auth) | **OPEN** | Deferred to Phase 15 production deployment; all Compose ports remain `127.0.0.1`-bound |
| `SEC-07` (Cumulative header read deadline) | **REMEDIATED** | Monotonic deadline enforced across `_read_request_head()`, slowloris regression tested |
| `SEC-08` (Unauthenticated source-table policy) | **OPEN (INTENTIONAL LAB DEFAULT)** | Controlled-network policy review deferred to Phase 15 |
| `SEC-09` (Secret `repr()` redaction) | **REMEDIATED** | `repr=False` on `client_credentials`, `source_credentials`, and `ClientConfig.password` |
| `SEC-10` (Container/CI security scanning) | **OPEN** | Deferred to Phase 15 |
| `SEC-11` (Audit logging on 405/source rejections) | **REMEDIATED** | Structured audit events + bounded redacted fault ring buffer added and tested |
| `SEC-12`, `SEC-13` | **OPEN (LOW)** | Documented follow-on refinements |
| `SEC-14` (Loopback & fail-closed controls) | **PRESERVED / VERIFIED** | All existing Phase 12 security controls intact |

---

## 4. Verification & Reproducibility

- Tests: [test_v1_api.py](file:///home/excellence/NLGCP/apps/api/tests/test_v1_api.py), [test_b08_runtime_integration.py](file:///home/excellence/NLGCP/services/correction-service/tests/test_b08_runtime_integration.py), [main_test.go](file:///home/excellence/NLGCP/services/gnss-ingestor/cmd/ingestor/main_test.go).
- Commands:
  ```bash
  .venv/bin/python -m pytest apps/api/tests services/correction-service/tests -q
  cd services/gnss-ingestor && go test -v ./...
  ```
- **Limitations:** No live PostgreSQL, NATS JetStream, or Redis container was mutated or assumed active during offline unit verification; database migrations should be applied via `.venv/bin/alembic upgrade head` against a running local Compose stack when operational testing begins.
