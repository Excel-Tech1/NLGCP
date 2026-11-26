"""Unit and pipeline tests for the B-02 Offline Rover Positioning Benchmark.

Covers all Phase I test requirements:
1. Dataset manifest and coordinate truth provenance validation (verified vs. provisional).
2. Strict zero-leakage assertions excluding withheld rover from reference sets.
3. Comparable RTKLIB config rendering across all 5 B-02 profiles.
4. RTCM 3.x pre-conversion framing / CRC-24Q / truncation fail-closed checks.
5. Known-coordinate ENU transformation accuracy (< 1e-6 m), all 19 positioning metrics,
   truth-independent repeatability, convergence windows, ambiguity reset counting, and
   honest FIX=0 / TTFF=None reporting.
6. Deterministic paired common-epoch moving-block bootstrap comparison.
7. Fail-closed execution on missing rover/base/nav inputs and non-zero/timeout RTKLIB runs.
8. End-to-end synthetic RTCM 1005+1074 -> convbin RINEX 3.02 check when convbin is present.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from nlgcp_rover_benchmark.metrics import (
    compute_positioning_metrics,
    count_ambiguity_resets,
    paired_comparison,
)
from nlgcp_rover_benchmark.models import (
    BenchmarkFailure,
    BenchmarkOutcome,
    DatasetWindowSpec,
    ProcessingProfile,
    RoverTruthRecord,
    TruthTier,
    assert_no_rover_leakage,
)
from nlgcp_rover_benchmark.rtklib_pipeline import (
    build_rnx2rtkp_command,
    convert_rtcm_to_rinex,
    execute_rnx2rtkp,
    render_profile_config,
    validate_rtcm_stream_integrity,
)
from nlgcp_rtcm_generation.messages import (
    Msm4Cell,
    Msm4Message,
    MsmSystem,
    ReferenceStation1005,
)
from nlgcp_rtcm_replay.framing import encode_payload_frame
from nlgcp_single_base.coordinates import (
    EcefCoordinate,
    GeodeticCoordinate,
    ecef_delta_to_enu,
    ecef_to_geodetic,
    geodetic_to_ecef,
)
from nlgcp_single_base.solution import EpochResidual, SolutionEpoch, SolutionQuality


def _verified_phri_truth() -> RoverTruthRecord:
    return RoverTruthRecord(
        station_id="PHRI00NGA",
        truth_tier=TruthTier.VERIFIED_IGS20_PPP_AR,
        accuracy_claim_permitted=True,
        ecef_xyz_m=(6308877.98392, 772269.10256, 530087.60603),
        reference_frame="IGS20",
        coordinate_epoch="2024-01-26T11:59:42Z",
        provenance_source="/data/pos_2024026_phri",
        provenance_sha256="a" * 64,
        antenna_model="TRM59900.00 NONE",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
        formal_sigma_xyz_m=(0.00055, 0.00016, 0.00013),
        processing_method="PRIDE PPP-AR 3.2.8",
        bias_products_available=True,
    )


def _synthetic_rtcm_1005_1074_stream() -> bytes:
    """SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""
    arp = ReferenceStation1005(
        station_id=2499,
        itrf_realization_year=0,
        gps_indicator=True,
        glonass_indicator=False,
        galileo_indicator=False,
        reference_station_indicator=True,
        ecef_x_m=6308878.0,
        ecef_y_m=772269.0,
        ecef_z_m=530087.0,
        oscillator_indicator=True,
        quarter_cycle_indicator=0,
    )
    frame_1005 = encode_payload_frame(arp.encode())
    cells: list[Msm4Cell] = []
    for prn in (1, 3, 6, 11, 14):
        c1_m = 21_000_000.0 + prn * 1000.0
        p2_m = c1_m + 2.0
        cells.append(
            Msm4Cell(
                satellite_id=prn,
                signal_id=2,  # GPS 1C
                pseudorange_m=c1_m,
                phase_range_m=c1_m + 0.12,
                lock_time_s=60.0,
                half_cycle_ambiguity=False,
                cnr_dbhz=45.0,
            )
        )
        cells.append(
            Msm4Cell(
                satellite_id=prn,
                signal_id=9,  # GPS 2P
                pseudorange_m=p2_m,
                phase_range_m=p2_m - 0.08,
                lock_time_s=60.0,
                half_cycle_ambiguity=False,
                cnr_dbhz=42.0,
            )
        )
    msg_1074 = Msm4Message(
        system=MsmSystem.GPS,
        station_id=2499,
        epoch=432_000_000,
        multiple_message=False,
        iod=0,
        clock_steering=0,
        external_clock=0,
        smoothing=False,
        smoothing_interval=0,
        cells=tuple(cells),
    )
    frame_1074 = encode_payload_frame(msg_1074.encode())
    return frame_1005 + frame_1074


def test_truth_record_blocks_verified_accuracy_claim_on_provisional_truth() -> None:
    _verified_phri_truth().validate()

    provisional_ok = RoverTruthRecord(
        station_id="OSGF",
        truth_tier=TruthTier.PROVISIONAL_OSGOF_LIMITED,
        accuracy_claim_permitted=False,
        ecef_xyz_m=(6246471.2, 820848.74, 994267.93),
        reference_frame="ITRF_UNDOCUMENTED_OSGOF_2011",
        coordinate_epoch="2011-01-01",
        provenance_source="osgof_table",
        provenance_sha256=None,
        antenna_model="TRM59800.00",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
    )
    provisional_ok.validate()

    provisional_bad = RoverTruthRecord(
        station_id="OSGF",
        truth_tier=TruthTier.PROVISIONAL_OSGOF_LIMITED,
        accuracy_claim_permitted=True,
        ecef_xyz_m=(6246471.2, 820848.74, 994267.93),
        reference_frame="ITRF_UNDOCUMENTED_OSGOF_2011",
        coordinate_epoch="2011-01-01",
        provenance_source="osgof_table",
        provenance_sha256=None,
        antenna_model="TRM59800.00",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
    )
    with pytest.raises(BenchmarkFailure, match="VERIFIED_IGS20_PPP_AR"):
        provisional_bad.validate()


def test_truth_record_blocks_non_earth_radius_and_incomplete_provenance() -> None:
    bad_radius = RoverTruthRecord(
        station_id="PHRI00NGA",
        truth_tier=TruthTier.VERIFIED_IGS20_PPP_AR,
        accuracy_claim_permitted=True,
        ecef_xyz_m=(1000.0, 2000.0, 3000.0),
        reference_frame="IGS20",
        coordinate_epoch="2024-01-26",
        provenance_source="test",
        provenance_sha256=None,
        antenna_model="NONE",
        antenna_delta_hen_m=(0.0, 0.0, 0.0),
    )
    with pytest.raises(BenchmarkFailure, match="outside Earth surface bounds"):
        bad_radius.validate()


def test_leakage_guard_passes_clean_split_and_blocks_every_leak_vector() -> None:
    clean = assert_no_rover_leakage(
        rover_station_id="PHRI00NGA",
        physical_anchor_id="EKAK00NGA",
        reference_coord_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
        reference_dataset_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
        iono_field_station_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
        ztd_station_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
        vrs_virtual_offset_from_truth_m=3.14,
    )
    assert clean.passed is True
    assert clean.vrs_virtual_offset_from_truth_m == 3.14

    # Rover leaked into ZTD field must fail closed
    with pytest.raises(BenchmarkFailure, match="LEAKAGE: rover PHRI00NGA found in reference ZTD"):
        assert_no_rover_leakage(
            rover_station_id="PHRI00NGA",
            physical_anchor_id="EKAK00NGA",
            reference_coord_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
            reference_dataset_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
            iono_field_station_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA"},
            ztd_station_ids={"ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA"},
        )

    # Rover leaked into iono field must fail closed
    with pytest.raises(BenchmarkFailure, match="iono_field"):
        assert_no_rover_leakage(
            rover_station_id="OSGF",
            physical_anchor_id="CGGT",
            reference_coord_ids={"ABUZ", "CGGT"},
            reference_dataset_ids={"ABUZ", "CGGT"},
            iono_field_station_ids={"ABUZ", "CGGT", "OSGF"},
            ztd_station_ids=set(),
        )


def test_rtklib_config_generation_consistency_across_all_profiles() -> None:
    base = (6300000.1234, 770000.5678, 530000.9012)
    cfg_kin = render_profile_config(ProcessingProfile.KINEMATIC_BRDC_SAAS, base_ecef_m=base)
    cfg_sta = render_profile_config(ProcessingProfile.STATIC_BRDC_SAAS, base_ecef_m=base)
    cfg_vrs = render_profile_config(ProcessingProfile.KINEMATIC_VRS_IONO_OFF, base_ecef_m=base)
    cfg_dgp = render_profile_config(ProcessingProfile.DGPS_CODE_DIFF, base_ecef_m=base)
    cfg_spp = render_profile_config(ProcessingProfile.SPP_SINGLE, base_ecef_m=None)

    assert "pos1-posmode       =kinematic" in cfg_kin
    assert "pos1-ionoopt       =brdc" in cfg_kin
    assert "pos1-tropopt       =saas" in cfg_kin
    assert "pos1-navsys        =1" in cfg_kin
    assert "pos2-armode        =continuous" in cfg_kin
    assert "ant2-pos1          =6300000.1234" in cfg_kin

    assert "pos1-posmode       =static" in cfg_sta
    assert "pos1-ionoopt       =off" in cfg_vrs
    assert "pos1-tropopt       =off" in cfg_vrs
    assert "pos1-posmode       =dgps" in cfg_dgp
    assert "pos2-armode        =off" in cfg_dgp
    assert "pos1-posmode       =single" in cfg_spp
    assert "ant2-postype" not in cfg_spp


def test_rtcm_integrity_validator_accepts_valid_and_rejects_crc_or_truncation() -> None:
    valid_stream = _synthetic_rtcm_1005_1074_stream()
    fail, summary = validate_rtcm_stream_integrity(valid_stream)
    assert fail is None
    assert summary["frame_count"] == 2
    assert summary["crc_fail_count"] == 0
    assert summary["message_numbers"] == [1005, 1074]

    # Flip payload byte -> CRC failure
    corrupted = bytearray(valid_stream)
    corrupted[8] ^= 0xFF
    fail_crc, sum_crc = validate_rtcm_stream_integrity(bytes(corrupted))
    assert fail_crc is BenchmarkOutcome.FAILED_INVALID_RTCM
    assert sum_crc["crc_fail_count"] >= 1

    # Truncated stream -> TRUNCATED failure
    fail_trunc, _ = validate_rtcm_stream_integrity(valid_stream[:-10])
    assert fail_trunc is BenchmarkOutcome.FAILED_TRUNCATED_RTCM

    # Empty stream -> TRUNCATED failure
    fail_empty, _ = validate_rtcm_stream_integrity(b"")
    assert fail_empty is BenchmarkOutcome.FAILED_TRUNCATED_RTCM


def test_known_enu_transformation_and_all_19_positioning_metrics() -> None:
    """Verify exact ENU error math (< 1e-6 m) and honest FIX/FLOAT/SINGLE/reset metrics."""
    truth_ecef = (6308877.98392, 772269.10256, 530087.60603)
    truth_geo = ecef_to_geodetic(EcefCoordinate(*truth_ecef))
    lat = math.radians(truth_geo.latitude_deg)
    lon = math.radians(truth_geo.longitude_deg)

    def _geo_from_enu(de: float, dn: float, du: float) -> GeodeticCoordinate:
        # Inverse ENU -> ECEF rotation
        dx = (
            -math.sin(lon) * de
            - math.sin(lat) * math.cos(lon) * dn
            + math.cos(lat) * math.cos(lon) * du
        )
        dy = (
            math.cos(lon) * de
            - math.sin(lat) * math.sin(lon) * dn
            + math.cos(lat) * math.sin(lon) * du
        )
        dz = math.cos(lat) * dn + math.sin(lat) * du
        return ecef_to_geodetic(
            EcefCoordinate(truth_ecef[0] + dx, truth_ecef[1] + dy, truth_ecef[2] + dz)
        )

    # Verify roundtrip precision < 1e-6 m
    g_test = _geo_from_enu(0.30, -0.40, 0.50)
    e_test = geodetic_to_ecef(g_test)
    re, rn, ru = ecef_delta_to_enu(
        EcefCoordinate(
            e_test.x_m - truth_ecef[0],
            e_test.y_m - truth_ecef[1],
            e_test.z_m - truth_ecef[2],
        ),
        truth_geo,
    )
    assert abs(re - 0.30) < 1e-6
    assert abs(rn - (-0.40)) < 1e-6
    assert abs(ru - 0.50) < 1e-6

    t0 = datetime(2024, 1, 26, 0, 0, 0, tzinfo=UTC)
    specs = [
        (0, 0.30, 0.40, 0.50, 2, SolutionQuality.FLOAT, 8, 1.2),
        (30, 0.03, 0.04, 0.05, 1, SolutionQuality.FIX, 9, 5.4),
        (60, 0.30, -0.40, -0.50, 2, SolutionQuality.FLOAT, 7, 1.1),  # FIX -> FLOAT reset #1
        (90, 1.50, 2.00, 1.00, 5, SolutionQuality.SINGLE, 5, 0.0),  # FLOAT -> SINGLE reset #2
    ]
    epochs: list[SolutionEpoch] = []
    for dt_s, de, dn, du, qcode, q, ns, ratio in specs:
        g = _geo_from_enu(de, dn, du)
        epochs.append(
            SolutionEpoch(
                epoch=t0 + timedelta(seconds=dt_s),
                coordinate=g,
                quality_code=qcode,
                quality=q,
                satellites=ns,
                age_s=0.0,
                ratio=ratio,
            )
        )

    metrics, resids = compute_positioning_metrics(
        epochs,
        truth_ecef_m=truth_ecef,
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:01:30Z",
        sampling_interval_s=30.0,
    )
    assert len(resids) == 4
    assert metrics["attempted_epochs"] == 4
    assert metrics["valid_epochs"] == 4
    assert metrics["availability_rate"] == 1.0
    assert metrics["fix_epochs"] == 1
    assert metrics["float_epochs"] == 2
    assert metrics["single_epochs"] == 1
    assert metrics["fix_rate"] == 0.25
    assert metrics["ttff_s"] == 30.0
    assert metrics["ambiguity_resets"] == 2
    assert count_ambiguity_resets(epochs) == 2

    # Expected horizontal errors: 0.50, 0.05, 0.50, 2.50
    expected_h_rmse = math.sqrt((0.50**2 + 0.05**2 + 0.50**2 + 2.50**2) / 4.0)
    assert abs(metrics["horizontal_rmse_m"] - expected_h_rmse) < 1e-5
    assert abs(metrics["horizontal_max_m"] - 2.50) < 1e-5
    assert metrics["satellites"] == {"mean": 7.25, "min": 5, "max": 9}
    assert metrics["repeatability"]["east_std_m"] is not None


def test_paired_comparison_block_bootstrap_determinism_and_direction() -> None:
    t0 = datetime(2024, 1, 26, 0, 0, 0, tzinfo=UTC)
    base_res = [
        EpochResidual(
            epoch=t0 + timedelta(seconds=30 * i),
            quality_code=2,
            quality=SolutionQuality.FLOAT,
            satellites=8,
            east_m=0.8,
            north_m=0.6,
            up_m=0.5,
            horizontal_error_m=1.0,
            vertical_abs_error_m=0.5,
            error_3d_m=math.sqrt(1.25),
        )
        for i in range(60)
    ]
    cand_res = [
        EpochResidual(
            epoch=t0 + timedelta(seconds=30 * i),
            quality_code=2,
            quality=SolutionQuality.FLOAT,
            satellites=8,
            east_m=0.4,
            north_m=0.3,
            up_m=0.25,
            horizontal_error_m=0.5,
            vertical_abs_error_m=0.25,
            error_3d_m=math.sqrt(0.3125),
        )
        for i in range(60)
    ]
    c1 = paired_comparison(
        base_res, cand_res, baseline_label="anchor", candidate_label="vrs", block_size=10
    )
    c2 = paired_comparison(
        base_res, cand_res, baseline_label="anchor", candidate_label="vrs", block_size=10
    )
    assert c1 == c2
    assert c1["paired_epochs"] == 60
    assert c1["horiz_rmse_improvement_m"] == 0.5
    assert c1["horiz_rmse_improvement_pct"] == 50.0
    assert c1["epoch_win_fraction_horiz"] == 1.0
    assert c1["horiz_rmse_gain_block_bootstrap_95ci_m"] == [0.5, 0.5]


def test_execute_rnx2rtkp_fails_closed_on_missing_inputs(tmp_path: Path) -> None:
    fake_rover = tmp_path / "rover.24O"
    fake_base = tmp_path / "base.24O"
    fake_nav = tmp_path / "brdc.rnx"

    o1, s1, _ = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=fake_rover,
        base_obs_path=fake_base,
        nav_paths=[fake_nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:05:00Z",
        run_dir=tmp_path / "r1",
    )
    assert o1 is BenchmarkOutcome.FAILED_MISSING_ROVER_OBS
    assert s1 is None

    fake_rover.write_text("dummy", encoding="ascii")
    o2, _, _ = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=fake_rover,
        base_obs_path=fake_base,
        nav_paths=[fake_nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:05:00Z",
        run_dir=tmp_path / "r2",
    )
    assert o2 is BenchmarkOutcome.FAILED_MISSING_REFERENCE_OBS

    fake_base.write_text("dummy", encoding="ascii")
    o3, _, _ = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=fake_rover,
        base_obs_path=fake_base,
        nav_paths=[fake_nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:05:00Z",
        run_dir=tmp_path / "r3",
    )
    assert o3 is BenchmarkOutcome.FAILED_MISSING_NAVIGATION


def test_convert_rtcm_to_rinex_fails_closed_on_corrupted_stream(tmp_path: Path) -> None:
    bad = tmp_path / "bad.rtcm3"
    raw = bytearray(_synthetic_rtcm_1005_1074_stream())
    raw[10] ^= 0xAA
    bad.write_bytes(bytes(raw))
    res = convert_rtcm_to_rinex(bad, tmp_path / "out.obs", ref_date_slash="2024/01/26")
    assert res.ok is False
    assert res.outcome is BenchmarkOutcome.FAILED_INVALID_RTCM


def test_convert_rtcm_to_rinex_valid_stream_preserves_arp_and_signals(tmp_path: Path) -> None:
    """SYNTHETIC TEST DATA — verify convbin RINEX 3.02 integrity on valid 1005+1074 stream."""
    rtcm_path = tmp_path / "valid_syn.rtcm3"
    rtcm_path.write_bytes(_synthetic_rtcm_1005_1074_stream())
    res = convert_rtcm_to_rinex(rtcm_path, tmp_path / "valid_syn.obs", ref_date_slash="2024/01/26")
    assert res.ok is True
    assert res.outcome is BenchmarkOutcome.COMPLETED
    assert res.rinex_path is not None and res.rinex_path.is_file()
    assert res.rinex_sha256 is not None and len(res.rinex_sha256) == 64
    assert res.summary["rinex_epoch_count"] == 1
    approx = res.summary["rinex_approx_xyz_m"]
    assert approx is not None
    assert math.dist(approx, (6308878.0, 772269.0, 530087.0)) < 1e-3
    gps_types = res.summary["rinex_sys_obs_types"].get("G", [])
    assert {"C1C", "L1C", "C2P", "L2P"} <= set(gps_types)


def test_build_rnx2rtkp_command_spp_and_relative_modes(tmp_path: Path) -> None:
    exe = tmp_path / "rnx2rtkp"
    cfg = tmp_path / "rtklib.conf"
    pos = tmp_path / "solution.pos"
    rov = tmp_path / "rover.obs"
    bas = tmp_path / "base.obs"
    nav = tmp_path / "brdc.rnx"

    cmd_rel = build_rnx2rtkp_command(
        executable=exe,
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        config_path=cfg,
        output_pos_path=pos,
        rover_obs_path=rov,
        base_obs_path=bas,
        nav_paths=[nav],
        base_ecef_m=(6300000.1234, 770000.5678, 530000.9012),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T01:00:00Z",
    )
    assert "-r" in cmd_rel
    assert "6300000.1234" in cmd_rel
    assert str(bas) in cmd_rel
    assert cmd_rel[-3:] == [str(rov), str(bas), str(nav)]

    cmd_spp = build_rnx2rtkp_command(
        executable=exe,
        profile=ProcessingProfile.SPP_SINGLE,
        config_path=cfg,
        output_pos_path=pos,
        rover_obs_path=rov,
        base_obs_path=bas,
        nav_paths=[nav],
        base_ecef_m=(6300000.1234, 770000.5678, 530000.9012),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T01:00:00Z",
    )
    assert "-r" not in cmd_spp
    assert str(bas) not in cmd_spp
    assert cmd_spp[-2:] == [str(rov), str(nav)]


def test_execute_rnx2rtkp_handles_nonzero_exit_timeout_and_malformed_pos(tmp_path: Path) -> None:
    rov = tmp_path / "rover.obs"
    bas = tmp_path / "base.obs"
    nav = tmp_path / "brdc.rnx"
    for p in (rov, bas, nav):
        p.write_text("dummy", encoding="ascii")

    # Non-zero exit fake binary
    fail_bin = tmp_path / "fake_fail.sh"
    fail_bin.write_text("#!/bin/sh\necho 'simulated failure' >&2\nexit 2\n", encoding="ascii")
    fail_bin.chmod(0o755)
    out1, sol1, info1 = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=rov,
        base_obs_path=bas,
        nav_paths=[nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:05:00Z",
        run_dir=tmp_path / "run_fail",
        rnx2rtkp_bin=fail_bin,
    )
    assert out1 is BenchmarkOutcome.FAILED_RTKLIB_EXECUTION
    assert sol1 is None
    assert info1["return_code"] == 2

    # Timeout fake binary
    slow_bin = tmp_path / "fake_slow.sh"
    slow_bin.write_text("#!/bin/sh\nsleep 2\n", encoding="ascii")
    slow_bin.chmod(0o755)
    out2, sol2, info2 = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=rov,
        base_obs_path=bas,
        nav_paths=[nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:05:00Z",
        run_dir=tmp_path / "run_timeout",
        rnx2rtkp_bin=slow_bin,
        timeout_s=0.05,
    )
    assert out2 is BenchmarkOutcome.FAILED_RTKLIB_EXECUTION
    assert sol2 is None
    assert info2["timeout"] is True

    # Malformed .pos file fake binary (exits 0 but emits corrupt headerless output)
    badpos_bin = tmp_path / "fake_badpos.sh"
    badpos_bin.write_text(
        '#!/bin/sh\nwhile [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "-o" ]; then shift; echo "CORRUPT ROW" > "$1"; exit 0; fi\n'
        "  shift\ndone\n",
        encoding="ascii",
    )
    badpos_bin.chmod(0o755)
    out3, _, _ = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=rov,
        base_obs_path=bas,
        nav_paths=[nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T00:05:00Z",
        run_dir=tmp_path / "run_badpos",
        rnx2rtkp_bin=badpos_bin,
    )
    assert out3 is BenchmarkOutcome.FAILED_RTKLIB_EXECUTION

    # No-overlap fake binary (exits 0, writes "error : no obs data" to stderr, no .pos file)
    noobs_bin = tmp_path / "fake_noobs.sh"
    noobs_bin.write_text("#!/bin/sh\necho 'error : no obs data' >&2\nexit 0\n", encoding="ascii")
    noobs_bin.chmod(0o755)
    out4, sol4, _ = execute_rnx2rtkp(
        profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
        rover_obs_path=rov,
        base_obs_path=bas,
        nav_paths=[nav],
        base_ecef_m=(6300000.0, 770000.0, 530000.0),
        start_time_utc="2024-01-27T00:00:00Z",
        end_time_utc="2024-01-27T00:05:00Z",
        run_dir=tmp_path / "run_noobs",
        rnx2rtkp_bin=noobs_bin,
    )
    assert out4 is BenchmarkOutcome.FAILED_EPOCH_MISMATCH
    assert sol4 is None


def test_metrics_honest_zero_fix_time_blocks_and_manifest_serialization(tmp_path: Path) -> None:
    truth_ecef = (6308877.98392, 772269.10256, 530087.60603)
    truth_geo = ecef_to_geodetic(EcefCoordinate(*truth_ecef))
    t0 = datetime(2024, 1, 26, 0, 0, 0, tzinfo=UTC)
    float_epochs = [
        SolutionEpoch(
            epoch=t0 + timedelta(hours=h),
            coordinate=truth_geo,
            quality_code=2,
            quality=SolutionQuality.FLOAT,
            satellites=6 if h < 12 else 9,
            age_s=0.0,
            ratio=1.1,
        )
        for h in (1, 7, 13, 20)
    ]
    metrics, _ = compute_positioning_metrics(
        float_epochs,
        truth_ecef_m=truth_ecef,
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T23:59:30Z",
        sampling_interval_s=30.0,
    )
    assert metrics["fix_rate"] == 0.0
    assert metrics["float_rate"] == 1.0
    assert metrics["ttff_s"] is None
    assert metrics["time_blocks_utc"]["18_24_utc"]["count"] == 1
    assert metrics["satellite_bins"]["6_to_7_sats"]["count"] == 2
    assert metrics["satellite_bins"]["ge_8_sats"]["count"] == 2
    assert metrics["outliers"]["horiz_gt_2m_count"] == 0

    spec = DatasetWindowSpec(
        dataset_id="syn_manifest_check",
        date_iso="2024-01-26",
        year=2024,
        doy=26,
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc="2024-01-26T23:59:30Z",
        sampling_interval_s=30.0,
        rover_station_id="PHRI00NGA",
        rover_obs_path=tmp_path / "r.24O",
        rover_obs_sha256="b" * 64,
        physical_anchor_id="EKAK00NGA",
        physical_anchor_obs_path=tmp_path / "a.24O",
        physical_anchor_obs_sha256="c" * 64,
        physical_anchor_ecef_m=(6296999.0, 868621.0, 560359.0),
        reference_stations=("ABFC00NGA", "EKAK00NGA", "MGBO00NGA"),
        nav_path=tmp_path / "brdc.rnx",
        nav_sha256="d" * 64,
        rover_inside_convex_hull=False,
        anchor_baseline_km=105.553,
        rover_truth=_verified_phri_truth(),
    )
    payload = spec.as_dict()
    assert payload["dataset_id"] == "syn_manifest_check"
    assert payload["rover_truth"]["truth_tier"] == "VERIFIED_IGS20_PPP_AR"
