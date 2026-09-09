# Phase 10 Pilot Evidence

## 1. Engineering pilot (synthetic loopback) — COMPLETE

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Local deterministic NTRIP test server (`valid` scenario, 8 synthetic
RTCM 3.x frames: `1005, 1077, 1087, 1005, 1230, 1077, 1006, 1087`):

- `probe`: ok=True, 8/8 frames, 8 CRC-valid, types
  `{1005: 2, 1077: 2, 1087: 2, 1230: 1, 1006: 1}`.
- `capture` (`loopback-001`): status COMPLETE, 8 valid / 0 invalid,
  0 reconnects, 0 dropped, buffer high-water 8, 8 forwarded.
- Stream SHA-256 `0402b7e8a364e9e0…` (full value in
  `pilot-summary.json`); arrival index 8 rows, monotonic, gap-free.
- Offline `validate-capture`: VALID, no findings.
- Phase 9 transport-compat check (`parse_stream` + inventory on
  `stream.rtcm3`, no admission/identity claim): 8 discovered, 8 valid,
  zero findings — the capture format replays through Phase 9 framing
  unchanged.
- Station mapping `TEST00SYN` (synthetic, unverified by design);
  authorization basis `synthetic-test-no-credentials`; no passwords in
  any artifact.

Outputs (outside Git): `${NLGCP_DATA_ROOT}/working/ntrip-pilot-synthetic/`
(`pilot-summary.json` at its root).

## 2. Fault-injection matrix — COMPLETE (automated suite)

87 Python + 30 Go tests cover: 401/403/404 terminal handling, HTML and
source-table-instead rejection, empty/malformed responses, split
delivery (1-byte reads), CRC quarantine, disconnect→reconnect with new
`connection_id` and continuing global sequence, stall bounds, capacity-1
lossless capture, path traversal, credential redaction, and Phase 9
bridge conversion + admission-format compatibility.

## 3. Real endpoint audit — BLOCKED (accepted outcome)

Searched the repository and `${NLGCP_DATA_ROOT}` for authorized/public
NTRIP evidence (`NTRIP/caster/mountpoint/MIRANET/NIGNET/SOGFA/CORS/
RTCM/endpoint/stream/source table`):

- `manifests/miranet_endpoint_check.txt`: MIRAnet web-portal
  connectivity check (HTTP 200 HTML page). Not an NTRIP caster; no
  mountpoints, no credentials, no RTCM.
- `manifests/nignet_endpoint_check.txt`: web checks only (TLS hostname
  mismatch on `www.nignet.net`; `nignet` over HTTP redirects to an
  unrelated site). Not an NTRIP caster.
- Environment: no `NLGCP_NTRIP_HOST/PORT/MOUNTPOINT/USERNAME/PASSWORD`
  configured → nothing authorized to connect to.
- Home-directory `cors-sample.rtcm3` (2757 bytes) / `cors-test.rtcm3`
  (151599 bytes) sit outside the data root with no capture provenance
  (who/when/where authorized, caster, mountpoint, arrival index) and
  were NOT admitted as authentic sources (unchanged from the Phase 9
  ruling). Read-only inspection only; nothing ingested.

No automatic connection was opened to any host: source-table retrieval
is permitted only against an authorized/public caster, and none exists.

## 4. Real pilot verdicts

```text
REAL LIVE INGESTION = BLOCKED (SOURCE_ACCESS_BLOCKED / AUTH_REQUIRED)
Authentic live RTCM connection: BLOCKED (no attempt made; no authorized target)
Real provider / station / mountpoint: none
Real capture: none (no bytes fabricated)
Observed real RTCM message types: unavailable
Phase 9 real-source admission: BLOCKED (no capture to admit)
Phase 9 real replay: BLOCKED (unchanged Phase 9 blocker)
Phase 8 EKAK correction-source availability: still BLOCKED
```

A live stream for another station, if one becomes available, must be
ingested under its own identity — never substituted for the Phase 8
EKAK00NGA selection.

## 5. Claims

Supported (demonstrated): NTRIP v2-first handshake with v1 tolerance,
fail-closed response validation, streaming RTCM framing across TCP
splits, CRC-24Q quarantine, genuine arrival timestamps, Phase 9
`CorrectionFrame` compatibility, bounded buffering without silent loss,
bounded reconnect with terminal awareness, stall detection, redacted
provenance, immutable capture layout with SHA-256 + arrival index,
offline validation/summarisation.

NOT claimed: live-service availability, correction accuracy,
centimetre positioning, fixed ambiguities, atmospheric/VRS improvement,
operational readiness, or any Phase 6/7 conclusion change.
Transport success ≠ positioning success.
