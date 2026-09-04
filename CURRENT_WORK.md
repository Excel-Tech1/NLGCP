# Current Work

## Active Phase

Phase 2 - Data Acquisition & Station Registry

## Current Milestone

P2-S3 - Manifest and File Integrity

## Status

Complete

## Completed

- Phase 1 engineering foundation is complete at commit `b2a2097`.
- Phase 2 PostgreSQL/PostGIS station registry foundation exists.
- Provider metadata provenance migration `5d50ff0e583d` is implemented with:
  - `providers.metadata_source_id`;
  - `metadata_sources.source_path`;
  - deterministic source identity uniqueness for importer idempotency.
- Provenance-controlled station metadata importer package implemented under `apps/api/src/nlgcp_api/station_metadata/`.
- Import validation rejects unsupported schemas, unknown source keys, unsafe source paths, partial coordinates, invalid intervals, overlapping histories, and equipment rows without receiver/antenna facts.
- Provenance resolution verifies source files under `NLGCP_DATA_ROOT`, computes SHA256, and fails closed on checksum mismatch.
- Database repository performs transactional imports, idempotent exact re-runs, and conflict detection without overwriting authoritative metadata.
- CLI entrypoint implemented at `scripts/phase2/import_station_metadata.py`.
- Automated tests use synthetic fixture material only and do not insert real stations.
- Report-only RINEX inventory tooling implemented under `apps/api/src/nlgcp_api/rinex_inventory.py`.
- RINEX discovery recursively scans configurable `NLGCP_DATA_ROOT`, identifies observation/navigation candidates, reports vault-relative paths, station markers where determinable, RINEX version, file type, compression, file size, observation date, first/last epoch, approximate sampling interval, SHA256, parser status, warnings, and errors.
- Plain text and gzip RINEX files are parsed; known but unsupported compression such as Unix `.Z` is reported as `not_parsed` without modifying files.
- Deterministic JSON inventory writing implemented for `manifests/rinex-inventory.json`.
- CLI entrypoint implemented at `scripts/phase2/discover_rinex_inventory.py`.
- Deterministic scientific-data manifest tooling implemented under `apps/api/src/nlgcp_api/data_manifest.py`.
- Manifest records vault-relative paths, filenames, file sizes, UTC modified timestamps, SHA256 checksums, artifact types, parser statuses, warnings, and errors.
- Duplicate checksum detection and case-normalized conflicting-path detection are implemented.
- Malformed/error artifact reporting is included without moving or deleting files.
- CLI entrypoint implemented at `scripts/phase2/build_data_manifest.py`; default behavior is report-only and excludes the output manifest itself for rerun idempotency.

## In Progress

- None.

## Not Started

- P2-S4 - GNSS Dataset QC Tooling.
- Real station metadata import.
- Scientific GNSS processing or Phase 3 RTK experiments.

## Blocked

None for P2-S1, P2-S2, or P2-S3.

## Known Issues

- Native Next.js SWC terminates with `Bus error` on this host; the verified production build currently uses the Next.js WASM compiler workaround.
- ESLint 9 is required by the current Next.js lint plugin chain but npm reports that major as unsupported; npm audit previously reported zero known vulnerabilities.
- PRIDE runtime tables may update independently of the pinned application source and therefore must be recorded with experiment provenance.

## Decisions Made

- Raw scientific GNSS data remains outside Git and immutable.
- Unknown station metadata remains null/omitted rather than inferred.
- Re-imports are idempotent only when the package exactly matches existing authoritative records; conflicting records fail closed for operator review.
- Synthetic station metadata remains limited to automated tests and disposable environments.

## Next Action

Start P2-S4 - GNSS Dataset QC Tooling. Build historical RINEX QC reporting with explicit unknown/not-computable states and synthetic fixtures only.

## Last Verified Commit

Current HEAD: `b2a2097`.

## Last Updated

2026-08-24
