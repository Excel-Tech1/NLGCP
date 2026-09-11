# Phase 11 — Correction-Generation Interface and Encoder Research Scaffold

## Status and non-goals

The Phase 11 scaffold is **READY architecturally** and **not operationally
approved**. It defines interfaces, registries, provenance, validation and a
synthetic reference vector. It does not generate authentic NLGCP corrections,
serve a caster, claim centimetre accuracy, claim ambiguity fixing, or change
the Phase 6/7/8 scientific conclusions.

The Python reference package is `research/rtcm_generation`:

```text
admitted Phase 8 request/context
        ↓
scientific admission gate
        ↓
domain/message encoder boundary
        ↓
Phase 9 RTCM framing + CRC-24Q
        ↓
GeneratedCorrectionFrame / Phase 12 artifact
```

## Contracts

`CorrectionGenerationRequest` carries request and decision fingerprints,
mode, reference/virtual station identity, coordinate provenance, distinct
GNSS/arrival/generation/transmission time fields, source/model fingerprints,
encoder version, message family and output classification.
`CorrectionGenerationContext` carries domain fields and observations without
embedding binary layout in scientific code. `CorrectionGenerationResult`
contains status, fail-closed reason codes, frames and provenance. Frames carry
message number, lengths, CRC, SHA-256, request fingerprint, encoder version,
input status and classification.

Recognized modes are `SINGLE_BASE`, `VRS`, and `NO_CORRECTION`:

- `NO_CORRECTION` produces no frames.
- `VRS` is blocked under the current `VRS_GEOMETRY_ONLY` / no promoted-model
  state (`VRS_OPERATIONAL_NOT_APPROVED`, `CORRECTION_MODEL_NOT_APPROVED`).
- `SINGLE_BASE` remains blocked without an admitted authentic input source.

The gate also requires an admissible decision, admitted source, verified
station identity, verified coordinate provenance, a GNSS epoch, an approved
model, supported encoder, and complete provenance. `OPERATIONAL_APPROVED` is
forbidden in this sprint.

## Message registry and encoder boundary

The registry records `REFERENCE_STATION_1005`, GPS MSM4 `1074`, GLONASS MSM4
`1084`, and one lab-only `SYNTHETIC_TEST_FRAME` family. Registry presence is
not support: the real families are `SCAFFOLDED`, while only the synthetic
family is `SYNTHETICALLY_VALIDATED`. No proprietary RTCM standard text is
copied. The scaffold does not invent reference-station or MSM bit layouts.

`FieldSpec`, `BitWriter`, and `BitReader` enforce units, scales, bounds,
signedness, finite values, overflow rejection, and deterministic padding. The
synthetic encoder emits a clearly labelled test payload under message number
4095; it is not a navigable RTCM message. Framing delegates to the tested
Phase 9 `0xD3`/10-bit-length/CRC-24Q implementation, avoiding a second CRC.

Phase 9 parsing validates framing, message number and CRC only. It does not
constitute semantic RTCM or scientific validation. RTKLIB remains an optional
future compatibility cross-check and is not modified here.

## Provenance, classification, and handoff

Generation provenance links the decision, source, model, registry and encoder
fingerprints. Every frame is classified `SYNTHETIC_TEST_ONLY`,
`DIAGNOSTIC_ONLY`, `RESEARCH_VALIDATION`, or `OPERATIONAL_APPROVED`; the last
classification is guarded and cannot be emitted by this sprint.

`CorrectionStreamArtifact` is the versioned Phase 12 handoff schema. It
contains stream/decision identity, mode/station fields, message families,
generation status, frame source, validity interval, classification and a
provenance fingerprint. It is a contract only: Phase 12 transport, accounts,
mountpoints, and public/private caster service are not started.

## Synthetic end-to-end lab path

The test path is:

```text
synthetic admitted fixture → Phase 11 request → synthetic frame
→ Phase 9 parser/CRC check → bounded local consumer envelope
```

Fixtures are labelled **SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC
RESULTS**, deterministic, and never sent to an external network. The real
state test deliberately blocks VRS and single-base requests when their model
or authentic input is unavailable.

## CORS-unblock procedure

When authorized access arrives, record the provider, endpoint authorization,
mountpoint, station mapping and credential reference without committing
secrets. Then run a bounded Phase 10 dry-run, source-table retrieval and
probe; capture authentic bytes with immutable metadata; admit/index/replay the
capture through Phase 9; derive a Phase 8 decision; and only then run Phase 11
real-input encoder validation. Cross-check with an independent/reference
decoder and controlled positioning tests. Operational approval requires
reviewed scientific evidence; successful transport, CRC, or frame rates are
not sufficient.
