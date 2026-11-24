# Day 1 - Repository and Readiness Audit

**Sprint:** NLGCP 14-Day Beta Sprint  
**Day:** 1 - audit and freeze  
**Date:** 2026-11-23  
**Branch:** `research/nlgcp-14-day-beta-sprint`  
**HEAD at audit start:** `d789da0` (`Recover Southern Nigeria navigation data`)  
**Worktree at audit start:** clean; `git status --short --branch` reported only the branch name  
**Mode:** read-only repository and evidence inspection; no implementation, downloads, external connections, dependency changes, or raw-data changes

## 1. Scope and method

This audit answers three questions:

1. What exists in the repository and what can it actually do?
2. Which Phase 11-16 tasks can be attempted without fabricating scientific evidence?
3. What is the least complex beta that is defensible under the current blockers?

The audit used repository source, tests, Compose and CI configuration, status/evidence documents, the authoritative technical baseline, and the previously recorded external evidence. It did not perform a new GNSS calculation, RTCM semantic validation, live NTRIP probe, field test, or accuracy assessment.

## 2. Repository baseline

| Area | Observed state | Consequence for the sprint |
|---|---|---|
| Governance and status | `AGENTS.md`, `CURRENT_WORK.md`, `PROJECT_STATUS.md`, and `EVIDENCE_INDEX.md` exist; `README.md` still advertises Phase 1 | Status and evidence documents are usable; root README is stale and must not be treated as current phase truth |
| Technical baseline | `docs/technical-baseline/v1.0/` contains the system requirements, architecture, ADRs, runbooks, and phase context | Baseline governs any architecture change; no production redesign is justified by this audit |
| API | `apps/api` is a FastAPI application with `GET /health` only | No platform API, mountpoint catalogue, session, entitlement, or station-status route is exposed |
| Web | `apps/web` is a static Next.js page stating that no live corrections or scientific results are available | No operator dashboard or data integration exists |
| Go ingestor | `services/gnss-ingestor` contains the Phase 10 NTRIP transport library and a health/readiness process; `cmd/ingestor` does not start a live NTRIP client | Transport code is reusable, but no live CORS ingestion runtime is wired |
| Correction service | `services/correction-service/README.md` is a reserved placeholder | No Phase 12 NTRIP caster or correction publisher exists |
| Station monitor | `services/station-monitor/README.md` is a reserved placeholder | No operational station monitoring service exists |
| NRTK engine | `services/nrtk-engine` is a C/C++ health executable and test only | No real-time NRTK processing is implemented |
| Phase 9 replay | `research/rtcm_replay` implements framing, CRC-24Q, admission, inventory, timing, replay, buffering, and a synthetic pilot | Replay/framing foundation exists; authentic RTCM pilot is blocked |
| Phase 10 ingestion | `research/ntrip_ingestion` and `services/gnss-ingestor/internal/ntrip` implement client-side NTRIP transport and capture | No authorized live source; no caster; real-provider validation is blocked |
| Phase 11 generation | `research/rtcm_generation` has admission, registry, field/bit utilities, synthetic encoder, Phase 9 framing adapter, provenance, and a Phase 12 handoff schema | Only synthetic lab frames are validated; no real RTCM/MSM encoder or operational correction generation |
| Database | `database/` contains the Phase 1 baseline and Phase 2 station-registry migrations | Metadata storage exists; no users, devices, entitlements, sessions, or correction audit tables |
| Compose | `compose.yml` defines PostgreSQL/PostGIS, NATS JetStream, Redis, API, web, and the ingestor health service, all bound to localhost or the Compose network | Local engineering integration is possible; no correction-service, station-monitor, or NRTK service is defined |
| CI | `.github/workflows/ci.yml` covers Python, Go, C++, web, and Compose syntax; `.github/workflows/security.yml` adds CodeQL and pull-request dependency review | Build/test/security baseline exists; no container scan, secret scan, integration-to-caster test, or field/acceptance test |
| Sprint documentation | No prior `docs/sprints/14-day-beta-sprint/` files were present | These Day 1 documents establish the sprint record without overwriting earlier phase evidence |

## 3. Confirmed capabilities

- The repository has a working multi-language quality gate: Ruff, mypy, pytest, Go vet/tests, CTest, ESLint, TypeScript, Next.js build, and Compose syntax checks.
- Phase 2 metadata and inventory modules are implemented as data-layer code and have synthetic/unit coverage.
- Phase 8 provides a fail-closed correction-mode decision boundary.
- Phase 9 provides deterministic RTCM 3.x transport framing and CRC-24Q parsing for captured/synthetic bytes.
- Phase 10 provides a substantial client-side NTRIP transport library with handshake, framing, capture, reconnect, admission, redaction, and bounded-buffer behavior.
- Phase 11 provides deterministic synthetic frame generation through the Phase 9 framing path and explicit fail-closed admission gates.
- Local Compose infrastructure is sufficient for a loopback-only engineering integration exercise.
- CI and repository controls are sufficient to verify that no generated artifact is silently promoted to operational status.

## 4. Confirmed gaps and risks

### 4.1 Scientific gaps

- The 2011 southern network has no verified coordinate set; all 11 station coordinates remain provisional.
- The 2024 positioning evidence is limited to DOY 026 and a small verified subset of stations.
- No promoted spatial interpolation model exists; the Phase 6 zero control remains best.
- VRS remains `ZERO` / `VRS_GEOMETRY_ONLY`; operational VRS is not approved.
- Phase 3 single-base results are FLOAT-only; no RTK FIX or centimetre-accuracy claim exists.
- No authentic RTCM capture, independent RTCM semantic validation, or rover field result exists.

### 4.2 Engineering gaps

- Phase 12 has no caster, mountpoint catalogue, session management, or correction publisher.
- Phase 13 has no real API surface, authentication, authorisation, entitlement model, or data-driven UI.
- Phase 14 has no metrics backend, dashboards, alert routing, SLOs, or central log correlation.
- Phase 15 has development controls only; it lacks production authentication, managed secrets, TLS termination, audit logging, container scanning, and network-zone enforcement.
- Phase 16 has no hardware inventory, field plan, control-point survey, rover interoperability matrix, or field acceptance evidence.
- The Go ingestor process does not start a live stream; its README describes transport capability that is not currently orchestrated by `cmd/ingestor`.
- The root README's Phase 1 statement is stale relative to the phase record.

### 4.3 Documentation and evidence risks

- Phase 10 documentation and README language can be read as implying a running live-ingestion service; the process is currently a health boundary only.
- Phase 11's registry contains real message-family names, but registry presence is not support. The real families are `SCAFFOLDED`; only message 4095 is `SYNTHETICALLY_VALIDATED`.
- Phase 9 encoder and validator share the same CRC/framing implementation; this proves internal consistency, not independent RTCM compatibility.
- Several phase documents are preserved on historical branches; this branch must use the current recorded review state rather than older pilot IDs.

## 5. Quality-gate baseline

The last recorded full gate before this audit passed: Ruff, ESLint, mypy (220 source files), TypeScript, pytest (656 passed, 6 skipped), Go vet/tests, CTest, and the Next.js production build. The Phase 2 recovery is recorded in `EVIDENCE_INDEX.md` and `docs/research/southern-coordinate-provenance-navigation-recovery.md`.

This Day 1 audit adds documentation only. The post-documentation check and its result are recorded in `07-day1-report.md`.

## 6. Day 1 audit conclusion

The repository is not ready for a real-user correction beta. The defensible beta is an internal, local, fixture-fed engineering integration beta that exercises the existing synthetic Phase 11 output, a lab NTRIP caster built during the sprint, the Phase 13 status surface, and Phase 14 diagnostics.

The audit does not authorize:

- operational RTCM or NTRIP correction output;
- external users or real credentials;
- real rover or field claims;
- RTK FIX, accuracy, availability, or VRS-improvement claims;
- using synthetic data as a substitute for unavailable observations.

## 7. Evidence ledger

- `git status --short --branch`; `git log -5 --oneline` - branch and HEAD inspection.
- `docs/phase11-correction-generation-scaffold.md` - Phase 11 scope and CORS-unblock procedure.
- `research/rtcm_generation/src/nlgcp_rtcm_generation/` - registry, admission, generator, encoder, validation, handoff.
- `research/rtcm_generation/tests/test_scaffold.py` - 14 synthetic-only tests.
- `research/rtcm_replay/src/nlgcp_rtcm_replay/crc.py`; `framing.py` - CRC-24Q and framing implementation.
- `services/gnss-ingestor/cmd/ingestor/main.go`; `services/gnss-ingestor/internal/ntrip/` - health boundary and client transport.
- `services/correction-service/README.md`; `services/station-monitor/README.md` - Phase 12 and monitoring placeholders.
- `apps/api/src/nlgcp_api/main.py`; `apps/api/tests/`; `apps/web/app/page.tsx` - Phase 13 boundary.
- `database/alembic/versions/` - schema scope.
- `compose.yml`; `.github/workflows/ci.yml`; `.github/workflows/security.yml` - local and CI topology.
- `docs/technical-baseline/v1.0/docs/16-...md` through `24-...md` - distribution, API, security, observability, validation, and roadmap requirements.
- `docs/research/southern-coordinate-provenance-navigation-recovery.md`; `docs/research/southern-nigeria-data-audit.md` - coordinate and geometry blockers.
- `docs/phase8-hybrid-correction-decision-engine.md`; `research/hybrid_decision_engine/` - correction-mode gates.
