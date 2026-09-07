from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_single_base.coordinates import (
    EcefCoordinate,
    GeodeticCoordinate,
    baseline_distance_m,
    geodetic_to_ecef,
)
from nlgcp_single_base.io import resolve_data_root, sha256_file
from nlgcp_single_base.models import (
    BLOCKED_MESSAGE,
    ExperimentDefinition,
    NavigationInput,
    Phase2Gate,
    ProcessingMode,
    ScientificExecutionBlocked,
    StationCoordinate,
    StationInput,
)
from nlgcp_single_base.pipeline import prepare_or_run_experiment
from nlgcp_single_base.rtklib import Rnx2RtkpExecution, render_rtklib_config
from nlgcp_single_base.solution import (
    SolutionEpoch,
    SolutionQuality,
    expected_epochs,
    parse_solution_pos,
    quality_from_code,
    residuals_against_control,
    summarise_accuracy_metrics,
    summarise_solution_state_metrics,
    ttff_seconds,
)

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS"


def test_phase2_gate_blocks_unverified_real_execution(tmp_path: Path) -> None:
    obs, nav = _write_inputs(tmp_path)
    definition = _definition(tmp_path, obs, obs, nav, gate=Phase2Gate())

    with pytest.raises(ScientificExecutionBlocked, match=BLOCKED_MESSAGE):
        prepare_or_run_experiment(definition, tmp_path, dry_run=False)

    manifest = tmp_path / "processed" / "single-base" / "EXP-SYNTH-001" / "manifest.json"
    assert manifest.exists()
    text = manifest.read_text(encoding="utf-8")
    assert "blocked" in text
    assert '"baseline_distance_m": null' in text


def test_missing_input_creates_blocked_manifest(tmp_path: Path) -> None:
    obs, nav = _write_inputs(tmp_path)
    missing = tmp_path / "missing.obs"
    definition = _definition(tmp_path, missing, obs, nav, gate=_open_gate(hashes_verified=False))

    with pytest.raises(ScientificExecutionBlocked, match="input file unavailable"):
        prepare_or_run_experiment(definition, tmp_path)

    manifest = tmp_path / "processed" / "single-base" / "EXP-SYNTH-001" / "manifest.json"
    assert "input file unavailable" in manifest.read_text(encoding="utf-8")


def test_checksum_mismatch_blocks(tmp_path: Path) -> None:
    obs, nav = _write_inputs(tmp_path)
    definition = _definition(
        tmp_path,
        obs,
        obs,
        nav,
        gate=_open_gate(),
        base_hash="0" * 64,
        rover_hash=sha256_file(obs),
        nav_hash=sha256_file(nav),
    )

    with pytest.raises(ScientificExecutionBlocked, match="checksum mismatch"):
        prepare_or_run_experiment(definition, tmp_path)


def test_missing_recorded_checksum_when_hashes_verified_blocks(tmp_path: Path) -> None:
    obs, nav = _write_inputs(tmp_path)
    definition = _definition(
        tmp_path,
        obs,
        obs,
        nav,
        gate=_open_gate(),
        base_hash=sha256_file(obs),
        rover_hash=None,
        nav_hash=sha256_file(nav),
    )

    with pytest.raises(ScientificExecutionBlocked, match="recorded checksum missing"):
        prepare_or_run_experiment(definition, tmp_path)


def test_resolve_data_root_requires_configured_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="required"):
        resolve_data_root({})
    with pytest.raises(RuntimeError, match="does not exist"):
        resolve_data_root({"NLGCP_DATA_ROOT": str(tmp_path / "missing")})
    file_path = tmp_path / "file"
    file_path.write_text(SYNTHETIC_LABEL, encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a directory"):
        resolve_data_root({"NLGCP_DATA_ROOT": str(file_path)})
    assert resolve_data_root({"NLGCP_DATA_ROOT": str(tmp_path)}) == tmp_path.resolve()


def test_coordinate_consistency_validation() -> None:
    geodetic = GeodeticCoordinate(9.0, 7.0, 100.0)
    coordinate = StationCoordinate(
        "ITRF2020",
        "2024.0",
        ecef=geodetic_to_ecef(geodetic),
        geodetic=geodetic,
    )
    coordinate.assert_ecef_geodetic_consistent()

    inconsistent = StationCoordinate(
        "ITRF2020",
        "2024.0",
        ecef=EcefCoordinate(1.0, 2.0, 3.0),
        geodetic=geodetic,
    )
    with pytest.raises(ScientificExecutionBlocked, match="consistency"):
        inconsistent.assert_ecef_geodetic_consistent()


def test_generated_rtklib_config_uses_verified_base_coordinate() -> None:
    coordinate = StationCoordinate(
        "ITRF2020",
        "2024.0",
        ecef=EcefCoordinate(111.1, 222.2, 333.3),
    )
    config = render_rtklib_config(ProcessingMode.STATIC, coordinate)

    assert "ant2-postype       =xyz" in config
    assert "ant2-pos1          =111.1000" in config
    assert "out-timeform       =hms" in config
    assert "out-height         =ellipsoidal" in config
    assert "stats-eratio1      =100" in config
    assert "stats-errratio1" not in config
    assert "pos1-navsys        =1" in config


def test_parse_solution_and_supported_metrics(tmp_path: Path) -> None:
    solution = _write_solution(
        tmp_path,
        [
            "2024/01/01 00:00:00.000 9.000000000 7.000000000 100.0000 2 10 0 0 0 0 0 0 0.1 1.0",
            "2024/01/01 00:00:10.000 9.000000100 7.000000100 100.0200 1 11 0 0 0 0 0 0 0.2 3.5",
        ],
    )

    parsed = parse_solution_pos(solution)
    residuals = residuals_against_control(parsed.epochs, GeodeticCoordinate(9.0, 7.0, 100.0))
    state = summarise_solution_state_metrics(
        parsed.epochs,
        start_time_utc="2024-01-01T00:00:00Z",
        end_time_utc="2024-01-01T00:00:10Z",
        sampling_rate_hz=1.0,
    )
    accuracy = summarise_accuracy_metrics(residuals)

    assert len(parsed.epochs) == 2
    assert parsed.epochs[0].age_s == 0.1
    assert parsed.epochs[0].ratio == 1.0
    assert state["fix_rate_solution_epochs"] == 0.5
    assert state["fix_rate_expected_epochs"] == pytest.approx(1 / 11)
    assert state["solution_availability"] == pytest.approx(2 / 11)
    assert state["ttff_seconds"] == 10.0
    assert accuracy["mean_up_m"] is not None
    assert accuracy["up_rmse_m"] is not None
    assert accuracy["horizontal_rmse_m"] is not None
    assert accuracy["three_d_rmse_m"] is not None


def test_parser_reports_malformed_and_structural_mismatch(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.pos"
    malformed.write_text("% bad header\nnot a valid solution row\n", encoding="utf-8")

    with pytest.raises(ScientificExecutionBlocked, match="parse failed"):
        parse_solution_pos(malformed)

    parsed = parse_solution_pos(malformed, strict=False)
    assert parsed.diagnostics.structural_mismatch is not None
    assert parsed.diagnostics.malformed_rows


def test_quality_mapping() -> None:
    assert quality_from_code(0) is SolutionQuality.NO_SOLUTION
    assert quality_from_code(1) is SolutionQuality.FIX
    assert quality_from_code(2) is SolutionQuality.FLOAT
    assert quality_from_code(3) is SolutionQuality.SBAS
    assert quality_from_code(4) is SolutionQuality.DGPS
    assert quality_from_code(5) is SolutionQuality.SINGLE
    assert quality_from_code(6) is SolutionQuality.PPP
    assert quality_from_code(7) is SolutionQuality.DEAD_RECKONING
    assert quality_from_code(99) is SolutionQuality.UNKNOWN


def test_ttff_seconds_cases() -> None:
    first = _epoch("2024-01-01T00:00:00Z", SolutionQuality.FIX)
    assert ttff_seconds([first]) == 0.0

    delayed = [
        _epoch("2024-01-01T00:00:00Z", SolutionQuality.FLOAT),
        _epoch("2024-01-01T00:00:07Z", SolutionQuality.FLOAT),
        _epoch("2024-01-01T00:00:21Z", SolutionQuality.FIX),
    ]
    assert ttff_seconds(delayed) == 21.0

    no_fix = [_epoch("2024-01-01T00:00:00Z", SolutionQuality.FLOAT)]
    assert ttff_seconds(no_fix) is None


def test_expected_epochs_and_availability_with_missing_epochs() -> None:
    assert expected_epochs("2024-01-01T00:00:00Z", "2024-01-01T00:00:03Z", 1.0) == 4
    metrics = summarise_solution_state_metrics(
        [
            _epoch("2024-01-01T00:00:00Z", SolutionQuality.FIX),
            _epoch("2024-01-01T00:00:03Z", SolutionQuality.FLOAT),
        ],
        start_time_utc="2024-01-01T00:00:00Z",
        end_time_utc="2024-01-01T00:00:03Z",
        sampling_rate_hz=1.0,
    )
    assert metrics["solution_epoch_count"] == 2
    assert metrics["expected_epoch_count"] == 4
    assert metrics["solution_availability"] == 0.5

    with pytest.raises(ScientificExecutionBlocked, match="invalid sampling"):
        expected_epochs("2024-01-01T00:00:00Z", "2024-01-01T00:00:03Z", 0)
    with pytest.raises(ScientificExecutionBlocked, match="precedes"):
        expected_epochs("2024-01-01T00:00:03Z", "2024-01-01T00:00:00Z", 1.0)


def test_experiment_collision_detection(tmp_path: Path) -> None:
    obs, nav = _write_inputs(tmp_path)
    definition = _definition(tmp_path, obs, obs, nav, gate=Phase2Gate())

    first = prepare_or_run_experiment(definition, tmp_path, dry_run=True)
    second = prepare_or_run_experiment(definition, tmp_path, dry_run=True)

    assert first["material_input_fingerprint"] == second["material_input_fingerprint"]

    changed = _definition(
        tmp_path,
        obs,
        obs,
        nav,
        gate=Phase2Gate(),
        experiment_id="EXP-SYNTH-001",
        start="2024-01-01T00:00:01Z",
    )
    with pytest.raises(ScientificExecutionBlocked, match="already exists"):
        prepare_or_run_experiment(changed, tmp_path, dry_run=True)


def test_zero_valid_solution_epochs_do_not_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obs, nav = _write_inputs(tmp_path)
    definition = _definition(
        tmp_path,
        obs,
        obs,
        nav,
        gate=_open_gate(),
        base_hash=sha256_file(obs),
        rover_hash=sha256_file(obs),
        nav_hash=sha256_file(nav),
    )

    def fake_run(*args: object, **kwargs: object) -> Rnx2RtkpExecution:
        output_path = args[5]
        stdout_path = args[6]
        stderr_path = args[7]
        assert isinstance(output_path, Path)
        assert isinstance(stdout_path, Path)
        assert isinstance(stderr_path, Path)
        _write_solution(tmp_path, [], path=output_path)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return Rnx2RtkpExecution(["rnx2rtkp"], 0, 0.01, 300.0, stdout_path, stderr_path)

    monkeypatch.setattr("nlgcp_single_base.pipeline.run_rnx2rtkp", fake_run)

    manifest = prepare_or_run_experiment(definition, tmp_path)

    assert manifest["execution_status"] == "failed_no_solution"


def test_baseline_distance_uses_ecef_metres() -> None:
    assert baseline_distance_m(EcefCoordinate(0, 0, 0), EcefCoordinate(3, 4, 12)) == 13.0


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    obs = tmp_path / "station.obs"
    obs.write_text(SYNTHETIC_LABEL + "\nOBS\n", encoding="utf-8")
    nav = tmp_path / "nav.rnx"
    nav.write_text(SYNTHETIC_LABEL + "\nNAV\n", encoding="utf-8")
    return obs, nav


def _write_solution(tmp_path: Path, rows: list[str], path: Path | None = None) -> Path:
    solution = path or tmp_path / "solution.pos"
    solution.write_text(
        "\n".join(
            [
                "% " + SYNTHETIC_LABEL,
                "%  GPST                  latitude(deg) longitude(deg)  height(m)   Q  ns   "
                "sdn(m)   sde(m)   sdu(m)  sdne(m)  sdeu(m)  sdun(m) age(s)  ratio",
                *rows,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return solution


def _open_gate(*, hashes_verified: bool = True) -> Phase2Gate:
    return Phase2Gate(
        base_station_verified=True,
        rover_station_verified=True,
        coordinates_verified=True,
        reference_frame_verified=True,
        coordinate_epoch_verified=True,
        equipment_interval_verified=True,
        real_observations_present=True,
        navigation_present=True,
        overlapping_interval_verified=True,
        sampling_interval_verified=True,
        file_provenance_verified=True,
        hashes_verified=hashes_verified,
        phase2_audit_approved=True,
    )


def _definition(
    tmp_path: Path,
    base_obs: Path,
    rover_obs: Path,
    nav: Path,
    *,
    gate: Phase2Gate,
    base_hash: str | None = None,
    rover_hash: str | None = None,
    nav_hash: str | None = None,
    experiment_id: str = "EXP-SYNTH-001",
    start: str = "2024-01-01T00:00:00Z",
) -> ExperimentDefinition:
    geodetic_base = GeodeticCoordinate(9.0, 7.0, 100.0)
    geodetic_rover = GeodeticCoordinate(9.0, 7.001, 100.0)
    base_coordinate = StationCoordinate(
        reference_frame="ITRF2020",
        coordinate_epoch="2024.0",
        ecef=geodetic_to_ecef(geodetic_base),
        geodetic=geodetic_base,
        provenance="synthetic fixture",
    )
    rover_coordinate = StationCoordinate(
        reference_frame="ITRF2020",
        coordinate_epoch="2024.0",
        ecef=geodetic_to_ecef(geodetic_rover),
        geodetic=geodetic_rover,
        provenance="synthetic fixture",
    )
    return ExperimentDefinition(
        experiment_id=experiment_id,
        research_question="Synthetic dry-run gate check",
        processing_mode=ProcessingMode.STATIC,
        start_time_utc=start,
        end_time_utc="2024-01-01T00:01:00Z",
        sampling_rate_hz=1.0,
        base=StationInput("BASE", base_coordinate, base_obs, "synthetic-metadata", base_hash),
        rover=StationInput("ROVER", rover_coordinate, rover_obs, "synthetic-metadata", rover_hash),
        navigation=[NavigationInput(nav, nav_hash)],
        phase2_gate=gate,
        notes=SYNTHETIC_LABEL + f" in {tmp_path}",
    )


def _epoch(timestamp: str, quality: SolutionQuality) -> SolutionEpoch:
    from nlgcp_single_base.solution import parse_iso_utc

    quality_code = 1 if quality is SolutionQuality.FIX else 2
    return SolutionEpoch(
        epoch=parse_iso_utc(timestamp),
        coordinate=GeodeticCoordinate(9.0, 7.0, 100.0),
        quality_code=quality_code,
        quality=quality,
        satellites=10,
        age_s=None,
        ratio=None,
    )
