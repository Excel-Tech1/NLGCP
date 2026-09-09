# Phase 9 — Recorded RTCM Replay

Offline deterministic correction-stream replay (transport/replay phase).

Phase 9 simulates how later live correction data will move through
NLGCP: recorded correction / RTCM source → source validation → framing
→ replay timeline → controlled playback (pause/resume/restart) →
bounded buffering → integrity checks → consumer interface → metrics +
evidence. Downstream streaming behaviour can therefore be tested
without depending on a live CORS provider.

Phase 9 does NOT recalculate Phase 8 scientific decisions, generate
corrections, claim positioning accuracy, run NTRIP, or ingest live
streams. A replayed transport stream is not proof of correction
accuracy (`transport success ≠ positioning success`).

## Real-data status

`REAL RECORDED RTCM PILOT = BLOCKED`: no authentic recorded RTCM
exists under `${NLGCP_DATA_ROOT}` (manifests carry zero RTCM/NTRIP
references; `miranet_endpoint_check.txt` / `nignet_endpoint_check.txt`
are connectivity checks, not replayable captures). The replay
framework is implemented and validated with clearly labelled synthetic
byte fixtures (`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC
RESULTS`); acquiring an authorised RTCM capture is the next
requirement. The home-directory `cors-*.rtcm3` files sit outside the
data root with no capture provenance and are NOT admitted as authentic
sources.

## Architecture

```text
recorded source definition (models.RTCMSource)
     ↓  admission.py — fail-closed ACCEPT/WARN/REJECT/BLOCKED
framing.py — RTCM 3 preamble 0xD3 / 10-bit length / CRC-24Q
     ↓  inventory.py — observed message types only
timing.py — EXACT / EPOCH-DERIVED / APPROXIMATE / UNAVAILABLE
     ↓  deterministic ReplayEvent timeline
replay.py — paced playback, pause/resume/stop, range/filter/loop
     ↓  buffer.py — bounded buffer + explicit backpressure
CorrectionFrame consumer contract (§15; Phase 10 interface)
     ↓  checkpoint.py / metrics.py / provenance.py / reporting.py
${NLGCP_DATA_ROOT}/processed/rtcm-replay/ bundles + summaries
```

Module map (`research/rtcm_replay/src/nlgcp_rtcm_replay/`):

| Module | Responsibility |
|---|---|
| `models.py` | Source/frame/config/checkpoint/metrics models, enums, fail-closed parsers |
| `crc.py` | CRC-24Q (poly 0x1864CFB) over preamble+header+payload |
| `framing.py` | Stream scanner, `encode_frame` fixture builder, message-number extraction |
| `fixtures.py` | Deterministic labelled synthetic fixtures (valid/corrupt/truncated) |
| `inventory.py` | Observed message-type inventory + fingerprint |
| `timing.py` | Timing classification + deterministic timeline |
| `clock.py` | `MonotonicClock` (production) / `FakeClock` (tests, no sleeping) |
| `replay.py` | `ReplayController`: speeds, pause/resume/stop, range, filter, loop, faults |
| `buffer.py` | `BoundedBuffer` with BLOCK/BACKPRESSURE/DROP_NEWEST_EXPLICIT |
| `checkpoint.py` | Fingerprint-gated restart checkpoints |
| `admission.py` | Fail-closed source admission + SHA-256 verification |
| `handoff.py` | Phase 8 `CorrectionDecisionPhase9` binding (no recalculation) |
| `provenance.py` | Source/inventory/Phase 8/config fingerprints + run provenance |
| `metrics.py` | Discovery + execution metric assembly (no fake latencies) |
| `subjects.py` | `correction.replay.<STATION>` subjects + ordering keys (no transport) |
| `reporting.py` | Output bundles + summary CSVs (strict-JSON sanitised) |

## RTCM framing

Transport frame: `0xD3` preamble, 2-byte header (6 reserved bits +
10-bit payload length 0..1023), payload (first 12 bits = message
number), 3-byte CRC-24Q computed over preamble + header + payload
(RTKLIB-compatible convention; live-caster interop must be
re-validated when authentic captures are acquired). Every anomaly —
stray bytes, oversize length, truncated header/frame, CRC failure —
becomes an explicit finding; message boundaries are never invented.

## Timing

Binary RTCM carries no universal per-frame wall clock. Replay timing
is reconstructed only from declared sources and classified honestly.
Synthetic fixtures ship a synthetic arrival schedule
(`EXACT_CAPTURE_TIMING`, lab timing only). Time-based slicing fails
closed when timestamps are unavailable.

## Speeds, buffering, checkpointing

- Speeds: `--speed 1` realtime, `--speed 10` accelerated, `--speed 0`
  unpaced/max-throughput (deterministic default; `effective_speed`
  serialises as null meaning unpaced).
- Buffer: bounded (`--buffer-capacity`); full-buffer behaviour is
  `BLOCK` (deterministic wait, counted), `BACKPRESSURE`, or explicit
  `DROP_NEWEST_EXPLICIT` (counted drops). Silent loss is impossible by
  construction: every drop is counted and reported.
- Checkpoints persist `(source, config)` fingerprints with the resume
  position; any change invalidates the checkpoint.

## Phase 8 handoff

`--phase8-handoff <phase9-handoff.json>` binds the recorded Phase 8
decision to a compatible replay source without recalculation:
`SINGLE_BASE` requires the selected reference (no silent
substitution → `SELECTED_CORRECTION_SOURCE_UNAVAILABLE`);
`NO_CORRECTION` emits nothing; `VRS` requires an approved artifact
(none exists — operational VRS is BLOCKED).

## CLI

```bash
export NLGCP_DATA_ROOT=/home/excellence/nlgcp-data
.venv/bin/python scripts/run_rtcm_replay.py inspect --source <source.json>
.venv/bin/python scripts/run_rtcm_replay.py validate --source <source.json>
.venv/bin/python scripts/run_rtcm_replay.py index --source <source.json>
.venv/bin/python scripts/run_rtcm_replay.py plan --source <source.json> --schedule <arrival.json> [--replay-id ID]
.venv/bin/python scripts/run_rtcm_replay.py replay --source <source.json> --schedule <arrival.json> [--config cfg.json] [--phase8-handoff h.json] [--replay-id ID]
.venv/bin/python scripts/run_rtcm_replay.py resume --replay-id ID --schedule <arrival.json>
.venv/bin/python scripts/run_rtcm_replay.py summarize
```

All ops accept `--dry-run` and emit machine-readable JSON.
Test faults: `--fault-corrupt SEQ`, `--fault-truncate SEQ`,
`--fault-stall N` (synthetic fixtures only).

## Outputs

Under `${NLGCP_DATA_ROOT}/processed/rtcm-replay/` (outside Git):

```text
sources/<source-id>/{source,inventory,frames,message-types,validation}.json/csv
runs/<replay-id>/{definition,admission,timeline,metrics,checkpoint,
                   provenance,validation,phase8-handoff}.json/csv
summaries/{sources,replay-runs}.csv
```

Fixtures live under `${NLGCP_DATA_ROOT}/working/rtcm-replay-fixtures/`;
`raw/` is never touched.

## Tests

74 synthetic-only tests (`SYNTHETIC TEST DATA — NOT VALID FOR
SCIENTIFIC RESULTS`): framing, CRC pass/fail, preamble/length/
truncation findings, message-number extraction, inventory, hashing,
admission ACCEPT/WARN/REJECT/BLOCKED, synthetic labelling, timing
classification, deterministic ordering, speeds, fake clock, pause/
resume/stop, checkpoint round-trip + invalidation, range replay,
filtering, loop cycles, bounded buffering, backpressure accounting, no
silent drops, consumer stall, malformed metadata, Phase 8 handoff
paths, provenance/fingerprinting, subjects.

## What Phase 9 is not

No live NTRIP, no CORS subscriber, no continuous capture, no
production reconnection loop, no correction generation, no accuracy /
ambiguity / availability claims. The `CorrectionFrame` contract plus
`correction.replay.*` subjects are the Phase 10-ready interface.
