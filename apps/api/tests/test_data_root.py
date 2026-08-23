from pathlib import Path

import pytest
from nlgcp_api.config import (
    REQUIRED_DATA_ROOT_DIRECTORIES,
    Settings,
    resolve_data_root,
)


def _create_vault(root: Path) -> None:
    for directory in REQUIRED_DATA_ROOT_DIRECTORIES:
        (root / directory).mkdir(parents=True)


def test_data_root_must_be_configured() -> None:
    settings = Settings(data_root=None)

    with pytest.raises(
        RuntimeError,
        match="NLGCP_DATA_ROOT is required",
    ):
        resolve_data_root(settings)


def test_data_root_must_exist(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    settings = Settings(data_root=missing)

    with pytest.raises(
        RuntimeError,
        match="does not exist",
    ):
        resolve_data_root(settings)


def test_data_root_must_be_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("test", encoding="utf-8")
    settings = Settings(data_root=file_path)

    with pytest.raises(
        RuntimeError,
        match="not a directory",
    ):
        resolve_data_root(settings)


def test_data_root_requires_phase2_structure(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    settings = Settings(data_root=tmp_path)

    with pytest.raises(
        RuntimeError,
        match="missing required directories",
    ):
        resolve_data_root(settings)


def test_data_root_accepts_valid_phase2_vault(tmp_path: Path) -> None:
    _create_vault(tmp_path)
    settings = Settings(data_root=tmp_path)

    assert resolve_data_root(settings) == tmp_path.resolve()
