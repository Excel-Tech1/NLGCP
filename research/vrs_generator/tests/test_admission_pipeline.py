"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nlgcp_atmospheric_model.provenance import sha256_file
from nlgcp_vrs.models import Blocked, Definition
from nlgcp_vrs.pipeline import generate, plan, read_json, write_json
from test_vrs import definition, rinex, validation_document


@pytest.fixture
def enclave(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Definition, Path]:
    import nlgcp_vrs.pipeline as pipeline

    d = definition()
    repo = Path(__file__).resolve().parents[3]
    root = tmp_path
    coordinates: dict[str, Any] = {}
    sessions = []
    p5 = root / "processed/network-rtk/experiments" / d.source_network_experiment
    p6 = root / "processed/atmospheric-model/experiments" / d.source_phase6_experiment
    p5.mkdir(parents=True)
    (p6 / "validation").mkdir(parents=True)
    (p6 / "models").mkdir()
    nav = root / "synthetic.nav"
    nav.write_text("SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS\n")
    obs_hashes = {}
    for i, s in enumerate(("A", "B", "C", "D")):
        obs = root / (s + ".24o")
        rinex(obs)
        # Distinct receiver/source metadata; never use target bytes as a reference.
        obs.write_text(
            obs.read_text().replace("SYNTHETIC TEST DATA -", f"SYNTHETIC {s} DATA -    ")
        )
        pos = root / (s + ".pos")
        pos.write_text("SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS " + s)
        coords = {"x_m": 6378137.0, "y_m": float(i * 100), "z_m": 0.0}
        coordinates[s] = {
            "ecef": coords,
            "scientifically_valid": True,
            "reference_frame": "IGS20",
            "coordinate_epoch": d.coordinate_epoch,
            "pos_file_path": str(pos),
            "pos_file_sha256": sha256_file(pos),
        }
        obs_hashes[s] = sha256_file(obs)
        session = {
            "station_id": s,
            "qc_status": "ACCEPT",
            "phase4_result_fingerprint": "qc-" + s,
            "observation_path": str(obs),
            "converted_sha256": obs_hashes[s],
            "navigation_path": "synthetic.nav",
            "navigation_sha256": sha256_file(nav),
        }
        sessions.append(session)
        qc = root / f"processed/qc/profiles/network_rtk/sessions/2024/{s}/026/qc-result.json"
        qc.parent.mkdir(parents=True)
        write_json(
            qc,
            {
                "overall_classification": "ACCEPT",
                "result_fingerprint": "qc-" + s,
                "qc_profile": {"name": "network_rtk"},
                "conversion": {"converted_sha256": obs_hashes[s]},
            },
        )
    coordpath = root / "processed/single-base/derived-coordinates.json"
    coordpath.parent.mkdir(parents=True)
    write_json(coordpath, {"stations": coordinates})
    write_json(
        p5 / "experiment.json",
        {
            "experiment_id": d.source_network_experiment,
            "coordinate_frame": "IGS20",
            "coordinate_epoch": d.coordinate_epoch,
            "year": 2024,
            "day_of_year": 26,
            "reference_stations": ["A", "B", "C"],
            "test_station": "D",
        },
    )
    write_json(p5 / "geometry.json", {"label": "SYNTHETIC TEST DATA"})
    write_json(p5 / "validation.json", {"verdict": "COMPLETE"})
    write_json(
        p5 / "admission.json",
        {
            "year": 2024,
            "day_of_year": 26,
            "qc_profile": "network_rtk",
            "diagnostic": False,
            "admitted": sessions,
        },
    )
    write_json(
        p6 / "definition.json",
        {
            "phase5_experiment_id": d.source_network_experiment,
            "year": 2024,
            "day_of_year": 26,
            "coordinate_frame": "IGS20",
            "coordinate_epoch": d.coordinate_epoch,
            "reference_stations": ["A", "B", "C"],
            "target_station": "D",
        },
    )
    write_json(p6 / "admission.json", {"status": "COMPLETE"})
    write_json(
        p6 / "derive-status.json",
        {
            "status": "COMPLETE",
            "provenance": {
                "inputs": {
                    "nav_sha256": sha256_file(nav),
                    "observation_sha256": obs_hashes,
                    "station_coordinates": {s: c["ecef"] for s, c in coordinates.items()},
                }
            },
        },
    )
    write_json(p6 / "validation/loocv.json", validation_document())
    (p6 / "models/target-predictions.csv").write_text("SYNTHETIC TEST DATA\n")
    monkeypatch.setattr(pipeline, "source_provenance", lambda _: {"synthetic": True})
    return root, d, repo


def test_plan_never_reads_target_observations(enclave: tuple[Path, Definition, Path]) -> None:
    root, d, repo = enclave
    (root / "D.24o").unlink()
    result = plan(root, d, repo, root)
    assert result["anchor"]["station"] == "C"
    assert result["target"]["target_height"] is not None
    assert "D" not in result["observations"]
    assert "D" not in result["material"]["source_observation_sha256"]
    assert not Path(result["outputs"]).exists()


@pytest.mark.parametrize(
    "change",
    [
        "observation",
        "navigation",
        "coordinate",
        "coordinate_epoch",
        "coordinate_frame",
        "coordinate_nan",
        "qc",
        "phase6",
        "phase6_source",
    ],
)
def test_admission_fails_closed(enclave: tuple[Path, Definition, Path], change: str) -> None:
    root, d, repo = enclave
    if change == "observation":
        (root / "A.24o").write_text("changed")
    elif change == "navigation":
        (root / "synthetic.nav").write_text("changed")
    elif change.startswith("coordinate"):
        p = root / "processed/single-base/derived-coordinates.json"
        doc = read_json(p)
        coord = doc["stations"]["D"]
        if change == "coordinate":
            coord["scientifically_valid"] = False
        elif change == "coordinate_epoch":
            coord["coordinate_epoch"] = "2023-01-01"
        elif change == "coordinate_frame":
            coord["reference_frame"] = "WGS84"
        else:
            coord["ecef"]["x_m"] = "nan"
        write_json(p, doc)
    elif change == "qc":
        p = root / "processed/qc/profiles/network_rtk/sessions/2024/A/026/qc-result.json"
        doc = read_json(p)
        doc["overall_classification"] = "REJECT"
        write_json(p, doc)
    elif change == "phase6_source":
        p = (
            root
            / "processed/atmospheric-model/experiments"
            / d.source_phase6_experiment
            / "definition.json"
        )
        doc = read_json(p)
        doc["day_of_year"] = 27
        write_json(p, doc)
    else:
        p = (
            root
            / "processed/atmospheric-model/experiments"
            / d.source_phase6_experiment
            / "validation/loocv.json"
        )
        doc = validation_document()
        doc["status"] = "BLOCKED"
        write_json(p, doc)
    with pytest.raises(Blocked):
        plan(root, d, repo, root)


def test_dry_run_and_resume(
    enclave: tuple[Path, Definition, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import nlgcp_vrs.pipeline as pipeline

    root, d, repo = enclave
    result = generate(root, d, repo, root, dry_run=True)
    assert not Path(result["outputs"]).exists()
    monkeypatch.setattr(
        pipeline, "build_adapter", lambda *_: (root / "synthetic-adapter", {"synthetic": True})
    )
    monkeypatch.setattr(
        pipeline,
        "geometry_batch",
        lambda *args: [
            {"geometric_transformation_m": 10.0, "satellite_clock_translation_m": 0.0}
            for _ in args[4]
        ],
    )
    first = generate(root, d, repo, root)
    second = generate(root, d, repo, root)
    assert first["virtual_observation_count"] == 2
    assert not first["reused"] and second["reused"]
    out = Path(first["outputs"])
    assert read_json(out / "provenance.json")["held_out_observations_used"] is False
    (out / "virtual-observations.csv").write_text("corrupted")
    with pytest.raises(Blocked, match="SHA-256 mismatch"):
        generate(root, d, repo, root)


def test_alias_target_cannot_enter_generation(enclave: tuple[Path, Definition, Path]) -> None:
    root, d, repo = enclave
    path = (
        root / "processed/network-rtk/experiments" / d.source_network_experiment / "admission.json"
    )
    doc = read_json(path)
    doc["admitted"][0]["observation_path"] = str(root / "D.24o")
    write_json(path, doc)
    with pytest.raises(Blocked, match="leakage"):
        plan(root, d, repo, root)


def test_incomplete_phase5_blocks(enclave: tuple[Path, Definition, Path]) -> None:
    root, d, repo = enclave
    path = (
        root / "processed/network-rtk/experiments" / d.source_network_experiment / "validation.json"
    )
    write_json(path, {"verdict": "BLOCKED"})
    with pytest.raises(Blocked, match="Phase 5 network validation incomplete"):
        plan(root, d, repo, root)
