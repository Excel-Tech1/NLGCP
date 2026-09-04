# Phase 4 GNSS QC and Station Health

This package implements auditable station-day admission before later NLGCP scientific processing. It does not implement RTK/NRTK estimation, atmospheric interpolation, VRS, RTCM, NTRIP, or accuracy claims.

## Profiles and scientific status

`config/qc-profiles-v1.0.json` defines `archive`, `single_base_rtk`, and `network_rtk`. The completeness and gap settings are **provisional**. They implement conservative, reviewable gates requested by the Phase 4 sprint; they are not claimed as calibrated Nigerian scientific thresholds. No C/N0, satellite-count, residual, or cycle-slip rejection threshold is present.

Profile result precedence is:

```text
REJECT (observed-data failure) > BLOCKED (external evidence unavailable) > WARN > ACCEPT
```

Thus a corrupt or severely truncated observation is not hidden by a simultaneously missing navigation product.

## Reproducible usage

```bash
export NLGCP_DATA_ROOT=/path/to/nlgcp-data

python scripts/run_gnss_qc.py dataset --dry-run
python scripts/run_gnss_qc.py session --station MGBO00NGA --doy 18
python scripts/run_gnss_qc.py station --station UNEC00NGA
python scripts/run_gnss_qc.py date-range --start-doy 20 --end-doy 30
python scripts/run_gnss_qc.py dataset
python scripts/run_gnss_qc.py summarize --profile network_rtk
```

The default dataset command evaluates all three profiles in one RINEX parse pass. `--stream-only` avoids retaining conversions. The normal mode writes derivative `.24D` and `.24O` files under `working/qc-converted/`; immutable `raw/` and `00-deliveries/` are never changed.

Dataset commands default to four independent session workers. Use `--workers 1` for strictly sequential execution or a smaller value on a constrained host. Each worker streams only one session, and each session writes to its own deterministic directory.

Results are profile-separated under:

```text
processed/qc/profiles/<profile>/sessions/<year>/<station>/<DOY>/
```

Each directory contains `qc-result.json`, `gaps.csv`, `satellite-summary.csv`, and `conversion-manifest.json`. Summaries, tables, measured SVG figures, and the validation report are generated from stored JSON. A source/profile/software fingerprint makes reruns resumable; cached results are reused only after the canonical source hash is reverified.

## Explicit limitations

- The historical body parser targets the RINEX 2.x dataset in the canonical 2024 manifest. Unsupported RINEX generations fail explicitly rather than being coerced.
- Coordinate eligibility is limited to an explicitly admitted coordinate epoch unless effective-dated metadata exists; the engine does not invent validity intervals.
- A non-zero RINEX LLI is reported as a potential cycle-slip/continuity indicator, not a confirmed slip.
- External products are inventoried and hashed. Missing acquisition provenance stays null and produces a finding where the profile requires that product.
