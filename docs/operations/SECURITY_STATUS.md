# NLGCP Security Status

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Source Audit:** [`13-day7-backend-security-review.md`](file:///home/excellence/NLGCP/docs/sprints/14-day-beta-sprint/13-day7-backend-security-review.md) (`NLGCP-EXP-2026-015`)
**Machine-Readable Register:** [`security_findings_register.json`](file:///home/excellence/NLGCP/research/archive/validation/security_findings_register.json)
**Last Updated:** 2026-11-26

---

## 1. Security Posture Summary

- **Loopback Lab Scope (`127.0.0.1`):** Strong fail-closed laboratory guardrails verified in source and tests (`SEC-14`): exact `127.0.0.1` bind enforcement, constant-time `hmac.compare_digest` credential verification, default TLS verification on outbound Phase 10 clients, non-root containers, immutable `NLGCP_DATA_ROOT`, secret redaction in logs (`caplog`-tested) and B-00 archive environment snapshots (`sanitize_environment_vars`), and strict fail-closed RTCM/VRS admission gates.
- **Non-Loopback / Operational Scope:** **NOT SAFE / BLOCKED.** All 13 open Day 7 findings (`2 CRITICAL`, `4 HIGH`, `4 MEDIUM`, `3 LOW`) remain **`OPEN`** as of 2026-11-26. None have been silently marked resolved.

---

## 2. Synchronized Security Findings Register (`SEC-01`–`SEC-14`)

| ID | Severity | Status | Blocks Non-Loopback? | Area & Summary |
|---|---|---|---|---|
| **SEC-01** | `CRITICAL` | `OPEN` | Yes | Plaintext HTTP Basic Auth & NTRIP v1 `SOURCE` without TLS (`services/correction-service`). |
| **SEC-02** | `CRITICAL` | `OPEN` | Yes | Static in-memory plaintext `CredentialStore`; zero auth on `apps/api`; no hashing/revocation/RBAC. |
| **SEC-03** | `HIGH` | `OPEN` | Yes | Unbounded pre-auth thread-per-connection in `LocalNtripCaster._accept_loop()`; no rate limiting. |
| **SEC-04** | `HIGH` | `OPEN` | Yes | No `max_sources` limit or exclusive single-writer mountpoint lock on `POST`/`SOURCE`. |
| **SEC-05** | `HIGH` | `OPEN` | Yes | Go ingestor `&http.Server` lacks `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, `IdleTimeout`. |
| **SEC-06** | `HIGH` | `OPEN` | Yes | `compose.yml` defaults `POSTGRES_PASSWORD=CHANGE_ME`; local NATS & Redis lack auth/TLS. |
| **SEC-07** | `MEDIUM` | `OPEN` | Yes | `_read_request_head()` enforces per-`recv()` timeout rather than cumulative header deadline. |
| **SEC-08** | `MEDIUM` | `OPEN` | No | `allow_unauthenticated_sourcetable` defaults to `True`. |
| **SEC-09** | `MEDIUM` | `OPEN` | Yes | Credential fields on `CasterConfig` / `ClientConfig` lack `repr=False`. |
| **SEC-10** | `MEDIUM` | `OPEN` | Yes | No `correction-service` Dockerfile; CI lacks container vulnerability & secret scanning beyond CodeQL. |
| **SEC-11** | `LOW` | `OPEN` | No | Missing structured audit log events on `405` and source-push auth/mountpoint rejections. |
| **SEC-12** | `LOW` | `OPEN` | No | `fetch_sourcetable()` malformed responses not counted in `ClientDiagnostics`. |
| **SEC-13** | `LOW` | `OPEN` | No | Chronic slow subscribers drop frames without eviction policy. |
| **SEC-14** | `INFORMATIONAL` | `VERIFIED_LAB_CONTROL` | No | Eight verified lab security invariants actively regression-tested. |

---

## 3. Archive & Secret Hygiene Rules (B-00)

- Never commit `.env`, API tokens, private keys, or NTRIP credentials into Git or `research/archive/`.
- `nlgcp archive provenance capture-env` restricts capture strictly to a minimal non-secret allowlist (`LANG`, `LC_ALL`, `TZ`, `NLGCP_DATA_ROOT`, `RTKLIB_SOURCE`, `VIRTUAL_ENV`) and strips any secret-bearing keys or values (unit-tested in `test_research_archive.py`).
