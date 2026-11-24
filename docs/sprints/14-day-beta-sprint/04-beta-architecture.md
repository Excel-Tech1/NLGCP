# Beta Architecture Map

**Sprint:** NLGCP 14-Day Beta Sprint  
**Day:** 1 - audit and freeze  
**Date:** 2026-11-23  
**Beta class:** Internal, local, fixture-fed engineering integration beta  
**Status:** Day 1 deliverable; target architecture only

## 1. Scope boundary

This beta exists to integrate and exercise software boundaries. It is not a correction service for real users.

In scope:

- synthetic Phase 11 frames;
- Phase 9 framing and CRC parsing;
- a local, loopback-only NTRIP caster;
- a local test NTRIP client;
- a read-only status/API surface and a static or minimally dynamic operator page;
- structured diagnostics;
- Compose and CI reproducibility.

Out of scope:

- public or internet-reachable caster;
- real NTRIP credentials or mountpoints;
- real CORS ingestion;
- real RTCM corrections or receiver interoperability claims;
- user accounts, billing, entitlements, or production authentication;
- field testing, rover accuracy, RTK FIX, or availability claims;
- VRS or NRTK performance claims.

## 2. Current architecture

```text
Control plane (local development only)
  Next.js web placeholder
        |
  FastAPI /health only
        |
  PostgreSQL/PostGIS station metadata

Correction / research plane
  Phase 10 Go NTRIP client library (not started by cmd/ingestor)
        |
  Phase 10 capture and Python research bridge
        |
  Phase 9 replay and framing
        |
  Phase 8 hybrid decision
        |
  Phase 11 synthetic generator / Phase 12 handoff schema
        |
  [Phase 12 caster: ABSENT]
```

Current observed boundaries:

- `apps/api` owns only process health; it does not calculate positions or publish corrections.
- `apps/web` is static and does not consume the API.
- `services/gnss-ingestor` exposes health/readiness and contains client transport code; `cmd/ingestor` does not start a live stream.
- `services/correction-service` and `services/station-monitor` are placeholders.
- `services/nrtk-engine` is a health executable only.
- NATS JetStream is available locally but no correction publisher/consumer workflow is running.
- The database stores station metadata, not sessions, users, devices, or entitlements.

## 3. Target Day 14 lab architecture

```text
Synthetic fixture (explicitly labelled)
        |
        v
Phase 11 generator (SYNTHETIC_TEST_ONLY; 4095 test frame or 1005/1074/1084 synthetic vectors)
        |
        v
Phase 9 framing / CRC-24Q
        |
        v
Phase 12 local lab caster
  - loopback bind only
  - one synthetic mountpoint
  - no public advertisement
        |
        v
Local test NTRIP client
        |
        v
Phase 13 read-only status surface
  - synthetic label
  - mountpoint state
  - blocked reasons
        |
        v
Phase 14 local diagnostics
  - structured logs
  - connection/frame/CRC counters
  - explicit scientific-validity = NOT_ASSESSED
```

The real correction path remains blocked:

```text
Authorized CORS -> live ingestion -> admitted capture -> Phase 8 decision
-> approved model -> real RTCM encoder -> independent validation
-> authenticated caster -> real rover -> field acceptance
```

Every segment after "Authorized CORS" is absent or blocked in this repository.

## 4. Component responsibilities

| Component | May do | Must not do |
|---|---|---|
| Phase 11 generator | Emit deterministic synthetic frames 4095/1005/1074/1084 through the Phase 9 adapter; enforce admission gates | Emit `OPERATIONAL_APPROVED`; claim RTCM semantic conformance or receiver compatibility from synthetic vectors; accept authentic input without admitted evidence |
| Phase 9 framing | Frame, length-check, and CRC-check test bytes | Treat framing/CRC success as semantic or scientific validation |
| Phase 12 lab caster | Serve a labelled synthetic mountpoint over loopback; manage bounded local sessions; expose status | Advertise an operational service; accept real user credentials; forward to a public network |
| Local test client | Connect, parse, and report synthetic frames and failures | Be represented as a real rover or field result |
| Phase 13 API/web | Show service state, classification, and blockers; expose read-only local status | Store real user data; issue NTRIP credentials; claim correction quality |
| Phase 14 diagnostics | Record counts, timestamps, and failures; correlate by local session/request ID | Invent SLOs, availability, or scientific health from process liveness |
| Database | Hold existing metadata; optionally hold synthetic session records if explicitly labelled | Mix synthetic and authentic records without provenance; store secrets |
| Compose | Run the local stack with loopback ports and healthchecks | Expose services to the public interface; become a production deployment |

## 5. Data and trust boundaries

1. **Synthetic fixture boundary:** every synthetic frame and artifact carries the explicit label; no fixture may be relabelled as authentic.
2. **Correction boundary:** the caster serves only the synthetic mountpoint and must fail closed for unknown or unlabelled input.
3. **Control-plane boundary:** the API is a status/control surface, not a per-epoch GNSS processor and not a correction transport.
4. **Network boundary:** all beta ports bind to `127.0.0.1` or an isolated Compose network. No external interface or public DNS name is part of the beta.
5. **Credential boundary:** no real NTRIP credentials, tokens, `.env` secrets, or private keys are created or committed. Local test credentials, if needed, are generated outside version control and are not reusable.
6. **Evidence boundary:** logs and test results record what happened, not what should have happened. Missing data remains missing.

## 6. Failure behavior

The beta must fail closed:

- unknown message family or unvalidated encoder: reject or emit no correction;
- missing provenance or classification: reject;
- CRC failure: quarantine/record, do not forward as valid;
- buffer exhaustion: apply an explicit policy and record it; never silently drop;
- caster unavailable: client reports failure and does not synthesize success;
- stale or disconnected session: expose the state, do not advertise healthy service;
- scientific validity: always `NOT_ASSESSED_BY_THIS_BETA`.

## 7. Deployment shape

The beta uses the existing Docker Compose development pattern:

- PostgreSQL/PostGIS, NATS JetStream, and Redis remain local infrastructure;
- API and web remain localhost-bound;
- the ingestor health service and a new local correction service remain localhost-bound;
- all mounts remain under the configured external `NLGCP_DATA_ROOT` with `data/raw/` treated as immutable;
- no Kubernetes, cloud ingress, billing, production authentication, or public TLS termination is introduced.

## 8. Architecture change control

Adding a local lab caster and local diagnostics is an implementation of already-documented phase boundaries, not a redesign of the production architecture. Any proposal to:

- expose a public caster;
- add production authentication or entitlement;
- change the control/correction plane separation;
- use real correction data;
- alter the scientific decision policy;

requires an explicit ADR or documented superseding decision and review before implementation.

## 9. Day 1 conclusion

The target beta can demonstrate software integration and fail-closed behavior. It cannot demonstrate a correction service. The architecture must make that distinction visible in every endpoint, mountpoint, log record, and UI label.
