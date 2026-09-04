# Phase 2 Station Metadata Import Specification

## Purpose

This document defines the canonical input contract for importing verified GNSS
station metadata into the NLGCP authoritative PostgreSQL registry.

The importer must never invent missing station, coordinate, equipment, reference
frame, epoch, provenance, or operational-status information.

## Canonical format

Each station import package is a UTF-8 JSON file.

Recommended external-vault location:

    ${NLGCP_DATA_ROOT}/metadata/stations/<provider>_<station>.json

The JSON document has these top-level fields:

    {
      "schema_version": "1.0",
      "sources": [],
      "provider": {},
      "station": {},
      "coordinates": [],
      "equipment": []
    }

`coordinates` and `equipment` may be empty when verified source material does
not provide scientifically adequate information.

## 1. schema_version

Required.

Current value:

    "1.0"

The importer must reject unsupported schema versions.

## 2. sources

Required non-empty array.

Each source object describes an actual provenance document or machine-readable
source used to establish imported metadata.

Fields:

- `key` — required package-local unique identifier.
- `source_type` — required provenance category.
- `path` — required path relative to `NLGCP_DATA_ROOT`.
- `source_reference` — required human-readable citation, publication reference,
  archive reference, URL description, or operator reference.
- `source_date` — nullable ISO date (`YYYY-MM-DD`).
- `expected_sha256` — nullable 64-character SHA256 supplied when independently
  known.
- `notes` — nullable text.

Example structure:

    {
      "key": "primary-site-log",
      "source_type": "site_log",
      "path": "metadata/source-documents/<source-file>",
      "source_reference": "<published/operator reference>",
      "source_date": null,
      "expected_sha256": null,
      "notes": null
    }

### Source rules

The importer must:

1. reject absolute source paths;
2. reject path traversal outside `NLGCP_DATA_ROOT`;
3. require the referenced source file to exist;
4. require the source to be a regular file;
5. compute SHA256 itself;
6. compare the computed SHA256 with `expected_sha256` when supplied;
7. fail closed on checksum disagreement;
8. persist the computed checksum in `metadata_sources`.

The importer must not trust a manually supplied checksum without verifying the
actual file.

## 3. provider

Required object.

Fields:

- `provider_code` — required.
- `provider_name` — required.
- `operator_name` — nullable.
- `country` — nullable.
- `source_key` — required and must reference an entry in `sources`.
- `notes` — nullable.

Provider codes must be stable identifiers. The importer must not silently
rename an existing provider.

## 4. station

Required object.

Fields:

- `station_code` — required.
- `station_name` — nullable.
- `network` — nullable.
- `operator_name` — nullable.
- `country` — nullable.
- `status` — required.
- `first_observation` — nullable ISO-8601 UTC timestamp.
- `last_observation` — nullable ISO-8601 UTC timestamp.
- `source_key` — required and must reference an entry in `sources`.
- `notes` — nullable.

Unknown values remain JSON `null`.

The importer must not infer present operational status merely because historical
observation data exists.

If both observation timestamps are supplied:

    last_observation >= first_observation

must hold.

## 5. coordinates

Array of zero or more effective-dated coordinate records.

Fields:

- `latitude_deg` — nullable.
- `longitude_deg` — nullable.
- `ellipsoidal_height_m` — nullable.
- `ecef_x_m` — nullable.
- `ecef_y_m` — nullable.
- `ecef_z_m` — nullable.
- `reference_frame` — required.
- `coordinate_epoch` — required.
- `solution_method` — nullable.
- `valid_from` — required ISO-8601 UTC timestamp.
- `valid_to` — nullable ISO-8601 UTC timestamp.
- `source_key` — required.
- `notes` — nullable.

### Coordinate rules

A coordinate record must contain either:

1. a complete geodetic pair:
   - latitude;
   - longitude;

or:

2. a complete ECEF triplet:
   - X;
   - Y;
   - Z.

Both representations may be supplied when the source provides both.

Latitude must be between -90 and +90 degrees.

Longitude must be between -180 and +180 degrees.

Partial latitude/longitude pairs are invalid.

Partial ECEF triplets are invalid.

`reference_frame` must not be guessed.

`coordinate_epoch` must not be guessed.

If the available source does not establish frame and epoch adequately, the
station may be imported but the coordinate record must be omitted until better
provenance is available.

If `valid_to` is supplied:

    valid_to > valid_from

must hold.

Coordinate validity intervals for the same station must not overlap.

No implicit reference-frame transformation is permitted during metadata import.

## 6. equipment

Array of zero or more effective-dated station-equipment records.

Fields:

- `receiver_model` — nullable.
- `receiver_serial` — nullable.
- `receiver_firmware` — nullable.
- `antenna_model` — nullable.
- `antenna_serial` — nullable.
- `radome` — nullable.
- `antenna_height_m` — nullable.
- `antenna_height_reference` — nullable.
- `valid_from` — required ISO-8601 UTC timestamp.
- `valid_to` — nullable ISO-8601 UTC timestamp.
- `source_key` — required.
- `notes` — nullable.

At least one meaningful receiver or antenna field must be supplied for an
equipment record.

Antenna height, when supplied, must be non-negative.

The antenna-height reference must not be guessed.

If `valid_to` is supplied:

    valid_to > valid_from

must hold.

Equipment validity intervals for the same station must not overlap.

## Import behaviour

The importer must operate transactionally.

The intended workflow is:

    read JSON package
        ->
    validate package structure
        ->
    resolve provenance files under NLGCP_DATA_ROOT
        ->
    compute and verify SHA256
        ->
    validate provider and station identity
        ->
    validate coordinates
        ->
    validate equipment history
        ->
    begin PostgreSQL transaction
        ->
    register provenance
        ->
    upsert provider/station safely
        ->
    write coordinate/equipment history
        ->
    commit

Any validation, provenance, checksum, identity, or database-integrity failure
must abort the entire import.

Partial imports are not acceptable.

## Idempotency

Re-running an unchanged import package must not create duplicate logical
provider, station, coordinate, equipment, or provenance records.

Conflicting metadata must not silently overwrite existing authoritative data.

A conflict must be reported for operator review.

## Scientific integrity

The following are prohibited:

- invented coordinates;
- invented ellipsoidal heights;
- inferred reference frames;
- invented coordinate epochs;
- invented equipment histories;
- inferred current station availability from historical files;
- silently transformed coordinate frames;
- importing a source document without computing its checksum;
- inserting synthetic example stations into the authoritative registry.

Synthetic records may only be used in disposable test databases and automated
tests.
