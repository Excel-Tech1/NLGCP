# Phase 12 — Local Synthetic NTRIP Correction Service

Localhost-only (`127.0.0.1`) NTRIP v2/v1 lab caster and client connecting the
Phase 11 synthetic RTCM `1005`/`1074`/`1084` generation pipeline to an
authenticated local NTRIP client.

**Scientific and operational boundary:** All mountpoints (`NLGCP_TEST`) emit
`SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.`
This service is a local engineering integration subsystem, not an operational
GNSS correction service.

## Components (`src/nlgcp_correction_service/`)

- `config.py` — fail-closed loopback-only (`127.0.0.1`) caster/client configs
- `auth.py` — constant-time Basic auth (`hmac.compare_digest`) + log redaction
- `mountpoints.py` — synthetic mountpoint registry and NTRIP source table
- `validation.py` — Phase 9 CRC-24Q / framing + non-operational policy gate
- `publisher.py` — bounded FIFO per-client broker + Phase 11 handoff publisher
- `caster.py` — loopback NTRIP v2/v1 caster (`GET`, `POST`, `SOURCE`)
- `client.py` — authenticated local NTRIP client with bounded exponential backoff
- `diagnostics.py` — structured redacted logs + 5-dimension health snapshot
- `pipeline.py` — end-to-end Phase 11 -> Phase 12 -> RTKLIB lab demo helper

## Reproducible local demo

```bash
.venv/bin/python scripts/run_phase12_lab_demo.py
# With native RTKLIB input_rtcm3() decoding enabled:
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python scripts/run_phase12_lab_demo.py
```

Run focused tests:

```bash
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest services/correction-service/tests -q
```
