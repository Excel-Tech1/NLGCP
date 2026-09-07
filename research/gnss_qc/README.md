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

## 2024 validation results (external evidence, not committed)

Full canonical 2024 run (`NLGCP_DATA_ROOT=/home/excellence/nlgcp-data`): 1290 sessions, 8 stations, 3870 profile results, 0 unexpected processing failures.

```text
archive:          ACCEPT 694, WARN 596, REJECT 0,   BLOCKED 0
single_base_rtk:  ACCEPT 4,   WARN 0,   REJECT 341, BLOCKED 945
network_rtk:      ACCEPT 4,   WARN 0,   REJECT 341, BLOCKED 945
```

Navigation coverage: 7 navigation-covered sessions; 1283 navigation-blocked RTK sessions (BLOCKED = missing required external evidence, not software failure; REJECT = observed-data QC failure, not missing navigation). RTK-profile findings: 371 partial/severely truncated sessions, 263 major-gap sessions, 1 excluded exact duplicate, 4 explicit aliases resolved. Only DOY 026 provides a four-station ACCEPT-only network overlap (ABFC00NGA, EKAK00NGA, MGBO00NGA, PHRI00NGA). The catalogued DOY 026 BKG/IGS broadcast-navigation product records acquisition provenance and SHA-256; the generated validation report derives its provenance wording from that inventory.

Evidence lives outside Git: `processed/qc/` and `validation/reports/phase4-gnss-qc-validation-report.md` under `${NLGCP_DATA_ROOT}`.

## Phase 5 admission gates

Phase 5 may consume only ACCEPT data automatically. WARN requires review; REJECT and BLOCKED are excluded. Profile thresholds remain PROVISIONAL pending calibration against reviewed Nigerian field evidence.
