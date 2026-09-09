# Phase 9 Pilot Evidence (synthetic framework pilot + real-source audit)

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS (fixtures only).
No positioning, accuracy, or operational-availability claim is made.

## Real recorded RTCM audit (2026-09-09)

- Searched `${NLGCP_DATA_ROOT}` (`/home/excellence/nlgcp-data`):
  `manifests/files.csv` and `manifests/canonical-raw-archive-2024.json`
  contain **zero** `rtcm` references; no `*.rtcm*` / `*ntrip*` /
  `*caster*` files exist under the data root; `raw/` holds RINEX
  station directories only.
- `manifests/miranet_endpoint_check.txt` and
  `manifests/nignet_endpoint_check.txt` are HTTP connectivity checks,
  NOT replayable correction captures (not misclassified).
- Home-directory `cors-sample.rtcm3` / `cors-test.rtcm3` sit outside
  the data root with no URL/mountpoint/start-end/SHA/arrival-timestamp/
  source-identity capture record → NOT admissible as authentic sources.

**Conclusion: `REAL RECORDED RTCM PILOT = BLOCKED`.**
Next requirement: an authorised RTCM capture stored per
`research/rtcm_replay/config/future-capture-template.md`.

## Synthetic fixtures (deterministic, valid CRC-24Q framing)

Under `${NLGCP_DATA_ROOT}/working/rtcm-replay-fixtures/`:

| Fixture | SHA-256 (prefix) | Content |
|---|---|---|
| `valid.rtcm3` (`syn-valid-001`) | `0402b7e8…` | 8 frames: 1005×2, 1077×2, 1087×2, 1006, 1230; schedule 0..7000 ms |
| `corrupt.rtcm3` (`syn-corrupt-002`) | `b5a63210…` | same + 1 flipped payload bit (frame 3 CRC FAIL) |
| `truncated.rtcm3` (`syn-trunc-003`) | `47e5d6f8b…` | valid prefix cut mid-frame (7 frames + TRUNCATED_FRAME finding) |

Station `SYN00TST`, mountpoint `SYNTHETIC`, labelled test-only.

## Scenario results (CLI, deterministic, FakeClock — no sleeping)

| Scenario | Run | Outcome |
|---|---|---|
| A valid replay | `run-a-valid` | ACCEPT; 8/8 emitted, 0 dropped, 0 duplicates, 0 gaps; EXACT_CAPTURE_TIMING |
| B corruption | `run-b-corrupt` | WARN (`CRC_FAIL offset=43`, quarantined); 7 emitted, 0 dropped/gaps |
| C restart | `run-c-partial` | fault-truncate after seq 4 → 5 emitted; `resume` → 3 more, checkpoint `last_emitted_sequence=7`, 0 duplicates |
| D backpressure | `run-d-backpressure` / `run-d-drop-explicit` | capacity-1 buffer, max depth 1, 8/8 delivered, 0 drops, 0 waits lost silently (full-buffer BLOCK/DROP counting covered by unit tests) |
| E Phase 8 incompatible | real AUTO handoff (EKAK00NGA) | REPLAY BLOCKED `SELECTED_CORRECTION_SOURCE_UNAVAILABLE` (exit 3), no substitution |
| E Phase 8 no-correction | real VRS_ONLY handoff | `NO_CORRECTION_NO_STREAM`, 0 frames (exit 0) |
| E synthetic single-base | `SYN00TST` handoff | admitted (runs A–D) |
| Truncation finding | `syn-trunc-003` validate | WARN `TRUNCATED_FRAME offset=101`, 7/7 valid frames admissible |

Message inventory (observed, `syn-valid-001`): 1005×2, 1006×1,
1077×2, 1087×2, 1230×1. No other message types claimed.

## Outputs

`${NLGCP_DATA_ROOT}/processed/rtcm-replay/`:
`sources/{syn-valid-001,syn-corrupt-002,syn-trunc-003}/`,
`runs/{run-a-valid,run-b-corrupt,run-c-partial,run-d-backpressure,run-d-drop-explicit,run-e-real-nocorr}/`,
`summaries/{sources,replay-runs}.csv`.

Real Phase 8 decision fingerprints consumed (not recalculated):
AUTO `737e0f0a…` (SINGLE_BASE EKAK00NGA 105.553 km, fallback) and
VRS_ONLY `4d990325…` (NO_CORRECTION/BLOCKED).

## Tests

74 synthetic-only Phase 9 tests pass; `make check` green (see evidence index).
`transport success ≠ positioning success` recorded on every run.
