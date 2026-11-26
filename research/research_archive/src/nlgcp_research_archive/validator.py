"""Manifest schema, cross-reference, and provenance validator for NLGCP B-00."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from nlgcp_research_archive.hash_verifier import is_valid_sha256_hex
from nlgcp_research_archive.models import (
    ARTIFACT_ID_RE,
    CLAIM_ID_RE,
    DATASET_ID_RE,
    EXPERIMENT_ID_RE,
    FINDING_ID_RE,
    LIMITATION_ID_RE,
    MISSING_TOKENS,
    REPRO_ID_RE,
    SOFTWARE_ID_RE,
    ClaimStatus,
    DatasetClassification,
    ExperimentStatus,
    ExperimentValidationResult,
    IntegrityStatus,
    RelationType,
    ReproducibilityStatus,
    ReproductionLevel,
    StorageType,
    ValidationLevel,
)

VALID_DATASET_CLASSIFICATIONS = {str(v) for v in DatasetClassification}
VALID_STORAGE_TYPES = {str(v) for v in StorageType}
VALID_INTEGRITY_STATUSES = {str(v) for v in IntegrityStatus}
VALID_EXPERIMENT_STATUSES = {str(v) for v in ExperimentStatus}
VALID_VALIDATION_LEVELS = {str(v) for v in ValidationLevel}
VALID_REPRO_STATUSES = {str(v) for v in ReproducibilityStatus}
VALID_REPRO_LEVELS = {str(v) for v in ReproductionLevel}
VALID_RELATION_TYPES = {str(v) for v in RelationType}
VALID_CLAIM_STATUSES = {str(v) for v in ClaimStatus}
VALID_DATA_TIERS = {"AUTHENTIC", "SYNTHETIC", "DOCUMENTATION_AUDIT", "MIXED_SEPARATED"}


def load_manifest_file(path: Path) -> dict[str, Any]:
    """Load a JSON or YAML manifest safely without modifying the file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        yaml_mod = importlib.import_module("yaml")
        parsed: Any = yaml_mod.safe_load(text)
    else:
        parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"manifest root must be a JSON/YAML object: {path}")
    return parsed


def _require_non_empty_str(data: dict[str, Any], key: str, errors: list[str]) -> str:
    val = data.get(key)
    if not isinstance(val, str) or not val.strip():
        errors.append(f"missing or empty required string field '{key}'")
        return ""
    return val.strip()


def validate_dataset_manifest(
    data: dict[str, Any],
    *,
    known_datasets: set[str] | None = None,
) -> list[str]:
    """Validate dataset manifest schema, controlled values, and hash formatting."""
    errors: list[str] = []
    _require_non_empty_str(data, "schema_version", errors)
    did = _require_non_empty_str(data, "dataset_id", errors)
    if did and not DATASET_ID_RE.match(did):
        errors.append(f"invalid dataset_id format '{did}' (expected NLGCP-DATA-YYYY-NNN)")
    _require_non_empty_str(data, "name", errors)
    _require_non_empty_str(data, "dataset_type", errors)
    scls = _require_non_empty_str(data, "source_classification", errors)
    if scls and scls not in VALID_DATASET_CLASSIFICATIONS:
        errors.append(f"invalid source_classification '{scls}'")
    _require_non_empty_str(data, "source_provider", errors)
    _require_non_empty_str(data, "description", errors)
    _require_non_empty_str(data, "acquisition_method", errors)
    if not isinstance(data.get("immutable_source"), bool):
        errors.append("missing or non-boolean required field 'immutable_source'")

    storage = data.get("storage")
    if not isinstance(storage, dict):
        errors.append("missing required object 'storage'")
    else:
        _require_non_empty_str(storage, "location", errors)
        stype = _require_non_empty_str(storage, "storage_type", errors)
        if stype and stype not in VALID_STORAGE_TYPES:
            errors.append(f"invalid storage.storage_type '{stype}'")
        _require_non_empty_str(storage, "original_filename", errors)

    integrity = data.get("integrity")
    if not isinstance(integrity, dict):
        errors.append("missing required object 'integrity'")
    else:
        algo = _require_non_empty_str(integrity, "algorithm", errors)
        if algo and algo != "SHA256":
            errors.append(f"unsupported integrity.algorithm '{algo}' (expected SHA256)")
        ehash = _require_non_empty_str(integrity, "expected_hash", errors)
        if ehash and ehash not in MISSING_TOKENS and not is_valid_sha256_hex(ehash):
            errors.append(f"invalid integrity.expected_hash format '{ehash}'")
        vstat = _require_non_empty_str(integrity, "verification_status", errors)
        if vstat and vstat not in VALID_INTEGRITY_STATUSES and vstat not in MISSING_TOKENS:
            errors.append(f"invalid integrity.verification_status '{vstat}'")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("missing required object 'metadata'")
    else:
        _require_non_empty_str(metadata, "format", errors)
        tc = metadata.get("temporal_coverage")
        if not isinstance(tc, dict) or not tc.get("start") or not tc.get("end"):
            errors.append("metadata.temporal_coverage must include 'start' and 'end'")
        _require_non_empty_str(metadata, "coordinate_reference_status", errors)
        _require_non_empty_str(metadata, "reference_frame", errors)

    for section in ("licensing", "registration"):
        if not isinstance(data.get(section), dict):
            errors.append(f"missing required object '{section}'")

    rels = data.get("relationships", {})
    if isinstance(rels, dict) and known_datasets is not None:
        for parent_id in rels.get("derived_from_datasets", []):
            if parent_id not in known_datasets:
                errors.append(f"unknown derived_from_datasets reference '{parent_id}'")
        for child_id in rels.get("derived_datasets", []):
            if child_id not in known_datasets:
                errors.append(f"unknown derived_datasets reference '{child_id}'")

    return errors


def validate_experiment_manifest(
    data: dict[str, Any],
    *,
    manifest_path: str,
    known_datasets: set[str],
    known_experiments: set[str],
    known_software: set[str],
    dataset_classifications: dict[str, str],
) -> ExperimentValidationResult:
    """Validate experiment schema, references, authentic/synthetic separation, and provenance."""
    errors: list[str] = []
    gaps: list[str] = []
    warnings: list[str] = []

    _require_non_empty_str(data, "schema_version", errors)
    eid = _require_non_empty_str(data, "experiment_id", errors) or "<MISSING_ID>"
    if eid != "<MISSING_ID>" and not EXPERIMENT_ID_RE.match(eid):
        errors.append(f"invalid experiment_id format '{eid}' (expected NLGCP-EXP-YYYY-NNN)")
    _require_non_empty_str(data, "title", errors)
    _require_non_empty_str(data, "milestone", errors)
    status = _require_non_empty_str(data, "status", errors)
    if status and status not in VALID_EXPERIMENT_STATUSES:
        errors.append(f"invalid experiment status '{status}'")

    data_tier = _require_non_empty_str(data, "data_classification", errors)
    if data_tier and data_tier not in VALID_DATA_TIERS:
        errors.append(f"invalid data_classification '{data_tier}'")

    _require_non_empty_str(data, "research_question", errors)

    ds_refs = data.get("datasets")
    if not isinstance(ds_refs, list):
        errors.append("missing required list 'datasets'")
        ds_refs = []
    else:
        for did in ds_refs:
            if not isinstance(did, str) or did not in known_datasets:
                errors.append(f"unknown dataset reference '{did}'")
            elif data_tier == "AUTHENTIC":
                cls = dataset_classifications.get(did, "")
                if cls == DatasetClassification.SYNTHETIC_TEST_DATA:
                    errors.append(
                        f"authentic/synthetic contamination: AUTHENTIC experiment '{eid}' "
                        f"references SYNTHETIC_TEST_DATA dataset '{did}'"
                    )

    sw = data.get("software")
    if not isinstance(sw, dict):
        errors.append("missing required object 'software'")
    else:
        rev = sw.get("nlgcp_revision", "")
        if not isinstance(rev, str) or not rev.strip():
            errors.append("missing software.nlgcp_revision")
        elif rev in MISSING_TOKENS:
            gaps.append(f"software.nlgcp_revision is {rev}")
        if sw.get("git_dirty") is True:
            warnings.append("experiment executed on a dirty Git working tree")
        elif sw.get("git_dirty") is None:
            gaps.append("software.git_dirty not recorded")
        py_ver = sw.get("python_version", "")
        if not py_ver or py_ver in MISSING_TOKENS:
            gaps.append("software.python_version not recorded")
        sw_ids = sw.get("software_ids", [])
        if not isinstance(sw_ids, list):
            errors.append("software.software_ids must be a list")
        else:
            for sw_id in sw_ids:
                if sw_id not in known_software:
                    errors.append(f"unknown software reference '{sw_id}'")

    cfg = data.get("configuration")
    if not isinstance(cfg, dict):
        errors.append("missing required object 'configuration'")
    else:
        cfg_loc = str(cfg.get("location", ""))
        cfg_sha = str(cfg.get("sha256", ""))
        if not cfg_loc or cfg_loc in MISSING_TOKENS:
            gaps.append(f"configuration.location is {cfg_loc or 'MISSING'}")
        if not cfg_sha or cfg_sha in MISSING_TOKENS:
            gaps.append(f"configuration.sha256 is {cfg_sha or 'MISSING'}")
        elif not is_valid_sha256_hex(cfg_sha):
            errors.append(f"invalid configuration.sha256 format '{cfg_sha}'")

    exe = data.get("execution")
    if not isinstance(exe, dict):
        errors.append("missing required object 'execution'")
    else:
        cmd = str(exe.get("command", ""))
        if not cmd or cmd in MISSING_TOKENS:
            gaps.append(f"execution.command is {cmd or 'MISSING'}")
        env_rec = str(exe.get("environment", ""))
        if not env_rec or env_rec in MISSING_TOKENS:
            gaps.append(f"execution.environment is {env_rec or 'MISSING'}")

    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        errors.append("missing required list 'outputs'")
    elif not outputs and status == ExperimentStatus.COMPLETED:
        gaps.append("completed experiment has zero recorded outputs")

    val = data.get("validation")
    if not isinstance(val, dict):
        errors.append("missing required object 'validation'")
    else:
        lvl = _require_non_empty_str(val, "highest_level", errors)
        if lvl and lvl not in VALID_VALIDATION_LEVELS:
            errors.append(f"invalid validation.highest_level '{lvl}'")

    repro = data.get("reproducibility")
    if not isinstance(repro, dict):
        errors.append("missing required object 'reproducibility'")
    else:
        rstat = _require_non_empty_str(repro, "status", errors)
        if rstat and rstat not in VALID_REPRO_STATUSES:
            errors.append(f"invalid reproducibility.status '{rstat}'")
        rlvl = _require_non_empty_str(repro, "level", errors)
        if rlvl and rlvl not in VALID_REPRO_LEVELS:
            errors.append(f"invalid reproducibility.level '{rlvl}'")

    rels = data.get("relationships", [])
    if not isinstance(rels, list):
        errors.append("relationships must be a list")
    else:
        for edge in rels:
            if not isinstance(edge, dict):
                errors.append("relationship entry must be an object")
                continue
            rtype = str(edge.get("type", ""))
            target = str(edge.get("target_id", ""))
            if rtype not in VALID_RELATION_TYPES:
                errors.append(f"invalid relationship type '{rtype}'")
                continue
            if rtype in (RelationType.USES_DATASET, RelationType.PRODUCES_DATASET):
                if target not in known_datasets:
                    errors.append(f"relationship {rtype} references unknown dataset '{target}'")
            elif target not in known_experiments:
                errors.append(f"relationship {rtype} references unknown experiment '{target}'")

    return ExperimentValidationResult(
        experiment_id=eid,
        manifest_path=manifest_path,
        status=status or "UNKNOWN",
        valid=len(errors) == 0,
        provenance_complete=(len(errors) == 0 and len(gaps) == 0),
        errors=tuple(errors),
        provenance_gaps=tuple(gaps),
        warnings=tuple(warnings),
    )


def validate_artifact_manifest(
    data: dict[str, Any],
    *,
    known_experiments: set[str],
    known_datasets: set[str],
) -> list[str]:
    """Validate an artifact manifest record and its cross-references."""
    errors: list[str] = []
    _require_non_empty_str(data, "schema_version", errors)
    aid = _require_non_empty_str(data, "artifact_id", errors)
    if aid and not ARTIFACT_ID_RE.match(aid):
        errors.append(f"invalid artifact_id format '{aid}' (expected NLGCP-ART-YYYY-NNN)")
    eid = _require_non_empty_str(data, "experiment_id", errors)
    if eid and eid not in known_experiments:
        errors.append(f"artifact '{aid}' references unknown experiment_id '{eid}'")
    _require_non_empty_str(data, "file_path", errors)
    stype = _require_non_empty_str(data, "storage_type", errors)
    if stype and stype not in VALID_STORAGE_TYPES:
        errors.append(f"invalid artifact storage_type '{stype}'")
    _require_non_empty_str(data, "file_type", errors)
    sha_val = _require_non_empty_str(data, "sha256", errors)
    if sha_val and sha_val not in MISSING_TOKENS and not is_valid_sha256_hex(sha_val):
        errors.append(f"invalid artifact sha256 format '{sha_val}'")
    _require_non_empty_str(data, "description", errors)
    src_ds = data.get("source_datasets", [])
    if not isinstance(src_ds, list):
        errors.append("source_datasets must be a list")
    else:
        for did in src_ds:
            if did not in known_datasets:
                errors.append(f"artifact '{aid}' references unknown dataset '{did}'")
    return errors


def validate_software_entry(entry: dict[str, Any]) -> list[str]:
    """Validate one software inventory record."""
    errors: list[str] = []
    sw_id = _require_non_empty_str(entry, "software_id", errors)
    if sw_id and not SOFTWARE_ID_RE.match(sw_id):
        errors.append(f"invalid software_id format '{sw_id}'")
    _require_non_empty_str(entry, "name", errors)
    _require_non_empty_str(entry, "version", errors)
    ehash = entry.get("expected_sha256")
    if (
        isinstance(ehash, str)
        and ehash not in MISSING_TOKENS
        and not is_valid_sha256_hex(ehash)
    ):
        errors.append(f"invalid software expected_sha256 '{ehash}' for '{sw_id}'")
    return errors


def validate_validation_registers(
    *,
    findings: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    reproductions: list[dict[str, Any]],
    known_experiments: set[str],
    known_datasets: set[str],
    known_artifacts: set[str],
) -> list[str]:
    """Validate cross-references across findings, limitations, claims, and repro records."""
    errors: list[str] = []
    seen_findings: set[str] = set()
    seen_limitations: set[str] = set()
    seen_claims: set[str] = set()
    seen_repros: set[str] = set()

    for lim in limitations:
        lid = str(lim.get("limitation_id", ""))
        if not LIMITATION_ID_RE.match(lid):
            errors.append(f"invalid limitation_id '{lid}'")
        elif lid in seen_limitations:
            errors.append(f"duplicate limitation_id '{lid}'")
        seen_limitations.add(lid)
        for eid in lim.get("related_experiments", []):
            if eid not in known_experiments:
                errors.append(f"limitation '{lid}' references unknown experiment '{eid}'")

    for fnd in findings:
        fid = str(fnd.get("finding_id", ""))
        if not FINDING_ID_RE.match(fid):
            errors.append(f"invalid finding_id '{fid}'")
        elif fid in seen_findings:
            errors.append(f"duplicate finding_id '{fid}'")
        seen_findings.add(fid)
        lvl = str(fnd.get("validation_level", ""))
        if lvl not in VALID_VALIDATION_LEVELS:
            errors.append(f"finding '{fid}' has invalid validation_level '{lvl}'")
        for eid in fnd.get("supporting_experiments", []):
            if eid not in known_experiments:
                errors.append(f"finding '{fid}' references unknown experiment '{eid}'")
        for did in fnd.get("supporting_datasets", []):
            if did not in known_datasets:
                errors.append(f"finding '{fid}' references unknown dataset '{did}'")
        for aid in fnd.get("result_artifacts", []):
            if aid not in known_artifacts:
                errors.append(f"finding '{fid}' references unknown artifact '{aid}'")

    for clm in claims:
        cid = str(clm.get("claim_id", ""))
        if not CLAIM_ID_RE.match(cid):
            errors.append(f"invalid claim_id '{cid}'")
        elif cid in seen_claims:
            errors.append(f"duplicate claim_id '{cid}'")
        seen_claims.add(cid)
        cstat = str(clm.get("status", ""))
        if cstat not in VALID_CLAIM_STATUSES:
            errors.append(f"claim '{cid}' has invalid status '{cstat}'")
        f_refs = clm.get("supporting_findings", [])
        if cstat in (ClaimStatus.SUPPORTED, ClaimStatus.SUPPORTED_WITH_LIMITATIONS) and not f_refs:
            errors.append(
                f"claim '{cid}' marked {cstat} without supporting_findings "
                "(must be INSUFFICIENT_EVIDENCE)"
            )
        for fid in f_refs:
            if fid not in seen_findings:
                errors.append(f"claim '{cid}' references unknown finding '{fid}'")

    for rep in reproductions:
        rid = str(rep.get("reproduction_id", ""))
        if not REPRO_ID_RE.match(rid):
            errors.append(f"invalid reproduction_id '{rid}'")
        elif rid in seen_repros:
            errors.append(f"duplicate reproduction_id '{rid}'")
        seen_repros.add(rid)
        orig = str(rep.get("original_experiment_id", ""))
        if orig not in known_experiments:
            errors.append(f"reproduction '{rid}' references unknown original experiment '{orig}'")
        rstat = str(rep.get("outcome", ""))
        if rstat not in VALID_REPRO_STATUSES:
            errors.append(f"reproduction '{rid}' has invalid outcome '{rstat}'")
        rlvl = str(rep.get("reproduction_level", ""))
        if rlvl not in VALID_REPRO_LEVELS:
            errors.append(f"reproduction '{rid}' has invalid reproduction_level '{rlvl}'")

    return errors
