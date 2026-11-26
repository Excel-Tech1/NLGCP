# NLGCP Deployment Status

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Operational Approval State:** **`OPERATIONAL_APPROVED = FORBIDDEN`**
**Last Updated:** 2026-11-26

---

## 1. Current Deployment Classification

| Environment | Status | Details & Evidence |
|---|---|---|
| **Local Development & Loopback Research Lab (`127.0.0.1`)** | **Active (Lab-Only)** | Local Python `.venv`, Docker Compose services (`127.0.0.1`-bound Postgres/PostGIS, NATS, Redis, `apps/api`, `apps/web`), Phase 12 loopback NTRIP caster (`NLGCP_TEST` synthetic; `NLGCP_VRS_EXP` isolated offline research replay). |
| **Controlled Private / Campus Network** | **BLOCKED** | Forbidden until all CRITICAL/HIGH Day 7 security findings (`SEC-01`–`SEC-07`, `SEC-09`, `SEC-10`) are remediated and an explicit ADR supersedes the loopback-only boundary. |
| **Public / Production Operational Service** | **NOT APPROVED / FORBIDDEN** | Blocked by missing authorized live Nigerian CORS streams (`GN-01`), zero genuine RTK integer ambiguity resolution (`B-03`, `FIX = 0.0%`), non-causal offline atmospheric modeling (`B-08`), single-decoder MSM4 validation (`B-06`), missing security hardening (`B-09`), absent monitoring (`Phase 14`), and zero field validation (`B-10`). |

---

## 2. Deployment Boundaries & Non-Regression Controls

1. `CasterConfig` and `ClientConfig` in `services/correction-service` programmatically reject every host string other than exact `"127.0.0.1"`.
2. Every host port published in [`compose.yml`](file:///home/excellence/NLGCP/compose.yml) binds strictly to `127.0.0.1`.
3. `services/correction-service` is NOT containerized or deployed as a long-running system daemon yet (`SEC-10`, `BE-03`).
4. Phase 13 web dashboard UI deployment was formally deferred during the Day 7 checkpoint (`12-day7-backend-architecture-audit.md`).

---

## 3. Minimum Gate Checklist Before Controlled-Network Staging

- [ ] Remediate `SEC-01` (TLS 1.2+/1.3 termination; disable plaintext NTRIP v1 `SOURCE`)
- [ ] Remediate `SEC-02` & `SEC-06` (managed secrets, hashed/rotatable credentials, RBAC, remove `CHANGE_ME` Compose defaults, enable NATS/Redis auth + TLS)
- [ ] Remediate `SEC-03`, `SEC-04`, `SEC-07` (pre-auth socket caps, rate limiting, exclusive mountpoint publisher lock, cumulative header deadline)
- [ ] Remediate `SEC-05`, `SEC-09`, `SEC-10`, `SEC-11` (Go HTTP server timeouts, `repr=False` on secrets, container/secret CI scanning, complete audit logs)
- [ ] Adopt explicit superseding ADR lifting the Phase 12 loopback-only lab restriction.
