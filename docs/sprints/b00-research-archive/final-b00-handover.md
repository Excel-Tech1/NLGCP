# Final Engineering Handover — Milestone B-00 (Research Archive, Data Provenance & Reproducibility Foundation)

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-00 — Research Archive, Data Provenance and Reproducibility Foundation
**Date:** 2026-11-26
**Branch:** `research/nlgcp-14-day-beta-sprint` (above local commit `5b5217a0033191134effebe0027d4ee16f70de5f`; **no commit, push, merge, or amend performed**)
**Operational Safety Controls:** Unchanged (`OPERATIONAL_APPROVED = FORBIDDEN`, Phase 6 `BEST = ZERO`, Phase 7 `VRS_GEOMETRY_ONLY`, `127.0.0.1` loopback-only lab boundary)

---

## 1. Milestone Verdict & Readiness Summary

| Dimension | Status | Directly Verified Evidence |
|---|---|---|
| **Stage 0: Initial Audit** | **COMPLETE** | [`00-initial-audit.md`](file:///home/excellence/NLGCP/docs/sprints/b00-research-archive/00-initial-audit.md) |
| **Stage 1: Architecture & Data Model** | **COMPLETE** | [`b00_research_archive_architecture.md`](file:///home/excellence/NLGCP/docs/architecture/b00_research_archive_architecture.md), [`b00_archive_data_model.md`](file:///home/excellence/NLGCP/docs/architecture/b00_archive_data_model.md), 6 JSON Schemas in [`research/archive/schema/`](file:///home/excellence/NLGCP/research/archive/schema/) |
| **Stages 2–5, 8, 10: Package & CLI** | **COMPLETE** | [`research/research_archive/src/nlgcp_research_archive/`](file:///home/excellence/NLGCP/research/research_archive/src/nlgcp_research_archive/) + [`scripts/run_research_archive.py`](file:///home/excellence/NLGCP/scripts/run_research_archive.py) + `[project.scripts] nlgcp` CLI (`exit 0/1/2/3`, strictly read-only) |
| **Stages 2–6, 9, 10: Real Archive Population** | **COMPLETE** | `21` datasets (`18` verified + `3` `UNAVAILABLE`), `17` experiments (`16` completed + `1` `SUPERSEDED`), `24` artifacts (`+311` nested B-02 outputs), `8` software entries (`5` hashed & verified), `18` findings, `12` limitations, `14` claims, `14` security findings, `6` reproduction records |
| **Stage 7: Central Project, Research & Ops Docs** | **COMPLETE** | All `13` canonical documents created across `docs/project/` (`5`), `docs/research/` (`5`), and `docs/operations/` (`3`) |
| **Stage 11: Automated Tests & Quality Gate** | **PASS** | `9/9` archive unit/CLI/safety/real-repo tests pass; full `make check` PASS (`849 passed, 13 skipped`, strict `mypy` `266` source files, Ruff, ESLint, TypeScript, Go, CTest `1/1`, Next.js build) |
| **Stage 12: Live Verification & Completeness Report** | **PASS (exit `0`)** | `.venv/bin/nlgcp archive verify --verify-nested` verified `18/18` available datasets (incl. `5.82 GiB` `NIGNET2011.zip`), `24/24` artifacts, `311/311` nested B-02 outputs, and `5/5` hashed scientific tools with `0` mismatches (`10-b00-archive-completeness-report.md`) |

---

## 2. Direct Answers to B-00 Engineering Handover Questions

1. **Were any existing research files, reports, raw GNSS datasets, or directory layouts moved, renamed, overwritten, or deleted?**
   **No.** Every existing file in `/home/excellence/NLGCP` and every file under `/home/excellence/nlgcp-data` (`~23 GiB`) was preserved strictly in place and untouched.
2. **Were any dataset hashes, software versions, commands, metrics, coordinates, or external products fabricated?**
   **No.** Every SHA-256 hash, byte size, commit hash, and metric was directly measured on disk. Unavailable products (`NLGCP-DATA-2011-006`, `NLGCP-DATA-2024-011`, `NLGCP-DATA-2026-004`) and unrecorded early-phase shell commands/configs are explicitly marked `NOT_AVAILABLE`, `NOT_RECORDED`, `NOT_APPLICABLE`, or `BLOCKED`.
3. **Is large research data duplicated into Git?**
   **No.** Zero RINEX, SP3, CLK, RTCM, or B-02 output binaries were copied into Git. External files are referenced via `${NLGCP_DATA_ROOT}/...` (`storage_type = "EXTERNAL_FILESYSTEM"`), and all `311` B-02 outputs are verified transitively via `NLGCP-ART-2026-024` (`hashes_manifest.json`).
4. **Is `nlgcp archive verify` strictly read-only by default?**
   **Yes.** Verification never modifies raw data, never rewrites expected hashes on mismatch, and never deletes or moves files (regression-tested in `test_cli_subcommands_exit_codes_and_readonly_safety` and `test_verify_file_integrity_rejects_bad_hash_format_without_touching_file`).
5. **What happens when external `/home/excellence/nlgcp-data` is absent or inaccessible (e.g., in CI)?**
   The CLI degrades fail-closed with deterministic exit code **`3` (`EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE`)** and reports `ACCESS_DENIED` on external entries while still validating all schemas, cross-references, and repository-local reports (`test_real_repository_archive_passes_schema_and_cross_references`).
6. **How is authentic vs. synthetic separation enforced?**
   `validator.py` enforces that no `AUTHENTIC` experiment may reference any `SYNTHETIC_TEST_DATA` dataset (`NLGCP-DATA-2026-003`). Violations fail validation with exit code `1`.
7. **Were negative and inconclusive scientific findings preserved?**
   **Yes.** All 11 mandatory negative/inconclusive findings are registered in [`findings_register.json`](file:///home/excellence/NLGCP/research/archive/validation/findings_register.json) and [`VALIDATION_REGISTER.md`](file:///home/excellence/NLGCP/docs/research/VALIDATION_REGISTER.md): `0.0%` genuine RTK FIX, `7` confirmed wrong-integer false fixes, geometry-only VRS degradation, 2024 kinematic H CI crossing zero, provisional 2011 truth, perimeter `ZERO`-dominance, `experimental_vrs.py:517` ZWD defect & fix, missing non-RTKLIB MSM4 decoder, `132` CDDIS auth failures, missing 2011/2024 precise/DCB/IONEX products, and Day 7 security blockers.
8. **Were all 14 Day 7 security findings preserved accurately without falsely marking them resolved?**
   **Yes.** [`security_findings_register.json`](file:///home/excellence/NLGCP/research/archive/validation/security_findings_register.json) and [`SECURITY_STATUS.md`](file:///home/excellence/NLGCP/docs/operations/SECURITY_STATUS.md) retain `SEC-01`–`SEC-13` as `OPEN` and `SEC-14` as `VERIFIED_LAB_CONTROL`.
9. **Are secrets or credentials prevented from entering environment snapshots?**
   **Yes.** `sanitize_environment_vars()` uses a strict 6-variable allowlist (`LANG`, `LC_ALL`, `TZ`, `NLGCP_DATA_ROOT`, `RTKLIB_SOURCE`, `VIRTUAL_ENV`) plus secret-substring and PEM/Bearer filters (`test_secret_redaction_never_captures_credentials`).
10. **What bugs were caught and fixed during B-00 implementation?**
    - Fixed `scan_unregistered_outputs()` in `hash_verifier.py` checking `item.parts` instead of `item.relative_to(scan_dir).parts[:-1]`, which excluded temp test roots under `/tmp`.
    - Added bundle-level `schema_version` inheritance in `registry.py` and explicit per-entry `schema_version` in `artifacts_registry.json`.
    - Added fail-closed `OSError` handling in `cli.py` for `--out-dir` / `--out` writes onto read-only/unmounted storage (returning exit `3` instead of an unhandled traceback).
11. **What exact verification outputs were written outside Git?**
    - `/home/excellence/nlgcp-data/processed/research-archive/b00/archive_verification_report.json`
    - `/home/excellence/nlgcp-data/processed/research-archive/b00/archive_verification_report.md`
12. **Were operational controls or scientific baselines altered?**
    **No.** `OPERATIONAL_APPROVED = FORBIDDEN`, Phase 6 `BEST = ZERO`, Phase 7 `VRS_GEOMETRY_ONLY`, and `127.0.0.1` loopback boundaries remain strictly intact.
13. **Was `git commit`, `git push`, `git merge`, `git reset`, or `git clean` run?**
    **No.** All B-00 changes remain uncommitted in the local working tree for explicit project-owner review.
14. **Did work proceed into B-04 or any follow-on milestone?**
    **No.** Execution stopped cleanly at the B-00 milestone boundary as instructed.

---

## 3. Inventory of New & Modified Repository Files

### New Archive Framework & CLI
- `research/research_archive/src/nlgcp_research_archive/{__init__,__main__,models,hash_verifier,validator,provenance,registry,cli}.py`
- `research/research_archive/tests/test_research_archive.py` (`9` unit, CLI, safety, secret-redaction & real-repo tests)
- `scripts/run_research_archive.py`
- `pyproject.toml` (registered `[project.scripts] nlgcp`, package wheel entry, pytest `pythonpath`/`testpaths`, and `mypy` `files`)

### New Machine-Readable Research Archive (`research/archive/`)
- `research/archive/schema/` (`6` JSON Schema files)
- `research/archive/datasets/` (`21` dataset manifests `NLGCP-DATA-*.json`)
- `research/archive/experiments/` (`17` experiment manifests `NLGCP-EXP-2026-001..017.json`)
- `research/archive/artifacts/artifacts_registry.json` (`24` registered artifacts + nested B-02 `311`-file manifest link)
- `research/archive/provenance/{software_inventory.json,environment_snapshot_2026-11-26.json}`
- `research/archive/validation/{findings_register.json,limitations_register.json,publication_evidence_map.json,security_findings_register.json}`
- `research/archive/reproducibility/repro_records.json`

### New Architecture, Sprint & Central Governance Docs
- `docs/architecture/{b00_research_archive_architecture.md,b00_archive_data_model.md}`
- `docs/project/{PROJECT_CHARTER.md,RESEARCH_OBJECTIVES.md,SYSTEM_ARCHITECTURE.md,TECHNICAL_DECISION_REGISTER.md,PROJECT_STATUS.md}`
- `docs/research/{DATASET_CATALOGUE.md,EXPERIMENT_CATALOGUE.md,VALIDATION_REGISTER.md,LIMITATIONS_REGISTER.md,PUBLICATION_EVIDENCE_MAP.md}`
- `docs/operations/{DEPLOYMENT_STATUS.md,SECURITY_STATUS.md,FIELD_VALIDATION_STATUS.md}`
- `docs/sprints/b00-research-archive/{00-initial-audit.md,10-b00-archive-completeness-report.md,final-b00-handover.md}`

### Updated Root Handoff & Governance Logs
- `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`

---

## 4. Recommended Next Actions (Awaiting User Authorization)

1. Review the uncommitted B-00 diff (`git status -s` / `git diff --stat`) and authorize a local Git commit for B-00 if satisfied.
2. Once B-00 is committed, proceed to the next explicitly authorized milestone (e.g., **B-04**, **B-01** 2011 precise coordinate acquisition, **B-06** non-RTKLIB MSM4 decoder, or **B-09** security hardening), registering every new experiment directly into `research/archive/` at completion.
