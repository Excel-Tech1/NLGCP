"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from nlgcp_atmospheric_model.provenance import fingerprint, sha256_file
from nlgcp_vrs.models import Blocked, Definition, anchor_selection, correction_gate
from nlgcp_vrs.observations import (
    SUPPORTED,
    WAVELENGTHS,
    Dataset,
    Measurement,
    read_observations,
    transform,
)
from nlgcp_vrs.pipeline import (
    checked_hash,
    experiment_dir,
    read_verified_outputs,
    synthesis_rows,
    write_json,
)
from nlgcp_vrs.validation import residuals

LABEL = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"
EPOCH = "2024-01-26T00:00:00.000000"
NEXT = "2024-01-26T00:03:00.000000"


def definition(**updates: Any) -> Definition:
    body = dict(
        experiment_id="synthetic-vrs",
        year=2024,
        day_of_year=26,
        target_station="D",
        reference_stations=["A", "B", "C"],
        source_network_experiment="synthetic-network",
        source_phase6_experiment="synthetic-atm",
        coordinate_frame="IGS20",
        coordinate_epoch="2024-01-26T12:00:00Z",
        start_time="2024-01-26T00:00:00",
        end_time="2024-01-26T00:03:00",
        sampling_interval=180.0,
    )
    return Definition.model_validate({**body, **updates})


def validation_document() -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "loocv": {
            "comparison_keys": 100,
            "best_model": "zero",
            "models": {
                name: {"count": 100, "rmse_m": value}
                for name, value in (
                    ("zero", 2.984),
                    ("idw", 3.546),
                    ("nearest", 4.004),
                    ("planar", 15.3),
                )
            },
        },
    }


def datasets() -> dict[str, Dataset]:
    observation = {
        c: Measurement(20000000.0 if c[0] != "L" else 100000000.0, 0, 6, 0) for c in SUPPORTED
    }
    dataset = Dataset(
        SUPPORTED, 30.0, {EPOCH: {"G01": observation}, NEXT: {"G01": copy.deepcopy(observation)}}
    )
    return {name: copy.deepcopy(dataset) for name in ("A", "B", "C")}


def geometry() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (e, "G01"): {"geometric_transformation_m": 100.0, "satellite_clock_translation_m": 0.25}
        for e in (EPOCH, NEXT)
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"experiment_id": "../escape"},
        {"target_station": "A"},
        {"reference_stations": ["A", "A", "B"]},
        {"reference_stations": ["A", "B"]},
        {"coordinate_frame": "WGS84"},
        {"coordinate_epoch": ""},
        {"sampling_interval": 0},
        {"sampling_interval": float("nan")},
        {"start_time": "2024-01-26T00:00:00Z"},
        {"end_time": "2024-01-25T23:59:00"},
        {"day_of_year": 27},
        {"correction_model": "idw"},
        {"rinex_output": True},
        {"unknown": True},
    ],
)
def test_invalid_definition(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        definition(**changes)


def test_virtual_identity_and_target_policy() -> None:
    d = definition()
    assert d.virtual_id == "VRS_synthetic-vrs"
    assert d.virtual_id not in (*d.reference_stations, d.target_station)
    assert d.target_policy == "verified_station_coordinate"


def test_anchor_nearest_and_tie_break() -> None:
    assert anchor_selection({"B": (1, 0, 0), "A": (-1, 0, 0)}, (0, 0, 0))["station"] == "A"
    assert anchor_selection({"A": (2, 0, 0), "B": (1, 0, 0)}, (0, 0, 0))["station"] == "B"
    with pytest.raises(Blocked):
        anchor_selection({"A": (float("nan"), 0, 0)}, (0, 0, 0))


def test_zero_control_no_promotion() -> None:
    gate = correction_gate(validation_document())
    assert gate["spatial_correction"] == "ZERO"
    assert gate["promoted_model"] is None
    assert not gate["automatic_correction_approved"]


def test_numeric_improvement_alone_does_not_promote() -> None:
    doc = validation_document()
    doc["loocv"]["models"]["idw"]["rmse_m"] = 1.0
    doc["loocv"]["best_model"] = "idw"
    gate = correction_gate(doc)
    assert gate["candidates"]["idw"]["improves_zero"]
    assert gate["candidates"]["idw"]["status"] == "NOT_APPROVED"
    assert gate["spatial_correction"] == "ZERO"


@pytest.mark.parametrize("model", ["nearest", "idw", "planar"])
def test_diagnostic_models_block_without_valid_translation(model: str) -> None:
    with pytest.raises(Blocked, match="GF_SD_ARC_DETRENDED"):
        correction_gate(validation_document(), model, True)


@pytest.mark.parametrize("problem", ["missing", "nan", "count", "winner", "incomplete"])
def test_bad_validation_blocks(problem: str) -> None:
    doc = validation_document()
    if problem == "missing":
        del doc["loocv"]["models"]["zero"]
    elif problem == "nan":
        doc["loocv"]["models"]["idw"]["rmse_m"] = float("nan")
    elif problem == "count":
        doc["loocv"]["models"]["idw"]["count"] = 99
    elif problem == "winner":
        doc["loocv"]["best_model"] = "idw"
    else:
        doc["status"] = "PARTIAL"
    with pytest.raises(Blocked):
        correction_gate(doc)


@pytest.mark.parametrize("code", SUPPORTED)
def test_observation_translation_units_and_sign(code: str) -> None:
    delta = transform(code, 20000000.0, 100.0, -0.5) - 20000000.0
    assert delta * WAVELENGTHS.get(code, 1) == pytest.approx(99.5, abs=1e-8)
    assert transform(code, 20000000.0, 0, 0) == 20000000.0


@pytest.mark.parametrize("code", ["D1", "S1", "C5", "L5"])
def test_unsupported_codes(code: str) -> None:
    with pytest.raises(Blocked):
        transform(code, 1, 1, 0)


def test_synthesis_is_deterministic_and_traceable() -> None:
    data = datasets()
    rows, _ = synthesis_rows(definition(), data, "A", geometry(), "synthetic-hash")
    assert len(rows) == 10
    assert rows[0]["ionosphere_correction_m"] == 0
    assert rows[0]["troposphere_correction_m"] == 0
    assert rows[0]["provenance_id"] == "synthetic-hash"
    assert (
        rows
        == synthesis_rows(
            definition(), dict(reversed(list(data.items()))), "A", geometry(), "synthetic-hash"
        )[0]
    )


@pytest.mark.parametrize("missing", ["epoch", "satellite", "code", "ephemeris"])
def test_common_support_gate(missing: str) -> None:
    data, geo = datasets(), geometry()
    if missing == "epoch":
        del data["B"].data[EPOCH]
    elif missing == "satellite":
        del data["B"].data[EPOCH]["G01"]
    elif missing == "code":
        del data["B"].data[EPOCH]["G01"]["C1"]
    else:
        geo[(EPOCH, "G01")] = {"reason": "missing ephemeris"}
    rows, excluded = synthesis_rows(definition(), data, "A", geo, "test")
    assert len(rows) == (9 if missing == "code" else 5)
    assert sum(excluded.values()) > 0


def test_target_leakage_blocked() -> None:
    data = datasets()
    data["D"] = data["A"]
    with pytest.raises(Blocked, match="leakage"):
        synthesis_rows(definition(), data, "A", geometry(), "test")


def test_carrier_lli_and_half_cycle() -> None:
    data = datasets()
    data["A"].data[EPOCH]["G01"]["L1"] = Measurement(1e8, 4, 6, 0)
    data["A"].data[EPOCH]["G01"]["L2"] = Measurement(1e8, 2, 7, 0)
    rows, excluded = synthesis_rows(definition(), data, "A", geometry(), "test")
    row = next(r for r in rows if r["epoch_gpst"] == EPOCH and r["observation_code"] == "L1")
    assert (row["source_lli"], row["source_ssi"], row["ambiguity_policy"]) == (
        4,
        6,
        "ANCHOR_RELATIVE_FLOAT",
    )
    assert excluded["anchor phase half-cycle ambiguity"] == 1


def rinex(path: Path, *, flag: int = 0, value: str = "  20000000.000") -> None:
    def header(body: str, label: str) -> str:
        return f"{body:<60}{label}\n"

    content = header("     2.11           OBSERVATION DATA    G", "RINEX VERSION / TYPE")
    content += header("SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS", "COMMENT")
    content += header("     2    C1    L1", "# / TYPES OF OBSERV")
    content += header("    30.000", "INTERVAL")
    content += header("  2024     1    26     0     0    0.0000000     GPS", "TIME OF FIRST OBS")
    content += header("     1     1", "WAVELENGTH FACT L1/2")
    content += header("", "END OF HEADER")
    content += f" 24  1 26  0  0  0.0000000  {flag}  1G01\n"
    content += f"{value:>14} 6{100000000.0:14.3f}46\n"
    path.write_text(content)


def test_rinex_gpst_phase_flags(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.24o"
    rinex(path)
    data = read_observations(path)
    assert list(data.data) == [EPOCH]
    assert data.data[EPOCH]["G01"]["L1"].lli == 4
    assert data.data[EPOCH]["G01"]["C1"].value == 20000000


@pytest.mark.parametrize("mutation", ["event", "nan", "utc", "truncated", "half", "duplicate"])
def test_rinex_malformed_fails_closed(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "synthetic.24o"
    rinex(
        path, flag=4 if mutation == "event" else 0, value="nan" if mutation == "nan" else "20000000"
    )
    text = path.read_text()
    if mutation == "utc":
        text = text.replace("GPS", "UTC")
    elif mutation == "truncated":
        text = text.rsplit("\n", 2)[0] + "\n"
    elif mutation == "half":
        text = text.replace("     1     1", "     2     1")
    elif mutation == "duplicate":
        text += "\n".join(text.splitlines()[-2:]) + "\n"
    path.write_text(text)
    with pytest.raises(Blocked):
        read_observations(path)


def test_clock_and_integer_ambiguity_datums_cancel() -> None:
    rows = []
    target = Dataset(("C1", "L1"), 180, {})
    for i, epoch in enumerate((EPOCH, NEXT)):
        target.data[epoch] = {}
        for j, sat in enumerate(("G01", "G02", "G03")):
            target.data[epoch][sat] = {
                "C1": Measurement(2e7, 0, 6, 0),
                "L1": Measurement(1e8, 4, 6, 0),
            }
            for code in ("C1", "L1"):
                # Arbitrary time-varying receiver clock and satellite-dependent
                # constant phase ambiguity: must not be called residual error.
                value = (
                    2e7 + 100 + i * 10
                    if code == "C1"
                    else 1e8 + 1000 * j + (100 + i * 10) / WAVELENGTHS["L1"]
                )
                rows.append(
                    {
                        "epoch_gpst": epoch,
                        "satellite": sat,
                        "observation_code": code,
                        "virtual_observation": value,
                        "source_lli": 4,
                        "epoch_flag": 0,
                    }
                )
    output, summary = residuals(rows, target, 180)
    assert len(output) == 8
    assert "tolerance_m" not in summary["C1"]
    assert "coverage_within_tolerance" not in summary["L1"]
    assert summary["C1"]["rmse_m"] == pytest.approx(0)
    assert summary["L1"]["rmse_m"] == pytest.approx(0, abs=1e-7)
    target.data[NEXT]["G02"]["L1"] = Measurement(1e8, 5, 6, 0)
    _, summary = residuals(rows, target, 180)
    assert summary["L1"]["count"] == 1
    _, summary = residuals(rows, target, 30)
    assert summary["L1"]["count"] == 0  # no gap bridging


def test_fingerprint_changes_with_material_inputs() -> None:
    base = {"observation": "a", "nav": "b", "xyz": [1, 2, 3], "phase6": "c", "algorithm": "v1"}
    for key in base:
        assert fingerprint(base) != fingerprint({**base, key: "changed"})
    assert fingerprint(base) == fingerprint(dict(reversed(list(base.items()))))


def test_checked_hash_and_resume_output_integrity(tmp_path: Path) -> None:
    required = [
        "virtual-observations.csv",
        "provenance.json",
        "metrics.json",
        "definition.json",
        "admission.json",
        "target.json",
        "anchor.json",
        "correction-model.json",
        "exclusions.json",
    ]
    for name in required:
        write_json(tmp_path / name, {"label": LABEL})
    write_json(
        tmp_path / "completion.json",
        {
            "fingerprint": "input-key",
            "output_sha256": {n: sha256_file(tmp_path / n) for n in required},
        },
    )
    assert read_verified_outputs(tmp_path, "input-key")["label"] == LABEL
    with pytest.raises(Blocked, match="fingerprint changed"):
        read_verified_outputs(tmp_path, "new-key")
    (tmp_path / "virtual-observations.csv").write_text("tampered")
    with pytest.raises(Blocked, match="SHA-256 mismatch"):
        read_verified_outputs(tmp_path, "input-key")
    with pytest.raises(Blocked):
        checked_hash(tmp_path / "missing", "0" * 64)


def test_output_symlink_escape(tmp_path: Path) -> None:
    (tmp_path / "processed").symlink_to(tmp_path / "raw", target_is_directory=True)
    with pytest.raises(Blocked, match="escapes"):
        experiment_dir(tmp_path, definition())


def test_rinex_export_is_explicitly_deferred() -> None:
    assert definition().rinex_output is False
    with pytest.raises(ValueError):
        definition(rinex_output=True)


def test_fixture_label_present() -> None:
    assert "SYNTHETIC TEST DATA" in LABEL
    assert json.loads(json.dumps({"label": LABEL}))["label"] == LABEL
