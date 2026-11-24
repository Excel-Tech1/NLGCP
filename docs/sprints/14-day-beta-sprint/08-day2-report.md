# Day 2 Report

**Sprint:** NLGCP 14-Day Beta Sprint  
**Day:** 2 - Phase 11 RTCM Protocol Implementation and Validation I (1005/1074/1084)  
**Date:** 2026-11-24  
**Branch:** `research/nlgcp-14-day-beta-sprint`  
**HEAD:** `d789da0` (`Recover Southern Nigeria navigation data`)  
**Status:** Complete (synthetic-fixture bit-level encoders verified; independent decoder deferred to Day 3)

## 1. Summary

Day 2 implemented, audited against pinned RTKLIB v2.4.2-p13, and unit-tested
three deterministic bit-level RTCM 3.x encoders in the Phase 11 research
package (`research/rtcm_generation`):

- `REFERENCE_STATION_1005` (RTCM 1005 reference-station ARP);
- `MSM4_GPS_1074` (GPS MSM4);
- `MSM4_GLONASS_1084` (GLONASS MSM4).

All fixtures are labelled `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC
RESULTS`. The encoders serialize caller-supplied fields into deterministic
payloads and delegate framing/CRC-24Q to the shared Phase 9 adapter
(`research/rtcm_replay`). They do not measure, interpolate, admit, or
scientifically validate GNSS observations or station coordinates.

The registry status for `REFERENCE_STATION_1005`, `MSM4_GPS_1074`, and
`MSM4_GLONASS_1084` is `SYNTHETICALLY_VALIDATED`. No family is
`REAL_INPUT_VALIDATED` or `OPERATIONALLY_APPROVED`. Semantic RTCM validation
remains `NOT_PERFORMED_NO_INDEPENDENT_DECODER`.

## 2. Starting State and Continuation Audit

| Item | Observed value |
|---|---|
| Repository | `/home/excellence/NLGCP` |
| Branch | `research/nlgcp-14-day-beta-sprint` |
| HEAD at start and end | `d789da0` |
| Pre-existing uncommitted work | Day 1 sprint documents, status/evidence updates, Phase 9 `encode_payload_frame` helper, initial Day 2 RTCM 1005/1074/1084 encoder implementation and initial tests |
| External changes | None; no downloads, network probes, raw-data changes, or reference-frame changes |
| Git commit | None created |

### 2.1 What was already completed before continuation

Before this takeover, the prior agent had completed:

- Phase 9 `encode_payload_frame` in `research/rtcm_replay/src/nlgcp_rtcm_replay/framing.py` and `frame_message_payload` in `research/rtcm_generation/src/nlgcp_rtcm_generation/framing.py`;
- Initial `ReferenceStation1005`, `Msm4Cell`, and `Msm4Message` models and bit-packing encoders in `research/rtcm_generation/src/nlgcp_rtcm_generation/messages.py`;
- Encoder classes (`ReferenceStation1005Encoder`, `GpsMsm4Encoder`, `GlonassMsm4Encoder`, `default_encoders()`) in `encoder.py`, updated family statuses in `registry.py`, strengthened synthetic/coordinate-state admission rules in `admission.py`, `MessageInputError` mapping in `generator.py`, and `NOT_PERFORMED_NO_INDEPENDENT_DECODER` semantic-validation reporting in `validation.py`;
- Initial 72 unit tests in `research/rtcm_generation/tests/test_rtcm_messages.py` and updated `test_scaffold.py` (14 tests);
- Initial Day 2 draft documentation updates.

### 2.2 What was audited, fixed, and added during continuation

A line-by-line audit of `messages.py` against the pinned RTKLIB v2.4.2-p13
source (`/home/excellence/RTKLIB`, commit
`71db0ffa0d9735697c6adfd06fdf766d0e5ce807`) uncovered and resolved the
following defects and coverage gaps:

1. **Critical protocol defect fixed — off-by-one MSM signal-ID tables:**
   In RTKLIB `src/rtcm3.c` lines 64–75, `msm_sig_gps[32]` and `msm_sig_glo[32]`
   are 0-indexed C arrays accessed via 1-based RTCM Signal IDs (`msm_sig[id - 1]`
   in `decode_msm_head`/`save_msm_obs`, returning `i + 1` in `to_sigid`).
   Index `0` (RTCM Signal ID `1`) is `""` (reserved) in **both** GPS and
   GLONASS. The initial Day 2 code had shifted GPS signals `1C..1M` and
   `2C..2M` and GLONASS signals `1C, 1P` down by one, causing:
   - reserved Signal ID `1` to be accepted as `"1C"` for both GPS and GLONASS;
   - valid GPS Signal ID `6` (`"1M"`) and `12` (`"2M"`) to be rejected;
   - reserved GPS Signal ID `7` to be accepted as `"2C"`;
   - valid GLONASS Signal ID `3` (`"1P"`) to be rejected;
   - both synthetic 1074 and 1084 test vectors to encode reserved Signal ID `1`.
   Both tables were programmatically verified directly against
   `/home/excellence/RTKLIB/src/rtcm3.c` and fixed to exact 1-based RTCM/RTKLIB
   signal IDs (`GPS_MSM_SIGNAL_IDS`: 19 entries starting at `2: "1C"`;
   `GLONASS_MSM_SIGNAL_IDS`: 7 entries starting at `2: "1C"`).
2. **Direct-construction validation hardened (`messages.py`):**
   - `ReferenceStation1005.validate()` now enforces strict integer/boolean/finite
     type checks (rejecting `bool` passed to integer/float fields) on direct
     construction, matching `from_mapping()`.
   - `Msm4Cell.validate()` and `Msm4Message.validate()` now enforce system-aware
     `satellite_id` bounds (`1..32` GPS, `1..24` GLONASS), defined signal-ID
     table membership, strict GPS TOW (`[0, 604799999]`) and GLONASS
     `(dow << 27) | tod_ms` (`dow in [0, 6]`, `tod_ms in [0, 86399999]`) epoch
     bounds, and `bool`-as-`int` rejection on direct model construction.
3. **Independent synthetic vectors regenerated and test coverage expanded (+31 tests):**
   - Updated the 1074 fixture to valid GPS signals `2` (`1C`) and `9` (`2P`) and
     the 1084 fixture to valid GLONASS signals `2` (`1C`) and `8` (`2C`).
   - Recomputed independent hardcoded payload/frame hex vectors with a
     standalone bit-string packer and independent CRC-24Q routine (not importing
     `nlgcp_rtcm_generation` or `nlgcp_rtcm_replay`).
   - Added 31 targeted tests in `test_rtcm_messages.py` (103 tests total in
     `test_rtcm_messages.py`, 117 in `research/rtcm_generation`): physical
     round-trip decoding within quantization resolution, all 16 `_to_msm_lock`
     threshold bins (`0..15`), positive/negative/zero fine pseudorange and fine
     phase boundaries, exact 64-cell mask acceptance vs 65+ rejection, high
     PRN/slot and high signal-ID mask bit placement, observation-order
     invariance, payload byte-length formula and trailing zero-padding bits,
     direct-construction invalid epoch/sat/signal/`bool` rejection, CRC-24Q
     standard check vector (`b"123456789" -> 0xCDE703`), single-bit mutation
     rejection across header/payload/CRC for all three families, and
     `encode_payload_frame` short/oversize length rejection.
4. **Report and git-status reconciliation:**
   - Updated this report (including previously omitted modified documentation
     files in Section 8) and aligned `CURRENT_WORK.md`, `EVIDENCE_INDEX.md`,
     `02-phase-readiness-matrix.md`, and `06-fourteen-day-tracker.md` with the
     final verified `make check` run.

## 3. Technical Design Decisions

### 3.1 RTCM 1005 (Stationary RTK Reference Station ARP)

- **Payload length:** 152 bits (19 bytes exact; 25 bytes framed with 3-byte
  `0xD3`/length header and 3-byte CRC-24Q).
- **Field layout (verified against `rtcm3e.c` `encode_type1005` and `rtcm3.c`
  `decode_type1005`):**
  12-bit message number (`1005`), 12-bit station ID (`0..4095`), 6-bit ITRF
  realization year (`0..63`), 4x 1-bit flags (GPS, GLONASS, Galileo,
  reference-station indicator), 38-bit signed ECEF-X (`0.0001 m`), 1-bit
  oscillator indicator, 1-bit reserved (`0`), 38-bit signed ECEF-Y (`0.0001 m`),
  2-bit quarter-cycle indicator (`0..3`), 38-bit signed ECEF-Z (`0.0001 m`).
- **Quantization:** Half-up rounding (`floor(x / 0.0001 + 0.5)`, matching
  RTKLIB's `ROUND` macro) over the signed 38-bit two's-complement domain
  `[-(1<<37), (1<<37)-1]`. Note: RTKLIB v2.4.2-p13's `set38bits` uses `floor`
  without `+0.5`, which can introduce a 0.1 mm downward IEEE-754 truncation
  bias on decimal inputs like `111111.1111`; half-up rounding avoids that bias
  and decodes cleanly through RTKLIB's `getbits_38` in `decode_type1005`.
- **Fail-closed input handling:** Missing, unknown, non-finite, boolean-as-int,
  and out-of-range fields raise `MessageInputError`.

### 3.2 RTCM 1074 (GPS MSM4) and RTCM 1084 (GLONASS MSM4)

- **Header:** 169 fixed bits (`12` msg no, `12` station ID, `30` epoch, `1`
  multiple-message sync, `3` IOD, `7` reserved `0`, `2` clock steering, `2`
  external clock, `1` smoothing, `3` smoothing interval, `64` satellite mask
  MSB = sat 1, `32` signal mask MSB = sig 1), followed by `Nsat * Nsig`
  sat-major/sig-minor cell mask bits (`<= 64`).
- **Epoch packing:**
  - GPS 1074: 30-bit unsigned GPS TOW in ms (`0..604,799,999`).
  - GLONASS 1084: `(epoch_dow << 27) | epoch_tod_ms` with `epoch_dow in 0..6`
    and `epoch_tod_ms in 0..86,399,999`.
- **Satellite data (field-major across sorted satellites):**
  `Nsat * 8` bits unsigned rough range integer ms (`0..254`; `255` rejected),
  followed by `Nsat * 10` bits unsigned rough range modulo 1 ms (`2^-10 ms`).
  Rough range is deterministically taken from the lowest `signal_id` cell for
  each satellite so encoding is invariant to caller observation order.
- **Signal data (field-major across sorted active cells):**
  `Ncell * 15` bits signed fine pseudorange (`2^-24 * RANGE_MS`, `±292.7 m`,
  sentinel `-16384` rejected), `Ncell * 22` bits signed fine phase-range
  (`2^-29 * RANGE_MS`, `±1171.0 m`, sentinel `-2097152` rejected), `Ncell * 4`
  bits unsigned lock-time indicator (`_to_msm_lock` matching `rtcm3e.c`),
  `Ncell * 1` bit half-cycle ambiguity indicator, `Ncell * 6` bits unsigned CNR
  (`1 dB-Hz`, `0..63`), zero-padded to an octet boundary.
- **GLONASS FCN boundary:** MSM4 (1084) does not carry the 4-bit extended
  satellite info (`DF419` / GLONASS FCN). `frequency_channel` is rejected as an
  unexpected field rather than silently ignored or fabricated.
- **Admission & framing boundary:**
  - `admission.py` requires `synthetic_fixture=True`,
    `classification=SYNTHETIC_TEST_ONLY`, and
    `coordinate.verification_state=SYNTHETIC_TEST_ONLY` for all non-operational
    families; `OPERATIONAL_APPROVED` remains forbidden; `VRS` remains blocked.
  - Framing and CRC-24Q reuse Phase 9 (`encode_payload_frame` / `crc24q`,
    polynomial `0x1864CFB`, init `0`, no final XOR) with no duplicate CRC.

## 4. Authoritative Protocol References and Unverifiable Details

### 4.1 References used (no licensed RTCM text reproduced)

- Pinned RTKLIB v2.4.2-p13 (`/home/excellence/RTKLIB`, commit
  `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`):
  - `src/rtcm3e.c`: `ROUND`, `set38bits`, `to_msm_lock`, `encode_type1005`,
    `to_satid`, `to_sigid`, `gen_msm_index`, `gen_msm_sat`, `gen_msm_sig`,
    `encode_msm_head`, `encode_msm_int_rrng`, `encode_msm_mod_rrng`,
    `encode_msm_psrng`, `encode_msm_phrng`, `encode_msm_lock`,
    `encode_msm_half_amb`, `encode_msm_cnr`, `encode_msm4`;
  - `src/rtcm3.c`: `msm_sig_gps`, `msm_sig_glo`, `getbits_38`,
    `decode_type1005`, `save_msm_obs`, `decode_msm_head`, `decode_msm4`;
  - `src/rtklib.h`: `CLIGHT`, `P2_24`, `P2_29`, `MAXPRNGPS` (32),
    `MAXPRNGLO` (24);
  - `src/rtkcmn.c`: `rtk_crc24q`.
- NLGCP technical baseline:
  `docs/technical-baseline/v1.0/docs/16-rtcm-and-ntrip-correction-distribution.md`.

### 4.2 Protocol details not establishable from RTKLIB v2.4.2-p13 alone

The following details require the licensed RTCM 10403.x specification and/or
independent decoder/receiver validation and were NOT guessed:

- **RTCM 1005 flag/enumeration semantics:** RTKLIB `encode_type1005` hard-codes
  `itrf=0`, `gps=1`, `glo=1`, `gal=0`, `ref=0`, `osc=1`, `qci=0`, and
  `decode_type1005` skips the constellation, oscillator, and quarter-cycle bits.
  Bit widths/positions are verified; semantic table rules for `DF021` (ITRF
  year) and `DF364` (quarter-cycle indicator) require RTCM 10403.x.
- **RTCM 1005 minimum negative 38-bit sentinel:** RTKLIB `getbits_38` decodes
  all two's-complement 38-bit values without a reserved minimum; whether RTCM
  DF025/026/027 forbids `-2^37` requires RTCM 10403.x (real Earth ECEF is far
  inside `±6.4e6 m`).
- **MSM4 header indicator semantics:** `clock_steering`, `external_clock`,
  `smoothing`, `smoothing_interval`, and `reserved` widths/positions are
  verified in `encode_msm_head`/`decode_msm_head`, but RTKLIB's encoder writes
  zeros; detailed enumeration meanings require RTCM 10403.x.
- **GLONASS 1084 special epoch values:** Special RTCM `DF416` encodings (e.g.,
  `dow=7` unknown day-of-week or leap-second `tod_ms` in `86,400,000..86,400,999`)
  are not implemented in RTKLIB `decode_msm_head`; the encoder fails closed
  outside `dow in [0, 6]` and `tod_ms in [0, 86,399,999]`.
- **MSM4 missing-observation sentinels & `DF397=0`:** Our encoder rejects
  missing/sentinel fine values (`-16384`, `-2097152`) and `DF397=255` rather
  than encoding partial-observable cells; note also that RTKLIB `decode_msm4`
  treats `DF397=0` (`r[j]==0.0`) as missing (real MEO GNSS pseudoranges are
  ~63–87 ms).
- **Post-RTKLIB v2.4.2-p13 MSM signal IDs:** Any RTCM 3.3+ GPS/GLONASS signal
  IDs added after RTKLIB v2.4.2-p13 are not included or guessed.
- **Independent decoder & receiver conformance:** Deferred to Day 3.

## 5. Independent Synthetic Test Vectors

All payloads below are deterministic synthetic vectors, not real station data.
Expected hex strings were generated by a standalone bit-string packer and
independent CRC-24Q routine (not importing `nlgcp_rtcm_generation` or
`nlgcp_rtcm_replay`), then hardcoded into `test_rtcm_messages.py`.

### 5.1 RTCM 1005

Fixture: station `1234`; ECEF `(111111.1111, -222222.2222, 3333333.3333)` m;
GPS+GLONASS indicators; oscillator on; ITRF 0.

```text
payload: 3ed4d20300423a35c7bf7b8b947207c2d24d55   (19 bytes, 152 bits)
frame:   d300133ed4d20300423a35c7bf7b8b947207c2d24d555f8fb0   (25 bytes)
```

### 5.2 RTCM 1074 (GPS MSM4)

Fixture: station `1234`, GPS TOW `345600123` ms, IOD `2`, satellites `(1, 2, 3)`,
valid GPS signals `2` (`1C`) and `9` (`2P`), three sparse cells (`0b101001`).

```text
payload: 4324d25265c1ec800070000000000000002040000052848c936d064c4fb4fcfc051c00c7a4f966f03ebd467956d0f0   (47 bytes, 373 bits + 3 zero pad bits)
frame:   d3002f4324d25265c1ec800070000000000000002040000052848c936d064c4fb4fcfc051c00c7a4f966f03ebd467956d0f0c0396f   (53 bytes)
```

### 5.3 RTCM 1084 (GLONASS MSM4)

Fixture: station `3210`, GLONASS day `3` and time-of-day `45296789` ms, IOD `5`,
satellites `(1, 2)`, valid GLONASS signals `2` (`1C`) and `8` (`2C`), four cells
(`0b1111`).

```text
payload: 43cc8a6accb257403660000000000000002080000079fa25b0c37333e827c65f973fefc69fcd17fe9579fba5a99bb9658d5480   (51 bytes, 401 bits + 7 zero pad bits)
frame:   d3003343cc8a6accb257403660000000000000002080000079fa25b0c37333e827c65f973fefc69fcd17fe9579fba5a99bb9658d5480787e97   (57 bytes)
```

## 6. Tests Executed and Results

### 6.1 Focused Phase 11 + Phase 9 gate

```text
.venv/bin/python -m pytest research/rtcm_generation research/rtcm_replay -q
191 passed in 1.76s  (103 in test_rtcm_messages.py, 14 in test_scaffold.py, 74 in research/rtcm_replay)

.venv/bin/python -m ruff check research/rtcm_generation research/rtcm_replay
All checks passed!

.venv/bin/python -m mypy research/rtcm_generation research/rtcm_replay
Success: no issues found in 40 source files
```

### 6.2 Full repository quality gate (`make check && git diff --check`)

- Ruff: `All checks passed!`
- Go `gofmt -d . && go vet ./...`: passed
- ESLint (`--max-warnings=0`): passed
- mypy: `Success: no issues found in 222 source files`
- TypeScript (`tsc --noEmit`): passed
- pytest: **`759 passed, 6 skipped in 32.63s`** (the 6 skips are the pre-existing
  native VRS geometry tests requiring `RTKLIB_SOURCE`; no new tests skipped)
- Go tests (`go test ./...`): passed (`internal/health`, `internal/ntrip`)
- CMake / CTest: `1/1 Test #1: nrtk-health-test Passed`
- Next.js production build: passed
- `git diff --check`: passed (no whitespace errors)

## 7. Known Limitations, Remaining Blockers, and Readiness Assessment

### 7.1 Known limitations

- Validation proves internal framing/CRC-24Q consistency and bit-field agreement
  against independently packed test vectors only.
- No independent RTCM decoder (e.g., native RTKLIB `input_rtcm3` or another
  reference decoder) has decoded these generated frames yet (deferred to Day 3).
- No commercial/field GNSS receiver interoperability testing has occurred.
- RTCM 1084 (MSM4) does not transport GLONASS frequency-channel numbers (FCN).
- Partial-observable cells (sentinel missing fine PR/phase) are not encoded.

### 7.2 Remaining blockers

- Independent RTCM decoder validation (Day 3).
- Authentic admitted GNSS observations and verified station coordinates.
- GLONASS FCN transport (e.g., RTCM 1020 or MSM5/MSM7) and authentic GLONASS
  validation.
- Promoted atmospheric/spatial correction model (Phase 6 BEST = ZERO) and
  operational VRS approval (Phase 7 `VRS_GEOMETRY_ONLY`).
- Authorized live CORS/NTRIP source, Phase 12 caster, rover hardware, and field
  validation evidence.

### 7.3 Scientific and operational readiness assessment

- **Engineering readiness (Day 2 scope):** COMPLETE for deterministic synthetic
  bit-level encoding of RTCM 1005, 1074, and 1084 through the Phase 9 framing
  and CRC-24Q path with fail-closed admission gates.
- **Scientific readiness:** NOT READY / BLOCKED. `SYNTHETICALLY_VALIDATED` is a
  unit-test status only, not scientific validation. Phase 6/7/8 conclusions are
  unchanged; no positioning accuracy, RTK FIX, or VRS improvement is claimed.
- **Operational readiness:** NOT APPROVED. `OPERATIONAL_APPROVED` remains
  forbidden; synthetic payloads are not navigable RTCM correction messages.

## 8. Observed Git Status

```text
## research/nlgcp-14-day-beta-sprint
 M CURRENT_WORK.md
 M EVIDENCE_INDEX.md
 M PROJECT_STATUS.md
 M docs/phase11-correction-generation-scaffold.md
 M research/rtcm_generation/README.md
 M research/rtcm_generation/src/nlgcp_rtcm_generation/__init__.py
 M research/rtcm_generation/src/nlgcp_rtcm_generation/admission.py
 M research/rtcm_generation/src/nlgcp_rtcm_generation/encoder.py
 M research/rtcm_generation/src/nlgcp_rtcm_generation/framing.py
 M research/rtcm_generation/src/nlgcp_rtcm_generation/generator.py
 M research/rtcm_generation/src/nlgcp_rtcm_generation/registry.py
 M research/rtcm_generation/src/nlgcp_rtcm_generation/validation.py
 M research/rtcm_generation/tests/test_scaffold.py
 M research/rtcm_replay/src/nlgcp_rtcm_replay/framing.py
?? docs/sprints/
?? research/rtcm_generation/src/nlgcp_rtcm_generation/messages.py
?? research/rtcm_generation/tests/test_rtcm_messages.py
```

No commit, merge, rebase, reset, stash, or push was performed.

## 9. Stop Point

Day 2 stops here. Day 3 (independent RTCM conformance review) must not start
without explicit authorization. The synthetic-only, fail-closed boundary
remains in force.
