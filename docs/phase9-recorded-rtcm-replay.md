# Phase 9 — Recorded RTCM Replay & Deterministic Stream Simulation

## 1. Purpose

Phase 9 builds the offline deterministic correction-stream transport
used to test downstream streaming behaviour without a live CORS
provider:

```text
recorded correction / RTCM source
        ↓ validate source
        ↓ decode framing/timestamps
        ↓ construct replay timeline
        ↓ controlled playback (pause/resume/restart)
        ↓ bounded buffering + integrity checks
        ↓ consumer interface (CorrectionFrame)
        ↓ metrics + evidence
```

After Phase 9, the lab pipeline reads: scientific decision →
selected correction source → deterministic correction stream →
downstream consumer interface. This is still an offline lab pipeline;
the NLGCP MVP is NOT operational.

## 2. Non-goals (explicitly out of scope)

No live NTRIP connection, CORS subscriber, continuous internet
capture, production reconnection loop, live mountpoint management,
correction generation, RTCM encoding, ambiguity resolution, or
accuracy/availability claims. Those belong to Phases 10–11.

## 3. RTCM 3.x framing

Transport frame: `0xD3` preamble; 2 header bytes carrying 6 reserved
bits + 10-bit payload length (0..1023); payload whose first 12 bits
are the RTCM message number; 3-byte CRC-24Q (poly `0x1864CFB`)
computed over preamble + header + payload — the RTKLIB-compatible
convention, documented in `crc.py` so live-caster interop can be
audited when authentic captures exist.

The scanner (`framing.parse_stream`) never invents boundaries:
- unknown bytes are skipped only with explicit `STRAY_BYTES` findings;
- forged/oversize lengths are refused with `OVERSIZED_LENGTH`
  (configurable `max_frame_length`, default 1023);
- short inputs yield `TRUNCATED_HEADER` / `TRUNCATED_FRAME`;
- CRC mismatches yield `CRC_FAIL` and quarantine the frame from the
  replay timeline (still counted in inventory/metrics).

Per-frame records carry `offset, frame_length, message_number,
crc_status, raw_hash`. Payloads are not fully decoded in this phase;
reliable framing and replay are the priority. Observed message types
are inventoried; unobserved types (e.g. any 1005/107x/1230 variant not
seen) are never claimed.

## 4. Timing limitations

A binary RTCM stream carries no universal per-frame wall clock.
Phase 9 reconstructs timing only from declared sources and classifies
the result (`timing.classify_timing`):

| `timestamp_source` + evidence | Quality |
|---|---|
| `capture` + per-frame arrival schedule | `EXACT_CAPTURE_TIMING` |
| `message_epoch` + decoded epochs | `MESSAGE_EPOCH_DERIVED` |
| nominal interval only | `APPROXIMATE` |
| nothing usable | `UNAVAILABLE` |

Epoch decoding is not implemented in this phase, so
`message_epoch` without epoch data classifies `UNAVAILABLE` with an
explicit finding. Time-based slicing fails closed when any event
lacks a timestamp. Synthetic fixtures ship a synthetic arrival
schedule (lab timing, `EXACT_CAPTURE_TIMING` by construction and
labelled synthetic). Offline replay reports source inter-arrival
intervals, scheduled replay delays, and consumer processing delays —
never “network latency”.

## 5. Replay architecture

`timing.build_timeline` produces integer-millisecond relative offsets;
`replay.apply_plan` applies sequence/time slicing, message filtering
(order-preserving), and loop expansion (unique cycle index per
repetition so loops are never confused with captured data).
`ReplayController.run` emits through a `BoundedBuffer` to any
`CorrectionFrame` consumer.

Determinism contract: identical source bytes + config + speed +
range ⇒ identical logical frame sequence (sequence / offset /
message number / hash / provenance). Wall-clock replay timestamps
may differ. Speeds: `>0` paces `relative_time_ms / speed` with
integer arithmetic; `0` means unpaced/max-throughput (deterministic
default; `effective_speed` serialises as null = unpaced).

`clock.py` separates the production `MonotonicClock` from the test
`FakeClock` (time advances only arithmetically — tests never sleep).

## 6. Phase 8 handoff

`handoff.py` parses `CorrectionDecisionPhase9` and binds it to a
compatible replay source without recalculating any science:

- `SINGLE_BASE` → source for the selected reference required, else
  `REPLAY = BLOCKED` with `SELECTED_CORRECTION_SOURCE_UNAVAILABLE`
  (no silent substitution of another station).
- `NO_CORRECTION` → admissible empty run, zero frames emitted.
- `VRS` → approved VRS correction artifact required; none exists
  (operational VRS is BLOCKED), so fail closed.

Current reviewed DOY 026 AUTO (`SINGLE_BASE` via EKAK00NGA,
105.553 km, fallback, VRS blocked for lack of a validated non-zero
spatial model) therefore replays BLOCKED: no EKAK RTCM recording
exists. Every outcome records `transport success ≠ positioning
success`.

## 7. Buffering and backpressure

`buffer.BoundedBuffer` is fixed-capacity with recorded occupancy,
high-water mark, waits, drops, and maximum queue depth. Full-buffer
policy is explicit per run: `BLOCK` (deterministic wait, counted),
`BACKPRESSURE`, or `DROP_NEWEST_EXPLICIT` (counted, reported drops).
There is no silent-discard path: a refused put either waits
(counted) or drops (counted). Metrics expose producer/consumer
frames, waits, drops, and queue depth.

## 8. Checkpointing and cache invalidation

Checkpoints persist source + config fingerprints with
`last_emitted_sequence`, source byte offset, replay timestamp, and
cycle. `validate_checkpoint` rejects resumes when either
fingerprint changed — covering source bytes, metadata, Phase 8
decision, timing config, message filters, and parser version.

## 9. Provenance

Every run records source SHA-256, source metadata, frame inventory
fingerprint, Phase 8 decision fingerprint, selected correction
source, replay config fingerprint, software/schema/parser versions,
Git commit, working-tree state, and execution time
(`provenance.build_provenance`). Output bundles are strict JSON
(non-finite floats sanitised to null).

## 10. Real vs synthetic sources

Source types: `RECORDED_RTCM`, `NTRIP_CAPTURE`,
`SYNTHETIC_TEST_FIXTURE`, `UNKNOWN`. Admission verdicts:
`ACCEPT` / `WARN` / `REJECT` / `BLOCKED`. Non-synthetic sources
require file presence, hash match, capture provenance, known
registry station/mountpoint, and at least one valid frame; `UNKNOWN`
is always REJECTED. Synthetic fixtures must use `SYN`/`TEST`
station ids, are always labelled, and can never validate station
performance.

Real-data status: `REAL RECORDED RTCM PILOT = BLOCKED` — no
authentic capture exists under `${NLGCP_DATA_ROOT}` (see
`research/rtcm_replay/PILOT_EVIDENCE.md` for the audit). Required
next step: an authorised capture stored per
`research/rtcm_replay/config/future-capture-template.md`. No live
ingestion was started in Phase 9.

## 11. Security and resource limits

Recorded binaries are untrusted inputs: oversized lengths refused,
truncation explicit, no path traversal (subjects sanitised),
streaming parse with O(1) per-frame memory, bounded event counts,
configurable `max_frame_length` / `max_source_bytes` / `max_events` /
buffer capacity. Raw captures are immutable; state lives under
`processed/` or `working/`.

## 12. Phase 10 interface

Downstream consumers receive `CorrectionFrame` (sequence, cycle,
source/station/mountpoint, message number, raw bytes, source +
replay timestamps, provenance) — identical for replay and future
live ingestion. Delivery subjects follow the reserved
`correction.*` family as `correction.replay.<STATION>` with
`(source_id, cycle, sequence)` ordering keys (`subjects.py`; no
transport attached in Phase 9, no external infrastructure in
tests). Phase 11 generator testing can drive the same consumer
contract deterministically.

## 13. Outputs, CLI, tests

Outputs: `${NLGCP_DATA_ROOT}/processed/rtcm-replay/{sources,runs,
summaries}/` per `reporting.py`. CLI: `scripts/run_rtcm_replay.py`
with `inspect / validate / index / plan / replay / resume /
summarize`, `--dry-run`, machine-readable JSON, and synthetic-only
fault injection (`--fault-corrupt / --fault-truncate /
--fault-stall`). Tests: 74 synthetic-only tests covering the §45
list (see `research/rtcm_replay/README.md`).

## 14. Claims

Supported (demonstrated): deterministic parsing/replay, ordering
preservation, CRC integrity checks, quarantine of corrupt frames,
pause/resume/checkpoint recovery, bounded buffering with explicit
backpressure, Phase 8 handoff gating, consumer contract stability.

NOT claimed: correction accuracy, centimetre positioning, fixed
ambiguities, VRS improvement, live-service availability,
operational NTRIP, real-pilot success (BLOCKED, reason recorded).
