# Offline VRS generator

Phase 7 produces traceable geometry-only virtual observations at verified
held-out station coordinates. **NO VALIDATED INTERPOLATION GAIN**.

See [theory, gates, validation and limitations](../../docs/phase7-vrs-generator.md)
and [real pilot evidence](PILOT_EVIDENCE.md). Independent scientific review is
COMPLETE (APPROVED_WITH_PROVISIONAL_LIMITATIONS;
`docs/phase6-7-scientific-validation.md`). Authoritative experiments are
`vrs-2024d026-<target>-geometry-v3`; v1/v2 identifiers are SUPERSEDED.
No RTCM, NTRIP, live delivery or Phase 8 implementation is included.

## Dependencies and commands

Use the repository Python environment (`python3 -m venv .venv`, then
`.venv/bin/python -m pip install -e '.[dev]'`), a C compiler, and the documented
unmodified RTKLIB source commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`.
Missing dependencies return a machine-readable BLOCKED outcome, never fixtures.
Source navigation and observations are only read; temporary decompression and
all derived data remain outside raw directories.

```bash
export NLGCP_DATA_ROOT=/home/excellence/nlgcp-data
export RTKLIB_SOURCE=/home/excellence/RTKLIB
.venv/bin/python scripts/run_vrs_generator.py inspect --definition research/vrs_generator/config/phri.json
.venv/bin/python scripts/run_vrs_generator.py plan --definition research/vrs_generator/config/phri.json
.venv/bin/python scripts/run_vrs_generator.py generate --definition research/vrs_generator/config/phri.json --dry-run
.venv/bin/python scripts/run_vrs_generator.py generate --definition research/vrs_generator/config/phri.json
.venv/bin/python scripts/run_vrs_generator.py validate --definition research/vrs_generator/config/phri.json
.venv/bin/python scripts/run_vrs_generator.py summarize --definition research/vrs_generator/config/phri.json
RTKLIB_SOURCE=/home/excellence/RTKLIB make check
```

`--data-root` and `--rtklib-source` before the operation override environment
variables. All five operations return JSON; BLOCKED returns exit 2. `inspect`
and `plan` resolve coordinates and verify evidence without loading observation
bodies. Every operation supports `--dry-run`; validation dry runs require an
existing complete generation and inspect the held-out input hashes.

Configurations for `phri`, `abfc`, `ekak`, `mgbo` rotate all four known stations;
three references remain in each run. No location is invented. Effective
sampling is 180 seconds, explicitly decimated from the 30-second source data.
Only GPS C1/P1/P2/L1/L2 codes supported by all references are eligible.

## Tests

The Python unit/integration tests use labelled synthetic fixtures and are
registered in the repository's normal pytest suite. Six native geometry checks
compile the adapter and compare with an independently calculated circular
orbit, including radians, GPST, Sagnac, zero displacement, time variation,
missing/stale/unhealthy ephemeris and horizon exclusion. Set `RTKLIB_SOURCE` to
run these; otherwise pytest explicitly reports their external-dependency skip.
No large datasets, compiled adapter or generated virtual observations enter Git.
