# Phase 10 — Live CORS / NTRIP Ingestion

## 1. Purpose

Phase 10 builds the fail-closed, provenance-preserving live correction
ingestion layer: an authorized NTRIP/CORS source → connection admission
→ NTRIP handshake → RTCM byte stream → streaming framer → CRC-24Q →
arrival timestamp → `CorrectionFrame` → bounded buffer/backpressure →
consumer frames + immutable capture + metrics + provenance.

```text
Recorded RTCM → Phase 9 adapter → CorrectionFrame
Live NTRIP    → Phase 10 adapter → CorrectionFrame
```

Downstream consumers cannot tell live apart from replay. After
Phase 10 the lab can, once authorized, feed genuine arrival timing back
through Phase 9 deterministic replay (closing the Phase 9 real-data
blocker) without changing any Phase 9 scientific rule.

## 2. Non-goals (explicitly out of scope)

No NLGCP-produced RTCM corrections, no VRS RTCM generator, no MSM
encoder, no correction-generation engine, no rover-facing NTRIP caster,
no operational network RTK, and no centimetre-accuracy, ambiguity-fix,
or validated-positioning claims. Those belong to Phase 11+.

## 3. Placement

Production live-stream transport lives in Go
(`services/gnss-ingestor/internal/ntrip/`: config, auth, sourcetable,
handshake, framing, crc, reconnect, admission, buffer, client, capture,
metrics, subjects) extending the existing ingestor service. The Python
research bridge (`research/ntrip_ingestion/src/nlgcp_ntrip_ingest/`)
provides capture validation, scientific inventory, Phase 9 integration,
and operator reporting/CLI. Both share wire conventions; Phase 9 CRC-24Q
and framing semantics are reused, not redefined.

## 4. Authorized-source policy

Automatic connection is permitted only to (1) a public endpoint
requiring no credentials, (2) an endpoint whose credentials are already
present in project-authorized environment/config, or (3) an endpoint
documented as authorized for this research. Otherwise `AUTH_REQUIRED`
or `SOURCE_ACCESS_BLOCKED`, fail closed. No invented credentials, no
brute-forced mountpoints, no credential guessing, no access-control
evasion, no enumeration of arbitrary hosts.

## 5. Configuration

`NLGCP_NTRIP_HOST/PORT/MOUNTPOINT/USERNAME/PASSWORD/TLS/USER_AGENT`
(+ `NLGCP_NTRIP_GGA` for rover-GGA streams). Secrets never required for
tests, never printed in logs, never stored in capture metadata;
redaction is tested. TLS validates by default; an explicit diagnostic
insecure mode is labelled unsafe and never default.

## 6. NTRIP scope

NTRIP v2 spoken first; `ICY 200 OK` tolerated. `200` accepted only with
a non-HTML, non-source-table body. `401/403` → terminal auth failure,
`404` → terminal mountpoint-not-found, anything else fail-closed before
binary parsing. Source-table retrieval is bounded (`STR`/`CAS`/`NET`/
`ENDSOURCETABLE`, size/entry caps, SHA-256); coordinates are provider
metadata, never verified station coordinates.

## 7. Admission and identity

Every mountpoint gets an admission record (ACCEPT/WARN/REJECT/BLOCKED +
reason codes) before ingestion. Mountpoint ≠ station: an explicit
registry mapping is required, else `STATION_IDENTITY_UNVERIFIED`,
which fails closed for Phase 8 correction-source use (a labelled
diagnostic capture may still proceed when authorization is clear).
GGA-required streams without configured coordinates fail closed with
`NMEA_POSITION_REQUIRED` — positions are never fabricated.

## 8. Streaming integrity

Incremental RTCM 3.x framer (split-safe, multi-frame reads, O(max
frame) memory), CRC-24Q per frame (`PASS` eligible, `FAIL`
quarantined/counted, never silently forwarded), message-number
extraction recorded only where valid, genuine per-frame arrival timing
(`connection_id`, global sequence, monotonic + UTC stamps, byte
offset, SHA-256) kept separate from any GNSS epoch (no epoch decoding
is claimed in this phase).

## 9. Resilience

Observable states
(DISCONNECTED/CONNECTING/AUTHENTICATING/STREAMING/DEGRADED/RECONNECTING/
STOPPED/BLOCKED); bounded exponential backoff with cap/jitter and
deterministic test timing; terminal failures never reconnect; stall
detection via last-byte/last-frame times; bounded buffers with explicit
BLOCK (default, lossless) or counted DROP diagnostics; reconnects mint
a new `connection_id` while the global capture sequence continues.

## 10. Captures

Immutable layout
`raw/rtcm-captures/<provider>/<station>/<date>/` with `stream.rtcm3`,
`arrival-index.csv`, `source-table.txt`, `capture.json`
(password-free), and `SHA256SUMS.txt`; incremental crash-safe writes;
`COMPLETE`/`PARTIAL`/`FAILED` labelling; sanitized paths with originals
in metadata. Arrival indexes let Phase 9 replay genuine live timing.

## 11. Phase 8/9 integration

`LiveFrame` converts losslessly onto the Phase 9 `CorrectionFrame`;
live subjects (`correction.live.<STATION>`) mirror replay subjects
(`correction.replay.<STATION>`). A live stream for another station is
ingested under its own identity and never substituted for the Phase 8
DOY 026 EKAK00NGA selection. Real-capture → Phase 9 admission/index/
replay is the defined feedback loop (pending an authentic capture).

## 12. Status

Engineering COMPLETE and validated (87 Python + 30 Go synthetic-only
tests; loopback pilot COMPLETE; `make check` green).
`REAL LIVE INGESTION = BLOCKED`: no authorized reachable source exists
— no public endpoint, no configured credentials, endpoint checks are
web pages not casters, home-directory `.rtcm3` files lack provenance.
Phase 6 BEST=ZERO and Phase 7 geometry-only conclusions are unchanged.
See `research/ntrip_ingestion/PILOT_EVIDENCE.md` for the audit record.
