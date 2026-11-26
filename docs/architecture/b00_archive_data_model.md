# B-00 Archive Data Model and Provenance Specification

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-00 — Research Archive, Data Provenance and Reproducibility Foundation
**Date:** 2026-11-26

---

## 1. Entity Relationship Model

```text
  +----------------------+       uses / derives       +-----------------------+
  |   DatasetManifest    |<---------------------------|  ExperimentManifest   |
  | (NLGCP-DATA-YYYY-NNN)|--------------------------->| (NLGCP-EXP-YYYY-NNN)  |
  +----------------------+        produces            +-----------------------+
             ^                                           |        |        ^
             | source_datasets                           |        |        | reproduces
             |                                 produces  |        | uses   |
             |                                           v        v        |
  +----------------------+       validates      +-------------+ +---------+ +---------------------+
  |   ArtifactRecord     |<---------------------| Finding     | |Software | |ReproducibilityRecord|
  | (NLGCP-ART-YYYY-NNN) |                      |(NLGCP-FIND) | |Inventory| |(NLGCP-REPRO-YYYY-N) |
  +----------------------+                      +-------------+ +---------+ +---------------------+
                                                   |       ^
                                      evidences    |       | constrains
                                                   v       |
                                     +---------------+   +------------------+
                                     |Publication    |   |LimitationRecord  |
                                     |Claim          |   |(NLGCP-LIM-NNN)   |
                                     |(NLGCP-CLM-NNN)|   +------------------+
                                     +---------------+
```

---

## 2. Stable Identifier Conventions

| Entity | Pattern | Example |
|---|---|---|
| Dataset | `^NLGCP-DATA-\d{4}-\d{3}$` | `NLGCP-DATA-2011-001` |
| Experiment | `^NLGCP-EXP-\d{4}-\d{3}$` | `NLGCP-EXP-2026-014` |
| Artifact | `^NLGCP-ART-\d{4}-\d{3}$` | `NLGCP-ART-2026-001` |
| Software Entry | `^NLGCP-SW-[A-Z0-9-]+$` | `NLGCP-SW-RTKLIB-242P13` |
| Scientific Finding | `^NLGCP-FIND-\d{3}$` | `NLGCP-FIND-001` |
| Limitation | `^NLGCP-LIM-\d{3}$` | `NLGCP-LIM-001` |
| Publication Claim | `^NLGCP-CLM-\d{3}$` | `NLGCP-CLM-001` |
| Reproduction Attempt | `^NLGCP-REPRO-\d{4}-\d{3}$` | `NLGCP-REPRO-2026-001` |

---

## 3. Controlled Vocabularies

### 3.1 Missing-Value Tokens (Mandatory Honesty Policy)
Where an attribute is genuinely absent or unverifiable, manifests use explicit controlled strings rather than guessed values:
`UNKNOWN`, `NOT_RECORDED`, `NOT_VERIFIED`, `NOT_AVAILABLE`, `NOT_APPLICABLE`, `BLOCKED`.

### 3.2 Dataset Source Classifications (`DatasetClassification`)
`AUTHENTIC_LIVE_CORS` | `AUTHENTIC_RECORDED_CORS` | `THIRD_PARTY_CORRECTION_STREAM` | `SYNTHETIC_TEST_DATA` | `SIMULATED_DATA` | `MODELLED_DATA` | `DERIVED_DATA` | `UNKNOWN`

### 3.3 Integrity Verification Statuses (`IntegrityStatus`)
`VERIFIED` | `MISSING` | `HASH_MISMATCH` | `NOT_CHECKED` | `ACCESS_DENIED` | `INVALID_MANIFEST`

### 3.4 Experiment Statuses (`ExperimentStatus`)
`PLANNED` | `IN_PROGRESS` | `COMPLETED` | `FAILED` | `BLOCKED` | `SUPERSEDED` | `REQUIRES_REVALIDATION`

### 3.5 Experiment Relationship Types (`RelationType`)
`USES_DATASET` | `PRODUCES_DATASET` | `DEPENDS_ON` | `VALIDATES` | `SUPERSEDES` | `REPRODUCES`

### 3.6 Validation Levels (`ValidationLevel` — Never Auto-Promoted)
1. `IMPLEMENTED`
2. `UNIT_TESTED`
3. `INTEGRATION_TESTED`
4. `INDEPENDENTLY_VALIDATED`
5. `SCIENTIFICALLY_VALIDATED`
6. `HARDWARE_VALIDATED`
7. `OPERATIONALLY_APPROVED`

### 3.7 Reproducibility & Reproduction Levels
- **Experiment reproducibility status:** `REPRODUCED` | `PARTIALLY_REPRODUCED` | `NOT_REPRODUCED` | `BLOCKED` | `NOT_ATTEMPTED` | `PARTIAL`
- **Reproduction levels (`ReproductionLevel`):**
  - `LEVEL_1_RECORD_COMPLETE` — sufficient documentation & provenance recorded.
  - `LEVEL_2_COMPUTATIONAL` — same inputs & configuration can be re-executed.
  - `LEVEL_3_NUMERICAL` — re-executed outputs agree within documented numerical tolerances.
  - `LEVEL_4_INDEPENDENT` — independent implementation or external tool confirms the scientific result.

### 3.8 Publication Claim Readiness
`SUPPORTED` | `SUPPORTED_WITH_LIMITATIONS` | `INSUFFICIENT_EVIDENCE` | `REFUTED_OR_NEGATIVE` | `BLOCKED`

---

## 4. Core Manifest Schemas

### 4.1 Dataset Manifest (`research/archive/schema/dataset.schema.json`)
Required top-level fields:
- `schema_version`, `dataset_id`, `name`, `dataset_type`, `source_classification`, `source_provider`, `description`, `acquisition_method`, `immutable_source`
- `storage`: `{location, storage_type (REPOSITORY|EXTERNAL_FILESYSTEM|UNAVAILABLE), original_filename, file_size_bytes}`
- `integrity`: `{algorithm ("SHA256"), expected_hash (64 hex or NOT_RECORDED/NOT_AVAILABLE), verification_status}`
- `metadata`: `{format, temporal_coverage {start, end}, station_count, constellations, sampling_interval_s, coordinate_reference_status, reference_frame}`
- `licensing`: `{status, conditions}`
- `registration`: `{retrieval_date, created_at, registered_by}`
- `relationships`: `{related_experiments, derived_from_datasets, derived_datasets}`

### 4.2 Experiment Manifest (`research/archive/schema/experiment.schema.json`)
Required top-level fields:
- `schema_version`, `experiment_id`, `title`, `milestone`, `status`, `data_classification` (`AUTHENTIC` | `SYNTHETIC` | `MIXED_PROHIBITED` | `DOCUMENTATION_AUDIT`), `research_question`, `hypothesis`
- `datasets` (list of `NLGCP-DATA-*` IDs)
- `software`: `{nlgcp_repository, git_branch, nlgcp_revision, git_dirty, software_ids, python_version}`
- `configuration`: `{location, sha256, parameters_summary}`
- `execution`: `{command, environment, started_at, completed_at, random_seed}`
- `outputs` (list of `{location, sha256, artifact_id, description}`)
- `metrics` (structured observed key metrics)
- `results`: `{report, summary, result_classification}`
- `validation`: `{highest_level, unit_test_status, integration_test_status, independent_validation, scientific_validation}`
- `limitations` (list of limitation IDs or explicit text)
- `relationships` (typed edges to other experiments/datasets)
- `reproducibility`: `{status, level, notes}`

### 4.3 Artifact Record (`research/archive/schema/artifact.schema.json`)
Required fields: `schema_version`, `artifact_id`, `experiment_id`, `file_path`, `storage_type`, `file_type`, `file_size_bytes`, `sha256`, `created_at`, `generated_by`, `source_datasets`, `description`, `validation_status`, `contains_nested_hash_manifest` (optional boolean for bundle manifests such as B-02's 311-file `hashes_manifest.json`).

### 4.4 External Data Path Resolution Rules
- `storage_type == "REPOSITORY"`: resolved relative to repository root (`/home/excellence/NLGCP`).
- `storage_type == "EXTERNAL_FILESYSTEM"`: absolute path (or `${NLGCP_DATA_ROOT}`-prefixed path resolved against configured `data_root`, defaulting to `/home/excellence/nlgcp-data`).
- If the external root directory itself does not exist or is unreadable (e.g., sandboxed execution), the verifier returns `ACCESS_DENIED` (never `VERIFIED`) and CLI `verify` returns exit code `3`.
- If the external root is accessible but a registered file is absent, the verifier returns `MISSING` and CLI `verify` returns exit code `1`.
- If SHA-256 disagrees with `expected_hash`, the verifier returns `HASH_MISMATCH` and CLI `verify` returns exit code `1`.
