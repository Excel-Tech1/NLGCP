# Scientific Readiness and Beta Boundary

**Sprint:** NLGCP 14-Day Beta Sprint  
**Day:** 1 - audit and freeze  
**Date:** 2026-11-23  
**Status:** Day 1 deliverable

## 1. Decision

**Operational correction beta is not supportable from the current evidence.**

The only defensible beta is an internal engineering integration beta using clearly labelled synthetic or recorded test material in a loopback environment. It may prove that software boundaries, framing, local transport, status reporting, and diagnostics work together. It cannot prove correction quality, RTK performance, VRS improvement, live availability, or fitness for survey use.

This is a scope decision, not a change to any scientific conclusion.

## 2. Evidence state

| Evidence area | Observed state | Scientific consequence |
|---|---|---|
| 2011 southern NIGNET coordinates | OSGoF table gives coordinates for all 11 exact station codes dated 2011-01-01; frame, reference point, coordinate epoch, uncertainty, and monument continuity remain absent; 0 verified, 11 provisional | No admissible 2011 network configuration |
| 2011 navigation recovery | Automated recovery validated 66/66 BKG GPS+GLONASS products for the 33 primary dates; 132 CDDIS attempts were `AUTHENTICATION_REQUIRED`; no credentials used or persisted | Navigation availability is improved, but coordinates still block a positioning experiment |
| 2011 geometry | Best four-station case has 85,946 exact common epochs across 33 dates; provisional geometry includes 3 inside and 22 outside cases; candidate admissions are blocked | Exact epochs do not cure unverified station coordinates |
| 2024 verified coordinates | PRIDE PPP-AR static daily solutions in IGS20 support ABFC, EKAK, MGBO, and PHRI; `BKFP00NGA` is marked scientifically invalid; other station entries are absent | Only a small verified subset is available |
| 2024 overlap | DOY 026 is the only four-station ACCEPT overlap | Phase 3-8 evidence remains representative, not multi-day |
| Phase 3 | Real single-base runs are FLOAT-only; the shortest available control EKAK-PHRI (105.553 km) had horizontal RMSE 0.968 m, vertical 0.584 m, 3D 1.130 m, fix rate 0.0 | No RTK FIX or centimetre-accuracy claim |
| Phase 5 | Offline NRTK pilot is limited to the representative DOY 026 network; nearest reference outperformed the network-input mean | No general NRTK improvement claimed |
| Phase 6 | Reviewed identical-sample LOOCV, n=15,948: zero 3.076 m, IDW 3.352 m, nearest 3.757 m, planar 14.373 m; all four folds are extrapolation; BEST MODEL = ZERO | No spatial interpolation model is promoted |
| Phase 7 | Reviewed `ZERO` / `VRS_GEOMETRY_ONLY`; 78,060 virtual observations, 480/480 epochs, 30 GPS satellites per rotation; positioning not performed | Operational corrected VRS is not approved |
| Phase 8 | Fail-closed decision engine; reviewed `AUTO` selects single-base fallback via EKAK00NGA 105.553 km; VRS_ONLY is blocked; single-base history is FLOAT-only | A decision is available, but no validated correction product is |
| Phase 9 | No authentic RTCM capture under the admitted data root; synthetic replay only | Real RTCM semantics and receiver compatibility are unvalidated |
| Phase 10 | No authorized live CORS/NTRIP source; synthetic loopback only | No live availability, latency, or correction-age evidence |
| Phase 11 | 1005/1074/1084 bit-level encoders and synthetic message 4095 are encoded and parsed; no independent decoder, authentic observation, or verified coordinate is admitted; semantic RTCM validation NOT PERFORMED | No real RTCM/MSM correction output |
| Field readiness | Hardware, rover, antenna, firmware, and field logistics are `UNKNOWN` | No field acceptance or interoperability claim |

## 3. What can be claimed after a synthetic beta

Allowed, if independently verified:

- the synthetic encoders produce deterministic 1005/1074/1084 and 4095 bytes through the Phase 9 framing adapter;
- the local caster accepts and serves only explicitly synthetic frames in a loopback test;
- the client receives the frames and reports connection and frame counters;
- the status surface displays `SYNTHETIC_TEST_ONLY`, the blocked reasons, and the absence of scientific validity;
- unit, replay, fault-injection, and integration tests pass;
- no silent frame loss or unhandled error occurs in the tested paths.

Every such claim must retain the label **SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS**.

## 4. What must not be claimed

- "RTK FIX", "centimetre accuracy", "survey-grade", or "validated accuracy";
- "operational NTRIP caster" or "live correction service";
- "VRS improvement" or "NRTK improvement";
- "authentic RTCM compatibility" based on synthetic framing;
- "live CORS ingestion" based on a local test server;
- "field validated", "receiver compatible", or "available in Nigeria";
- any replacement of unavailable observations with synthetic inputs;
- any change to the Phase 6/7/8 scientific conclusions without new reviewed evidence.

## 5. Unlock conditions

A real correction beta would require, at minimum:

1. an admitted coordinate set with frame, epoch, reference point, uncertainty, and monument identity;
2. an authorized authentic observation/correction source;
3. a promoted correction model that has passed reviewed validation;
4. independent RTCM encoding/decoding and receiver compatibility evidence;
5. a caster and session design accepted under the security and distribution requirements;
6. rover/receiver hardware and a documented field plan;
7. control-point field acceptance, including FIX rate, error, TTFF, and recovery evidence;
8. independent review of the complete evidence chain.

None of these conditions is met by this audit.

## 6. Beta boundary

The sprint may exercise:

- the Phase 11 synthetic generator and Phase 9 framing boundary;
- a local, non-public Phase 12 lab caster;
- a local test NTRIP client;
- the Phase 13 status/control-plane surface, with no real users;
- local diagnostics and failure-path tests;
- Compose/CI reproducibility.

The sprint may not exercise or imply:

- an operational correction service;
- external client access;
- production identity, billing, or entitlement;
- real station or rover data without recorded authorization;
- field acceptance.

## 7. Scientific integrity statement

No scientific threshold, coordinate, observation, accuracy value, hardware capability, or field result was invented for this report. Where evidence is unavailable, the state is recorded as `UNKNOWN` or `BLOCKED`. Synthetic fixtures remain explicitly labelled and are not valid for scientific results.
