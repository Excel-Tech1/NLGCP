# B-09 Live CORS Integration & Nigerian Provider Assessment Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-09 — Live CORS Integration (Stage A + Stage B Assessment)  
**Date:** 2026-11-27  
**Classification:**  
- **Stage A (Credential-Free Recorded & Local Loopback Ingestion):** `IMPLEMENTED` | `UNIT_TESTED` & `INTEGRATION_TESTED`  
- **Stage B (External Live Nigerian CORS Integration):** **`BLOCKED_EXTERNAL_ACCESS`** (no authorized commercial or institutional NTRIP credentials present; zero unauthorized endpoints probed)  
- **Operational Approval:** `NOT_APPROVED` (`OPERATIONAL_APPROVED = FORBIDDEN`)

---

## 1. Nigerian CORS Provider Assessment

Per ADR-001 (source-independent ingestion), NLGCP separates provider adapters from core positioning/correction logic. Publicly documented Nigerian CORS providers were assessed without fabricating endpoints, IP addresses, or credentials:

| Provider Code | Operator & Website | Access Tier | Coverage & Technical Notes | Stage B Status | Onboarding Path |
|---|---|---|---|---|---|
| **`SOGPOS_SACREDION`** | Sacredion Nigeria Limited (with Tersus GNSS) — `https://www.sacredioncors.com/` | `COMMERCIAL_SUBSCRIPTION` | Commercial Nigerian CORS network with stations reported across Lagos, Benin City, Port Harcourt, Warri, Jos, Osun, and Minna. Standard NTRIP client access requires an active commercial account/subscription; specific caster IP/port/mountpoints are delivered via the subscriber portal or SOGPOS Mobile app. | **`BLOCKED_EXTERNAL_ACCESS`** | Commercial subscription / agreement (`info@sacredioncors.com`, `admin@sacredioncors.com`); configure `NLGCP_SOGPOS_*` env vars |
| **`NIGNET_OSGOF`** | Office of the Surveyor General of the Federation (OSGoF) — `https://osgof.gov.ng/` | `PUBLIC_INSTITUTIONAL` | National geodetic backbone; historical 2011 & 2024 RINEX archives verified in B-04. No public unauthenticated NTRIP caster is exposed; live streaming requires formal institutional agreement and credentials. | **`BLOCKED_EXTERNAL_ACCESS`** | Formal request to OSGoF Geodesy Department; configure `NLGCP_NIGNET_*` env vars |
| **`CORSLOCATE_NG`** | Pink Project NG Ltd — `https://corslocate.ng/` | `COMMERCIAL_MARKETPLACE` | Commercial Nigerian CORS aggregator/marketplace focused on Lagos and multi-operator subscriptions with instant NTRIP credential provisioning post-payment. | **`BLOCKED_EXTERNAL_ACCESS`** | Paid operator subscription; configure `NLGCP_CORSLOCATE_*` env vars |
| **`NLGCP_LOCAL_STAGE_A`** | NLGCP Engineering Lab | `LOCAL_LAB_STAGE_A` | Offline recorded RTCM 3.x streams + `127.0.0.1` loopback NTRIP caster (`NLGCP_TEST` / `NLGCP_VRS_EXP`) for deterministic transport and bus integration testing. | **`STAGE_A_AVAILABLE_OFFLINE`** | Local workspace / `${NLGCP_DATA_ROOT}` |

---

## 2. Stage A Implementation Wired to B-08 Event Contracts

Implemented in [providers.py](file:///home/excellence/NLGCP/research/ntrip_ingestion/src/nlgcp_ntrip_ingest/providers.py), [b09_ingestion.py](file:///home/excellence/NLGCP/research/ntrip_ingestion/src/nlgcp_ntrip_ingest/b09_ingestion.py), and CLI [run_b09_cors_assessment.py](file:///home/excellence/NLGCP/scripts/run_b09_cors_assessment.py):

1. **Read-Only Recorded RTCM Ingestion (`ingest_recorded_rtcm_file_to_event_bus`):**
   - Streams bytes incrementally through Phase 10 `StreamingFramer` with CRC-24Q verification;
   - Quarantines corrupt frames (`frames_crc_invalid_quarantined`) and emits redacted B-08 `AUDIT_SECURITY` (`RTCM_CRC24Q_QUARANTINED`) events rather than forwarding bad frames;
   - Enforces fail-closed station identity mapping (`STATION_IDENTITY_UNVERIFIED` blocks frame forwarding by default);
   - Emits canonical B-08 `EventEnvelope` (`nlgcp.events.v1`, `correction.replay.<STATION>` or `correction.live.<STATION>`) with `operational_approved = False` and `scientific_validity = "NOT_ASSESSED_TRANSPORT_ONLY"`.
2. **Loopback Live Client Integration:** Verified end-to-end from Phase 12 `LocalNtripCaster` (`127.0.0.1`) → `LocalNtripClient` → `ingest_rtcm_bytes_to_event_bus()` → `BoundedEventBus` (`correction.live.EKAK00NGA`).
3. **Fail-Closed Stage B Gate (`evaluate_stage_b_provider_gate`):** Verifies presence of all six non-empty runtime environment variables (`<PREFIX>_{HOST,PORT,MOUNTPOINT,USERNAME,PASSWORD,AUTHORIZATION_BASIS}`) without ever logging secret values; defaults strictly to `BLOCKED_EXTERNAL_ACCESS`.

---

## 3. Prerequisites to Unblock Stage B Live Ingestion

Before connecting to **SOGPOS (`sacredioncors.com`)**, **NIGNET**, or any commercial Nigerian CORS caster:
1. Obtain written operator/subscription authorization and legitimate NTRIP credentials (never committed to Git or `.env.example`);
2. Verify station monument coordinates independently (PPP/ITRF frame & antenna PCO/height) before admitting any live stream to Phase 8/11 scientific processing (`STATION_IDENTITY_UNVERIFIED` remains enforced otherwise);
3. Perform controlled Stage B read-only capture under `${NLGCP_DATA_ROOT}/raw/rtcm-captures/` with SHA-256 provenance manifests and non-RTKLIB independent message auditing (B-07).

---

## 4. Verification & Reproducibility

- Tests: [test_b09_cors_ingestion.py](file:///home/excellence/NLGCP/research/ntrip_ingestion/tests/test_b09_cors_ingestion.py).
- Command:
  ```bash
  .venv/bin/python scripts/run_b09_cors_assessment.py
  .venv/bin/python -m pytest research/ntrip_ingestion/tests/test_b09_cors_ingestion.py -v
  ```
