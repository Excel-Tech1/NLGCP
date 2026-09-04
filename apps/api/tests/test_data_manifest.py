from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from nlgcp_api.data_manifest import (
    ManifestArtifact,
    build_data_manifest,
    default_manifest_output_path,
    find_conflicting_paths,
    write_data_manifest,
)

SYNTHETIC_NOTICE = "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS"


def test_builds_manifest_with_duplicate_checksum_detection(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    metadata_dir = tmp_path / "metadata"
    raw_dir.mkdir()
    metadata_dir.mkdir()
    (raw_dir / "duplicate-a.bin").write_text(SYNTHETIC_NOTICE, encoding="utf-8")
    (metadata_dir / "duplicate-b.bin").write_text(SYNTHETIC_NOTICE, encoding="utf-8")

    manifest = build_data_manifest(tmp_path)

    assert [artifact.relative_vault_path for artifact in manifest.artifacts] == [
        "metadata/duplicate-b.bin",
        "raw/duplicate-a.bin",
    ]
    assert len(manifest.duplicate_checksums) == 1
    assert manifest.duplicate_checksums[0].relative_vault_paths == [
        "metadata/duplicate-b.bin",
        "raw/duplicate-a.bin",
    ]


def test_conflicting_path_detection_is_case_insensitive() -> None:
    artifacts = [
        _artifact("raw/ABCD0010.26o", "a" * 64),
        _artifact("raw/abcd0010.26o", "b" * 64),
    ]

    conflicts = find_conflicting_paths(artifacts)

    assert len(conflicts) == 1
    assert conflicts[0].normalized_path == "raw/abcd0010.26o"
    assert conflicts[0].relative_vault_paths == [
        "raw/ABCD0010.26o",
        "raw/abcd0010.26o",
    ]


def test_manifest_reports_malformed_rinex_candidate(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "abcd0010.26o.Z").write_bytes(b"synthetic compressed placeholder\n")

    manifest = build_data_manifest(tmp_path)

    assert manifest.artifacts[0].parser_status == "not_parsed"
    assert manifest.artifacts[0].warnings == [
        "compression unix-compress is discovered but not parsed"
    ]
    assert manifest.malformed_artifacts == []


def test_manifest_write_is_deterministic_when_output_is_excluded(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    manifests_dir = tmp_path / "manifests"
    raw_dir.mkdir()
    manifests_dir.mkdir()
    (raw_dir / "artifact.bin").write_text(SYNTHETIC_NOTICE, encoding="utf-8")
    output_path = default_manifest_output_path(tmp_path)
    excluded = {PurePosixPath("manifests/scientific-data-manifest.json")}

    first_manifest = build_data_manifest(tmp_path, exclude_paths=excluded)
    write_data_manifest(first_manifest, output_path)
    first = output_path.read_text(encoding="utf-8")
    second_manifest = build_data_manifest(tmp_path, exclude_paths=excluded)
    write_data_manifest(second_manifest, output_path)
    second = output_path.read_text(encoding="utf-8")

    assert first == second
    assert json.loads(first)["artifacts"][0]["relative_vault_path"] == "raw/artifact.bin"


def _artifact(path: str, checksum: str) -> ManifestArtifact:
    return ManifestArtifact(
        relative_vault_path=path,
        filename=Path(path).name,
        file_size_bytes=1,
        modified_time_utc="2026-01-01T00:00:00+00:00",
        sha256=checksum,
        artifact_type="file",
        parser_status=None,
        warnings=[],
        errors=[],
    )
