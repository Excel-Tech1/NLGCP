# B-00 Research Archive Completeness & Verification Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-00 — Research Archive, Data Provenance and Reproducibility Foundation
**Archive Version:** `b00-research-archive-v1.0`
**Generated From Live Run:** `2026-11-26T11:54:23Z` (strictly read-only verification via `.venv/bin/nlgcp archive verify --verify-nested --out-dir /home/excellence/nlgcp-data/processed/research-archive/b00`)
**Machine-Readable Report:** `/home/excellence/nlgcp-data/processed/research-archive/b00/archive_verification_report.json`
**Overall Verdict:** **`VERIFIED_WITH_RECORDED_PROVENANCE_GAPS` (exit `0`)**

---

## Executive Integrity Summary

- **Datasets:** `21` registered — **`18` SHA-256 verified** (including `5.82 GiB` immutable `NIGNET2011.zip`), `0` missing, `0` hash mismatches, `0` inaccessible, **`3` explicitly `UNAVAILABLE`** (`NLGCP-DATA-2011-006` 2011 precise products, `NLGCP-DATA-2024-011` 2024 DCB/IONEX, `NLGCP-DATA-2026-004` authorized live Nigerian CORS stream).
- **Experiments:** `17` registered — `16` `COMPLETED`, `1` `SUPERSEDED` (`NLGCP-EXP-2026-005` pre-review Phase 6), **`2` complete provenance** (`NLGCP-EXP-2026-016` B-02 PHRI 2024, `NLGCP-EXP-2026-017` B-02 OSGF 2011), **`15` honestly recorded historical provenance gaps**, `0` schema/reference errors, `0` authentic/synthetic contaminations.
- **Artifacts:** `24` top-level artifacts registered — **`24/24` SHA-256 verified** (`0` missing, `0` mismatches) + **`311/311` nested B-02 outputs verified** via `NLGCP-ART-2026-024` (`hashes_manifest.json`).
- **Software Provenance:** `8` registered — **`5/5` hashed scientific tools SHA-256 verified** (`RTKLIB rnx2rtkp`, `RTKLIB convbin`, `PRIDE PPP-AR pdp3`, `ESA gLAB 6.0.0`, `gLAB input.c`), plus `3` host language toolchains (`Python 3.12.3`, `Go 1.25.6`, `Node v20.20.2`).
- **Evidence Registers:** `18` findings (including all mandatory negative/inconclusive findings), `12` limitations, `14` publication claims, `14` Day 7 security findings (`SEC-01`..`SEC-14`), `6` reproduction records.
- **Fail-Closed Sandbox Verification:** When external `/home/excellence/nlgcp-data` is absent (CI / sandboxed test), `nlgcp archive verify` returns **`exit 3` (`EXTERNAL_STORAGE_INACCESSIBLE`)** while still verifying all repository-local manifests and reports (`0` schema errors).

---

## Section A — Dataset Completeness & Integrity

| Dataset ID | Classification | Storage | Size (B) | SHA-256 Status | Coordinate / Frame Status |
|---|---|---|---:|---|---|
| `NLGCP-DATA-2011-001` | `AUTHENTIC_RECORDED_CORS` | `EXTERNAL` | `5,820,369,120` | **`VERIFIED`** (`8ccb0045…`) | `PROVISIONAL_OSGOF_2011_01_01` |
| `NLGCP-DATA-2011-002` | `AUTHENTIC_RECORDED_CORS` | `EXTERNAL` | `56,968` | **`VERIFIED`** (`52cc6c9b…`) | `WGS84_BROADCAST` |
| `NLGCP-DATA-2011-003` | `DERIVED_DATA` | `EXTERNAL` | `4,305` | **`VERIFIED`** (`e48cd164…`) | `PROVISIONAL_OSGOF_2011_01_01` |
| `NLGCP-DATA-2011-004` | `DERIVED_DATA` | `EXTERNAL` | `6,478,287` | **`VERIFIED`** (`c9f43c87…`) | `PROVISIONAL_OSGOF_2011_01_01` |
| `NLGCP-DATA-2011-005` | `DERIVED_DATA` | `EXTERNAL` | `6,418,001` | **`VERIFIED`** (`95f3bad2…`) | `PROVISIONAL_OSGOF_2011_01_01` |
| `NLGCP-DATA-2011-006` | `AUTHENTIC_RECORDED_CORS` | `UNAVAILABLE` | `NOT_AVAILABLE` | `NOT_CHECKED` (`UNAVAILABLE`) | `NOT_AVAILABLE` (`B-01` 2011 SP3/CLK) |
| `NLGCP-DATA-2024-001` | `AUTHENTIC_RECORDED_CORS` | `EXTERNAL` | `537,609` | **`VERIFIED`** (`4f97149b…`) | `PARTIALLY_VERIFIED_DOY_026_ONLY` |
| `NLGCP-DATA-2024-002` | `AUTHENTIC_RECORDED_CORS` | `EXTERNAL` | `1,306,845` | **`VERIFIED`** (`a6418387…`) | `WGS84_BROADCAST` |
| `NLGCP-DATA-2024-003` | `DERIVED_DATA` | `EXTERNAL` | `3,665` | **`VERIFIED`** (`f48411df…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-004` | `DERIVED_DATA` | `EXTERNAL` | `4,796,500` | **`VERIFIED`** (`a2bae005…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-005` | `DERIVED_DATA` | `EXTERNAL` | `10,946,890` | **`VERIFIED`** (`57e1917a…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-006` | `DERIVED_DATA` | `EXTERNAL` | `12,743,833` | **`VERIFIED`** (`953df3cd…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-007` | `DERIVED_DATA` | `EXTERNAL` | `11,821,585` | **`VERIFIED`** (`be679f14…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-008` | `DERIVED_DATA` | `EXTERNAL` | `5,257` | **`VERIFIED`** (`7f62d246…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-009` | `AUTHENTIC_RECORDED_CORS` | `EXTERNAL` | `1,932,216` | **`VERIFIED`** (`33c5ce3e…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-010` | `DERIVED_DATA` | `EXTERNAL` | `217,498` | **`VERIFIED`** (`2d10325a…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2024-011` | `AUTHENTIC_RECORDED_CORS` | `UNAVAILABLE` | `NOT_AVAILABLE` | `NOT_CHECKED` (`UNAVAILABLE`) | `NOT_AVAILABLE` (2024 DCB/IONEX) |
| `NLGCP-DATA-2026-001` | `DERIVED_DATA` | `EXTERNAL` | `3,914` | **`VERIFIED`** (`d9eb20c3…`) | `VERIFIED_IGS20_PPP_AR` |
| `NLGCP-DATA-2026-002` | `DERIVED_DATA` | `EXTERNAL` | `4,045` | **`VERIFIED`** (`e4f49265…`) | `PROVISIONAL_OSGOF_2011_01_01` |
| `NLGCP-DATA-2026-003` | `SYNTHETIC_TEST_DATA` | `EXTERNAL` | `115` | **`VERIFIED`** (`0402b7e8…`) | `SYNTHETIC_TEST_ONLY` |
| `NLGCP-DATA-2026-004` | `AUTHENTIC_LIVE_CORS` | `UNAVAILABLE` | `NOT_AVAILABLE` | `NOT_CHECKED` (`UNAVAILABLE`) | `NOT_AVAILABLE` (Live CORS `GN-01`) |

---

## Section B — Experiment Provenance Completeness

| Experiment ID | Status | Schema Valid | Provenance Complete | Recorded Historical Gaps / Warnings |
|---|---|---|---|---|
| `NLGCP-EXP-2026-001` | `COMPLETED` | `True` | `False` | `configuration.{location,sha256}`, `execution.{command,environment}` = `NOT_RECORDED` |
| `NLGCP-EXP-2026-002` | `COMPLETED` | `True` | `False` | `git_dirty=null`, `configuration.*`, `execution.*` = `NOT_RECORDED` (numerically reproduced in B-02) |
| `NLGCP-EXP-2026-003` | `COMPLETED` | `True` | `False` | `configuration.*`, `execution.environment` = `NOT_RECORDED` |
| `NLGCP-EXP-2026-004` | `COMPLETED` | `True` | `False` | `execution.environment` = `NOT_RECORDED` (config SHA `fd3d999e…` & CLI recorded) |
| `NLGCP-EXP-2026-005` | `SUPERSEDED` | `True` | `False` | Superseded by `NLGCP-EXP-2026-006`; `git_dirty=null`, `execution.*` = `NOT_RECORDED` |
| `NLGCP-EXP-2026-006` | `COMPLETED` | `True` | `False` | `execution.{command,environment}` = `NOT_RECORDED` (config SHA `f9828fec…` verified) |
| `NLGCP-EXP-2026-007` | `COMPLETED` | `True` | `False` | `configuration.*` = `NOT_RECORDED`; warning: ran on dirty Git tree prior to `5b5217a` |
| `NLGCP-EXP-2026-008` | `COMPLETED` | `True` | `False` | `configuration.*`, `execution.*` = `NOT_RECORDED` |
| `NLGCP-EXP-2026-009` | `COMPLETED` | `True` | `False` | `configuration.*` = `NOT_RECORDED`; warning: ran on dirty Git tree prior to `5b5217a` |
| `NLGCP-EXP-2026-010` | `COMPLETED` | `True` | `False` | `configuration.*`, `execution.*` = `NOT_RECORDED` |
| `NLGCP-EXP-2026-011` | `COMPLETED` | `True` | `False` | `configuration.*`, `execution.*` = `NOT_RECORDED` (`SYNTHETIC` only) |
| `NLGCP-EXP-2026-012` | `COMPLETED` | `True` | `False` | `configuration.*`, `execution.*` = `NOT_RECORDED` (`SYNTHETIC` only) |
| `NLGCP-EXP-2026-013` | `COMPLETED` | `True` | `False` | `configuration.*`, `execution.environment` = `NOT_RECORDED` (`SYNTHETIC` only) |
| `NLGCP-EXP-2026-014` | `COMPLETED` | `True` | `False` | `configuration.*` = `NOT_RECORDED` (`SYNTHETIC` only) |
| `NLGCP-EXP-2026-015` | `COMPLETED` | `True` | `False` | `configuration.*` = `NOT_APPLICABLE` (documentation & security audit) |
| **`NLGCP-EXP-2026-016`** | `COMPLETED` | `True` | **`True`** | **None — full B-02 PHRI 2024 provenance complete (`config 44d22f17…` + `311` outputs)** |
| **`NLGCP-EXP-2026-017`** | `COMPLETED` | `True` | **`True`** | **None — full B-02 OSGF 2011 provenance complete (`config 44d22f17…` + `311` outputs)** |

---

## Section C — Artifact & Nested Manifest Integrity

- **Top-Level Artifacts (`24/24` `VERIFIED`):** `NLGCP-ART-2026-001` through `NLGCP-ART-2026-024` (`20` external filesystem outputs + `4` repository Markdown reports) all verified byte-exact against SHA-256 (`0` missing, `0` mismatches).
- **Nested B-02 Hash Manifest (`NLGCP-ART-2026-024`):** `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/hashes_manifest.json` (`2a2a921f…`) checked all **`311 / 311`** derived RTCM, RINEX, RTKLIB `.conf`/`.pos`, and JSON files — **`311` verified, `0` missing, `0` mismatches**.

---

## Section D — Software & Environment Provenance

| Software ID | Name | Version | Path | SHA-256 Status |
|---|---|---|---|---|
| `NLGCP-SW-RTKLIB-RNX2RTKP` | RTKLIB `rnx2rtkp` | `v2.4.2-p13` (`71db0ffa…`) | `/home/excellence/.local/bin/rnx2rtkp` | **`VERIFIED`** (`b4a96cd0…`) |
| `NLGCP-SW-RTKLIB-CONVBIN` | RTKLIB `convbin` | `v2.4.2-p13` (`71db0ffa…`) | `/home/excellence/.local/bin/convbin` | **`VERIFIED`** (`b575f81e…`) |
| `NLGCP-SW-PRIDE-PDP3` | PRIDE PPP-AR `pdp3` | `3.2.8` (`4907bfe5…`) | `/home/excellence/.PRIDE_PPPAR_BIN/pdp3` | **`VERIFIED`** (`9e526f55…`) |
| `NLGCP-SW-GLAB-600` | ESA/gAGE-UPC gLAB | `6.0.0` | `/opt/gLAB/gLAB_linux` | **`VERIFIED`** (`ca530155…`) |
| `NLGCP-SW-GLAB-INPUTC` | ESA/gAGE-UPC gLAB `input.c` | `6.0.0` | `/opt/gLAB/source/core/input.c` | **`VERIFIED`** (`16fd82ea…`) |
| `NLGCP-SW-PYTHON-312` | Python (`.venv`) | `3.12.3` | `/home/excellence/NLGCP/.venv/bin/python` | `NOT_CHECKED` (`expected_sha256=NOT_RECORDED`) |
| `NLGCP-SW-GO-125` | Go Toolchain | `go1.25.6 linux/amd64` | `NOT_RECORDED` | `NOT_CHECKED` |
| `NLGCP-SW-NODE-2020` | Node.js / npm | `v20.20.2 / npm 10.8.2` | `NOT_RECORDED` | `NOT_CHECKED` |

- **Environment Snapshot:** [`research/archive/provenance/environment_snapshot_2026-11-26.json`](file:///home/excellence/NLGCP/research/archive/provenance/environment_snapshot_2026-11-26.json) captured cleanly with `data_root.accessible = true`, lockfile SHA-256 digests (`pyproject.toml`, `apps/web/package*.json`, `go.mod`, `CMakeLists.txt`, `compose.yml`), and zero secrets (`LANG`, `VIRTUAL_ENV` only).

---

## Section E — Evidence, Security, Limitation & Publication Claim Coverage

- **Findings (`18`):** `NLGCP-FIND-001`–`018`, including **all 11 mandatory negative/inconclusive findings** (0.0% genuine FIX, 7 false `Q=1` fixes, geometry-only VRS degradation, 2024 kinematic H CI crossing zero, provisional 2011 coordinates, perimeter extrapolation `ZERO`-dominance, `experimental_vrs.py:517` ZWD defect & fix, missing non-RTKLIB MSM4 decoder, 132 CDDIS auth failures, missing 2011/2024 precise/DCB/IONEX products, and Day 7 security blockers).
- **Limitations (`12`):** `NLGCP-LIM-001`–`012` mapped to `B-01`–`B-10`, `GN-01`, `GN-05`.
- **Day 7 Security Findings (`14`):** `SEC-01`–`SEC-14` (`13` `OPEN`, `1` `VERIFIED_LAB_CONTROL`) preserved verbatim in [`security_findings_register.json`](file:///home/excellence/NLGCP/research/archive/validation/security_findings_register.json).
- **Publication Claims (`14`):** `2` `SUPPORTED`, `5` `SUPPORTED_WITH_LIMITATIONS`, `2` `REFUTED_OR_NEGATIVE`, `2` `INSUFFICIENT_EVIDENCE`, `3` `BLOCKED` (zero unsupported claims marked supported).
- **Reproducibility Records (`6`):** `2` `LEVEL_3_NUMERICAL` (`REPRODUCED`), `1` `LEVEL_2_COMPUTATIONAL` (`REPRODUCED`), `1` `LEVEL_4_INDEPENDENT` (`PARTIALLY_REPRODUCED`), `1` `LEVEL_1_RECORD_COMPLETE` (`PARTIALLY_REPRODUCED`), `1` `LEVEL_0_NONE` (`BLOCKED`).

---

## Section F — Explicit Unresolved Gaps & Maintenance Policy

1. **Historical provenance gaps (`15` earlier experiments):** Shell invocations, static config files, or environment snapshots from earlier feature-branch pilots (`NLGCP-EXP-2026-001`–`015`) were honestly recorded as `NOT_RECORDED`/`NOT_APPLICABLE` rather than invented retroactively.
2. **External data dependencies (`3` `UNAVAILABLE` datasets):** 2011 precise `SP3`/`CLK`/`ERP`/`OSB` (`B-01`), 2024 external DCB/IONEX, and authorized live Nigerian CORS streams (`GN-01`) remain absent and unfabricated.
3. **Ongoing Maintenance Rule:** Every future milestone (starting with `B-04` and beyond) MUST register its datasets, experiment manifest (with config SHA-256 + command + environment snapshot), artifacts, findings, and limitations under `research/archive/` and pass `.venv/bin/nlgcp archive verify` prior to handover.
