from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from nlgcp_api.station_metadata.provenance import (
    ProvenanceError,
    resolve_package_sources,
)
from nlgcp_api.station_metadata.validation import validate_station_import_payload

from .test_validation import valid_payload


def test_resolves_sources_and_computes_sha256(tmp_path: Path) -> None:
    source_path = tmp_path / "metadata" / "source-documents" / "synthetic-site.log"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS\n",
        encoding="utf-8",
    )
    package = validate_station_import_payload(valid_payload())

    resolved = resolve_package_sources(package, tmp_path)

    expected_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert resolved["site-log"].sha256 == expected_sha


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    source_path = tmp_path / "metadata" / "source-documents" / "synthetic-site.log"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS\n",
        encoding="utf-8",
    )
    payload = valid_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    source = sources[0]
    assert isinstance(source, dict)
    source["expected_sha256"] = "0" * 64
    package = validate_station_import_payload(payload)

    with pytest.raises(ProvenanceError, match="checksum mismatch"):
        resolve_package_sources(package, tmp_path)


def test_rejects_missing_source_file(tmp_path: Path) -> None:
    package = validate_station_import_payload(valid_payload())

    with pytest.raises(ProvenanceError, match="does not exist"):
        resolve_package_sources(package, tmp_path)
