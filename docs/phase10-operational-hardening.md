# Phase 10 — Operational Hardening

## Scope and status

Phase 10 is the bounded, fail-closed live NTRIP ingestion boundary:

```text
configuration → connection/authentication → RTCM framing/CRC
→ arrival timing → bounded buffer → CorrectionFrame
→ immutable capture and optional publisher adapter
```

Engineering and synthetic loopback validation are complete. Real-provider
validation remains **BLOCKED** because no authorized authenticated caster and
mountpoint has been admitted. Liveness and readiness describe service health;
neither is a claim of RTK availability, correction quality, or positioning
accuracy.

## Operational contracts

- Configuration is validated before dialing. Credentials are environment-only,
  and redaction applies to headers, URLs, logs, exceptions, and provenance.
- Liveness means the process can answer health requests. A disabled service is
  alive. Readiness means configuration and required storage are usable; a
  configured stream may still be `DISCONNECTED`, `STALLED`, or `BLOCKED`.
- Stream states are `DISCONNECTED`, `CONNECTING`, `AUTHENTICATING`,
  `STREAMING`, `DEGRADED`, `RECONNECTING`, `STOPPED`, and `BLOCKED`.
- Authentication failures, invalid mountpoints, and invalid configuration are
  terminal. Connection resets, EOF, timeout, DNS failure, and stalls use a
  bounded reconnect policy.
- Each connection receives a new `connection_id`; the capture-wide frame
  sequence continues across reconnects.
- CRC-failed frames are captured and indexed for audit but never forwarded.
  Default buffering is lossless/blocking. Any drop mode must be explicit and
  counted.

## Capture integrity and recovery

Capture directories contain `stream.rtcm3`, `arrival-index.csv`,
`source-table.txt`, `capture.json`, and `SHA256SUMS.txt`. A frame is written as
a whole unit; rotation decisions occur before a frame is written, so a frame
is never split across capture files. Byte, frame, duration, and minimum-free-
disk policies are bounded. A limit produces `CAPTURE_BLOCKED_DISK_LIMIT` or
`CAPTURE_ROTATION_REQUIRED`; raw evidence is not silently deleted.

If a process stops before finalization, locate directories lacking
`capture.json` and run the recovery helper from the Python package. It writes
only a conservative `PARTIAL`/`PROCESS_INTERRUPTED` manifest and preserves
the raw bytes. Phase 9 must subsequently perform binary admission and CRC
validation.

## Health, metrics, and logging

The Go service exposes `/health` and `/live` (liveness), `/ready` (readiness),
and `/status` (combined machine-readable state). Useful transport metrics are
connection attempts/successes, authentication failures, reconnects, bytes and
frames received, CRC pass/fail, message counts, active connection, stall
events, last-valid-frame age, buffer occupancy/high-water, waits, explicit
drops, and capture opened/finalized/partial/disk-limit events.

Structured events should carry `event`, `provider_id`, `station_id`,
`mountpoint_id`, `connection_id`, `capture_id`, and `reason_code` only where
known. Passwords, authorization headers, credential-bearing URLs, and secret
values are never fields. Transport rates and uptime are operational metrics,
not scientific performance metrics.

## NATS/JetStream boundary

`BoundedPublisher` is the lab adapter boundary. It preserves the live subject
`correction.live.<STATION>` and the Phase 9 ordering/provenance envelope,
counts queue overflow, and does not require NATS in unit tests. A future NATS
implementation must preserve ordering, use bounded publishing, and expose
broker failure without making the raw capture dependent on broker health.

## Compose boundary

Compose includes a health-checked `gnss-ingestor` service with an external
`${NLGCP_DATA_ROOT}/raw/rtcm-captures` bind mount. It contains no credentials;
credentials remain environment-injected at runtime. The service is not an
external caster and does not publish corrections to users.
