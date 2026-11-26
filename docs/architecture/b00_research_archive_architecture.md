# B-00 Research Archive Architecture

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-00 — Research Archive, Data Provenance and Reproducibility Foundation
**Date:** 2026-11-26
**Authoritative Baseline Alignment:** `docs/technical-baseline/v1.0/docs/23-research-experiment-and-reproducibility-plan.md`, `ADR-009-immutable-raw-archive.md`, `ADR-011-fail-closed-integrity.md`

---

## 1. Architectural Principles

1. **Zero-disruption overlay:** Existing NLGCP packages (`research/*`), reports (`docs/research/*`, `docs/sprints/14-day-beta-sprint/*`), and external datasets (`/home/excellence/nlgcp-data`) stay at their current paths. The archive references them by canonical path and SHA-256 rather than moving or duplicating files.
2. **Single machine-readable source of truth:** Canonical registries live as deterministic, sorted-key JSON files under `research/archive/`, validated by JSON Schema definitions under `research/archive/schema/` and strict Python dataclasses in `research/research_archive/`. Human-readable Markdown catalogues and verification reports are generated from or cross-checked directly against these manifests.
3. **Fail-closed integrity & honesty (`ADR-011`):** Verification is strictly read-only. Missing files, inaccessible external paths, hash mismatches, incomplete provenance, and negative findings are surfaced explicitly — expected hashes are never rewritten automatically, and inaccessible external data is never reported as verified.
4. **Immutable raw data separation (`ADR-009`):** Original GNSS archives (`incoming/`, `00-deliveries/`, `raw/`, `external-products/`) are registered with `immutable_source = true` and strictly segregated from derived datasets (`DERIVED_DATA`) and synthetic fixtures (`SYNTHETIC_TEST_DATA`).
5. **External filesystem referencing:** Multi-gigabyte GNSS observations and benchmark outputs remain under `${NLGCP_DATA_ROOT}` (`/home/excellence/nlgcp-data`), never copied into Git. The verifier resolves external paths dynamically, reporting `ACCESS_DENIED` or `MISSING` (and CLI exit code `3`) when external storage is unavailable (e.g., sandboxed CI).

---

## 2. Repository Integration Layout

Adapted cleanly to NLGCP's existing `research/<pkg>/src/nlgcp_<pkg>/` and `scripts/run_*.py` conventions:

```text
NLGCP/
├── docs/
│   ├── architecture/
│   │   ├── b00_research_archive_architecture.md   # This architecture specification
│   │   └── b00_archive_data_model.md              # Entity schema & lineage model
│   ├── project/
│   │   ├── PROJECT_CHARTER.md
│   │   ├── RESEARCH_OBJECTIVES.md
│   │   ├── SYSTEM_ARCHITECTURE.md
│   │   ├── TECHNICAL_DECISION_REGISTER.md
│   │   └── PROJECT_STATUS.md
│   ├── research/
│   │   ├── DATASET_CATALOGUE.md                   # Central dataset catalogue
│   │   ├── EXPERIMENT_CATALOGUE.md                # Central experiment catalogue
│   │   ├── VALIDATION_REGISTER.md                 # Central findings & validation levels
│   │   ├── LIMITATIONS_REGISTER.md                # Explicit scientific & negative findings
│   │   ├── PUBLICATION_EVIDENCE_MAP.md            # Claim -> Finding -> Exp -> Dataset chains
│   │   └── (all existing Phase 6/7 & B-02 reports preserved untouched)
│   ├── operations/
│   │   ├── DEPLOYMENT_STATUS.md
│   │   ├── SECURITY_STATUS.md
│   │   └── FIELD_VALIDATION_STATUS.md
│   └── sprints/b00-research-archive/
│       ├── 00-initial-audit.md
│       ├── 10-b00-archive-completeness-report.md
│       └── final-b00-handover.md
│
├── research/
│   ├── archive/                                   # Machine-readable canonical archive store
│   │   ├── schema/                                # JSON Schemas (v2020-12)
│   │   ├── datasets/                              # NLGCP-DATA-*.json manifests
│   │   ├── experiments/                           # NLGCP-EXP-*.json manifests
│   │   ├── artifacts/                             # NLGCP-ART-*.json manifests
│   │   ├── provenance/                            # software_inventory.json, environment snapshot
│   │   ├── validation/                            # findings, limitations, claims, security registers
│   │   └── reproducibility/                       # Level 1-4 reproduction attempt records
│   └── research_archive/                          # Python package (strict mypy + ruff)
│       ├── src/nlgcp_research_archive/
│       │   ├── __init__.py
│       │   ├── models.py                          # Controlled enums & typed manifest contracts
│       │   ├── validator.py                       # Schema, reference & provenance validation
│       │   ├── hash_verifier.py                   # Read-only SHA-256 verifier & safe scanner
│       │   ├── provenance.py                      # Redacted env capture & lineage graph
│       │   ├── registry.py                        # Archive loader, verifier & report generator
│       │   └── cli.py                             # `nlgcp archive ...` CLI interface
│       └── tests/
│           └── test_research_archive.py           # Dataset, experiment, artifact, CLI & safety tests
│
└── scripts/
    └── run_research_archive.py                    # Standalone CLI entry point
```

---

## 3. Component Responsibilities

| Component | Responsibility | Safety Invariant |
|---|---|---|
| `models.py` | Defines controlled enums (`DatasetClassification`, `IntegrityStatus`, `ExperimentStatus`, `ValidationLevel`, `ReproducibilityStatus`, `ReproductionLevel`) and immutable dataclasses. | Rejects unknown status tokens and mixed authentic/synthetic claims. |
| `validator.py` | Validates required fields, ID formats, duplicate IDs, SHA-256 hex format, cross-references (`experiment -> dataset`, `artifact -> experiment`, `finding -> experiment/dataset`, `claim -> finding`), and authentic vs. synthetic separation. | Never equates syntactic validity with scientific reproducibility. |
| `hash_verifier.py` | Resolves repo-relative and external `${NLGCP_DATA_ROOT}` paths, computes streaming SHA-256, compares against manifest `expected_hash`, and supports explicit unregistered-output scanning with temp/build exclusion rules. | Strictly read-only; never rewrites expected hashes, never deletes/moves files, never auto-registers temp files. |
| `provenance.py` | Captures OS/kernel/arch/toolchain/lockfile/Git metadata and verifies external scientific binaries (`rnx2rtkp`, `convbin`, `pdp3`, `gLAB_linux`); constructs full provenance lineage chains (`Claim -> Finding -> Experiment -> Config/Software -> Dataset`). | Redacts/excludes all secret-bearing env vars (`*PASSWORD*`, `*SECRET*`, `*TOKEN*`, `*KEY*`, `*CREDENTIAL*`, `*AUTH*`). |
| `registry.py` | Loads the full `research/archive/` tree, executes end-to-end verification, and renders both machine-readable JSON and human-readable Markdown summaries. | Read-only by default; writes report files only when explicit `--out-dir` is supplied. |
| `cli.py` | Exposes `nlgcp archive {status,datasets,experiments,artifacts,provenance,verify,report}` (also callable via `scripts/run_research_archive.py` and `python -m nlgcp_research_archive`). | Deterministic exit codes: `0` pass, `1` integrity/validation failure, `2` bad args/config, `3` external storage inaccessible / tool unavailable. |

---

## 4. Versioning & Change Control Strategy

- Every manifest carries `schema_version` (e.g., `nlgcp.archive.dataset.v1`).
- Historical manifests are append-only/superseded rather than overwritten: when a new experiment improves or corrects an earlier run, the older manifest transitions to `SUPERSEDED` and links via `relationships` (`SUPERSEDES` / `SUPERSEDED_BY`) while keeping its original metrics, hashes, and limitations intact.
- Repeated runs of an experiment are recorded as distinct `ReproducibilityRecord` entries under `research/archive/reproducibility/` referencing the original `experiment_id`, never overwriting prior outputs.
