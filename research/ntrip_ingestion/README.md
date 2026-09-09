# Phase 10 — Live CORS / NTRIP Ingestion

Fail-closed, provenance-preserving live GNSS correction ingestion:
authorized NTRIP caster → admission → handshake → RTCM byte stream →
streaming framer → CRC-24Q → arrival timestamp → `LiveFrame` →
bounded buffer/backpressure → consumer frames + immutable capture +
metrics + provenance.

Phase 10 does NOT generate corrections, serve rovers, or claim
positioning accuracy. Transport success ≠ positioning success.

## Real-data status

`REAL LIVE INGESTION = BLOCKED`: no authorized reachable NTRIP source
exists (no public endpoint documented, no `NLGCP_NTRIP_*` credentials
configured, endpoint checks are web pages — not casters — and carry no
mountpoints). Engineering is implemented and validated with the local
deterministic test server and labelled synthetic fixtures
(`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`).
Acquiring an authorized source remains the documented next requirement.

## Architecture

Production live-stream transport lives in Go
(`services/gnss-ingestor/internal/ntrip/`); the Python research bridge
(`research/ntrip_ingestion/src/nlgcp_ntrip_ingest/`) provides capture
validation, Phase 9 compatibility, and operator reporting. Both share
the same wire conventions (NTRIP v2 first, RTCM 3.x framing, CRC-24Q).

```text
authorized caster
     ↓  admission.py — mountpoint ACCEPT/WARN/REJECT/BLOCKED + station mapping
handshake.py — NTRIP v2 request, v1 ICY tolerance, fail-closed validation
     ↓  framer (streaming, chunk-tolerant) + CRC-24Q (Phase 9 convention)
timing.py — genuine arrival timestamps (never GNSS epochs)
     ↓  LiveFrame → bridge.py → Phase 9 CorrectionFrame (same contract)
buffer (bounded, BLOCK default) + reconnect (bounded, terminal-aware)
     ↓  capture.py — stream.rtcm3 + arrival-index.csv + source-table.txt
                     + capture.json + SHA256SUMS.txt
subjects.py — correction.live.<STATION> (mirrors correction.replay.*)
```

Module map (`research/ntrip_ingestion/src/nlgcp_ntrip_ingest/`):

| Module | Responsibility |
|---|---|
| `models.py` | `NtripConfig` (env), admission/mapping/frame/arrival/metric/capture models |
| `auth.py` | Basic auth, URL/header/text redaction (passwords never logged) |
| `sourcetable.py` | Bounded `STR`/`CAS`/`NET`/`ENDSOURCETABLE` parsing (coordinates = metadata) |
| `handshake.py` | NTRIP v2 request building, v1 tolerance, fail-closed response validation |
| `framing.py` | Incremental RTCM 3.x framer over TCP splits (reuses Phase 9 CRC-24Q) |
| `timing.py` | `SystemClock` / `FakeClock` + per-frame arrival records |
| `backoff.py` | Exponential backoff with cap/jitter; terminal vs transient classification |
| `admission.py` | Mountpoint admission + mountpoint→registry station mapping |
| `client.py` | Lifecycle states, stall detection, reconnect loop, probe/capture |
| `capture.py` | Incremental immutable capture writer (crash-safe, path-safe) |
| `provenance.py` | Redacted provenance envelopes + software commit |
| `subjects.py` | `correction.live.<STATION>` subjects + ordering keys (no transport) |
| `bridge.py` | `LiveFrame` → Phase 9 `CorrectionFrame`; Phase 9 admission reuse |
| `testserver.py` | Deterministic local NTRIP test server (all fault scenarios) |
| `reporting.py` | Offline capture validation + summarisation |

## NTRIP scope

NTRIP v2 spoken first (`Ntrip-Version: Ntrip/2.0`); `ICY 200 OK`
(v1-compatible casters) accepted. Success = `200` with a non-HTML,
non-source-table body. `401`/`403` → terminal auth failure;
`404` → terminal mountpoint-not-found; HTML / source-table-instead /
empty / malformed → refused before any binary parsing.

## Authentication and GGA

Credentials via `NLGCP_NTRIP_USERNAME` / `NLGCP_NTRIP_PASSWORD` only
(plus `HOST`/`PORT`/`MOUNTPOINT`/`TLS`/`USER_AGENT`/`GGA`). Missing
credentials for a protected stream → `AUTH_REQUIRED`/`BLOCKED`. A
stream requiring rover GGA without configured `NLGCP_NTRIP_GGA` →
`NMEA_POSITION_REQUIRED`/`BLOCKED` (no fabricated positions). TLS
certificates validate by default; an explicit insecure mode exists for
diagnostics only, is labelled unsafe, and is never default.

## CLI

```bash
export NLGCP_DATA_ROOT=/home/excellence/nlgcp-data
.venv/bin/python scripts/run_ntrip_ingest.py sourcetable [--dry-run]
.venv/bin/python scripts/run_ntrip_ingest.py probe --duration 5 --max-bytes 65536 [--dry-run]
.venv/bin/python scripts/run_ntrip_ingest.py capture --capture-id ID --output-root DIR [--dry-run]
.venv/bin/python scripts/run_ntrip_ingest.py validate-capture --capture-dir DIR
.venv/bin/python scripts/run_ntrip_ingest.py summarize --capture-dir DIR
```

`probe` is bounded and non-invasive (never indefinite). `--dry-run`
validates configuration without authenticating/streaming and never
claims connectivity.

## Captures

Authentic captures belong under
`${NLGCP_DATA_ROOT}/raw/rtcm-captures/<provider>/<station>/<date>/`
(Phase 10 produced none — no authorized source). Synthetic pilots live
under `${NLGCP_DATA_ROOT}/working/` and are labelled synthetic; raw
captures are immutable once closed (`COMPLETE`/`PARTIAL`/`FAILED`).

## Tests

87 synthetic-only tests (`SYNTHETIC TEST DATA — NOT VALID FOR
SCIENTIFIC RESULTS`): request formation, auth, redaction, source-table
parsing/limits, handshake accept/reject matrix, admission/mapping,
split/multi-frame/CRC/stray framer behaviour, timing, backoff,
terminal classification, live-server probe/capture matrix
(valid/v1/split/auth/404/HTML/source-table-instead/empty/dial-fail),
lossless capacity-1 capture, CRC quarantine, disconnect reconnect,
stall bounds, unverified-identity labelling, password exclusion, path
traversal, dry-run honesty, env convention, subjects, Phase 9 bridge
conversion, Phase 9 admission of the capture format, and capture
validate/summarize round-trips. Go adds 30 tests over the same surface.

## What Phase 10 is not

No correction generation, no MSM encoding, no rover service, no NTRIP
caster for users, no network-RTK/accuracy/ambiguity/VRS claims, and no
change to the Phase 6 BEST=ZERO / Phase 7 geometry-only conclusions.
