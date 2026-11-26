"""Unit and integration tests for Phase 7 Experimental VRS, RTCM bridge, and NTRIP isolation.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
Verifies physically signed dispersion synthesis, all fail-closed quality gates,
RTCM 1005/1074 encoding with exact integer-cycle arc alignment, independent
decoding (RTKLIB + ESA/gAGE-UPC gLAB v6.0.0 when installed), isolated
NLGCP_VRS_EXP loopback NTRIP streaming, and strict operational separation.
"""

from __future__ import annotations

import hashlib
import math
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from nlgcp_atmospheric_model.combinations import GAMMA_GPS
from nlgcp_atmospheric_model.constants import EARTH_ROT_RATE_RAD_S, SPEED_OF_LIGHT_M_S
from nlgcp_atmospheric_model.observations import (
    GPS_L1_WAVELENGTH_M,
    GPS_L2_WAVELENGTH_M,
    Rinex2Header,
    SatObs,
    StationDataset,
)
from nlgcp_atmospheric_model.satellite_geometry import (
    BroadcastEphemeris,
    broadcast_position,
    gps_datetime_to_tow,
)
from nlgcp_correction_service import (
    DEFAULT_MOUNTPOINT,
    EXPERIMENTAL_VRS_MOUNTPOINT,
    LOOPBACK_HOST,
)
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.client import LocalNtripClient
from nlgcp_correction_service.config import CasterConfig, ClientConfig
from nlgcp_correction_service.mountpoints import (
    MountpointDefinition,
    MountpointError,
    MountpointRegistry,
    experimental_vrs_mountpoint,
)
from nlgcp_correction_service.publisher import PublicationError
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy
from nlgcp_rtcm_generation.independent_decoder import (
    GLAB_DEFAULT_SOURCE,
    IndependentDecoderUnavailable,
    build_glab_rtcm1005_decoder,
    build_rtklib_decoder,
    decode_rtcm1005_with_glab,
    decode_with_convbin,
    decode_with_rtklib_native,
)
from nlgcp_rtcm_generation.models import GeneratedCorrectionFrame, OutputClassification
from nlgcp_vrs.experimental_vrs import (
    VrsMaturity,
    VrsOutcome,
    generate_experimental_vrs,
    geodetic_to_ecef,
    validate_experimental_vrs_against_target,
    validate_vrs_coordinate,
)
from nlgcp_vrs.models import correction_gate
from nlgcp_vrs.rtcm_bridge import (
    VrsRtcmBridgeError,
    encode_experimental_vrs_to_rtcm,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_eph(sat: str, week: int, toe: float, m0: float, omega0: float) -> BroadcastEphemeris:
    return BroadcastEphemeris(
        satellite_id=sat,
        toc_week=week,
        toc_tow_s=toe,
        af0_s=1.2e-5,
        af1_s_s=1.0e-12,
        af2_s_s2=0.0,
        iode=1.0,
        crs_m=0.0,
        delta_n_rad_s=0.0,
        m0_rad=m0,
        cuc_rad=0.0,
        e=0.005,
        cus_rad=0.0,
        sqrt_a_m_sqrt=5153.6,
        toe_tow_s=toe,
        toe_week=week,
        cic_rad=0.0,
        omega0_rad=omega0,
        cis_rad=0.0,
        i0_rad=math.radians(55.0),
        crc_m=0.0,
        omega_rad=0.5,
        omega_dot_rad_s=-8.0e-9,
        idot_rad_s=0.0,
        health=0,
    )


def _geom_range(
    eph: BroadcastEphemeris, week: int, tow: float, rx_xyz: tuple[float, float, float]
) -> float:
    tau = 0.072
    for _ in range(3):
        sp = broadcast_position(eph, week, tow - tau)
        ang = EARTH_ROT_RATE_RAD_S * tau
        sx = math.cos(ang) * sp[0] + math.sin(ang) * sp[1]
        sy = -math.sin(ang) * sp[0] + math.cos(ang) * sp[1]
        rng = math.dist(rx_xyz, (sx, sy, sp[2]))
        tau = rng / SPEED_OF_LIGHT_M_S
    return rng


def _synthetic_vrs_scenario() -> dict[str, object]:
    """Build a 4-reference + 1-interior-target physically consistent synthetic GPS scenario."""
    ref_coords = {
        "REF1": geodetic_to_ecef(11.0, 5.0, 350.0),
        "REF2": geodetic_to_ecef(11.0, 10.0, 350.0),
        "REF3": geodetic_to_ecef(6.0, 10.0, 350.0),
        "REF4": geodetic_to_ecef(6.0, 5.0, 350.0),
    }
    target_coord = geodetic_to_ecef(8.5, 7.5, 420.0)
    base_dt = datetime(2024, 1, 26, 12, 0, 0, tzinfo=UTC)
    week, base_tow = gps_datetime_to_tow(base_dt)

    # Pick 4 GPS satellites high overhead Nigeria at 2024-01-26 12:00 UTC
    nav: dict[str, list[BroadcastEphemeris]] = {
        "G01": [_make_eph("G01", week, base_tow, 0.2, 0.3)],
        "G02": [_make_eph("G02", week, base_tow, 0.7, 0.5)],
        "G03": [_make_eph("G03", week, base_tow, -0.3, 0.9)],
        "G04": [_make_eph("G04", week, base_tow, 0.5, -0.2)],
    }
    # Ensure at least 2 satellites are above 15 deg elevation; adjust m0/omega0 deterministically
    from nlgcp_atmospheric_model.satellite_geometry import elevation_azimuth_deg

    good_nav: dict[str, list[BroadcastEphemeris]] = {}
    sat_idx = 1
    for m0_deg in range(0, 360, 30):
        for om_deg in range(0, 360, 45):
            cand = _make_eph(
                f"G{sat_idx:02d}", week, base_tow, math.radians(m0_deg), math.radians(om_deg)
            )
            sp = broadcast_position(cand, week, base_tow)
            el, _ = elevation_azimuth_deg(target_coord, sp)
            if el > 35.0:
                good_nav[f"G{sat_idx:02d}"] = [cand]
                sat_idx += 1
                break
        if len(good_nav) >= 4:
            break
    nav = good_nav

    epochs = [f"2024-01-26T12:0{i}:00.000000" for i in range(4)]
    all_coords = {**ref_coords, "TGT": target_coord}
    # Synthetic linear ionospheric L1 delay (m) by latitude
    iono_by_st = {"REF1": 3.2, "REF2": 3.4, "REF3": 2.4, "REF4": 2.2, "TGT": 2.8}

    datasets: dict[str, StationDataset] = {}
    iono_field: dict[tuple[str, str, str], float] = {}
    for st, xyz in all_coords.items():
        data: dict[str, dict[str, SatObs]] = {}
        for idx, ep in enumerate(epochs):
            tow = base_tow + 60.0 * idx
            smap: dict[str, SatObs] = {}
            for sat, ephs in nav.items():
                rho = _geom_range(ephs[0], week, tow, xyz)
                i1 = iono_by_st[st]
                # Large realistic RINEX carrier-phase offset (~10^7 cycles) to exercise arc rebase
                n1_init = 8_000_000.0 if st == "REF1" else 5_000_000.0
                n2_init = 6_000_000.0
                c1 = rho + i1
                p2 = rho + GAMMA_GPS * i1
                l1 = (rho - i1) / GPS_L1_WAVELENGTH_M + n1_init
                l2 = (rho - GAMMA_GPS * i1) / GPS_L2_WAVELENGTH_M + n2_init
                smap[sat] = SatObs(
                    values={"C1": c1, "P2": p2, "L1": l1, "L2": l2, "S1": 45.0, "S2": 41.0}
                )
                if st != "TGT":
                    iono_field[(ep, sat, st)] = i1
            data[ep] = smap
        datasets[st] = StationDataset(
            station_id=st,
            header=Rinex2Header(
                path=f"synthetic://{st}",
                obs_types=("C1", "P2", "L1", "L2", "S1", "S2"),
                interval_s=60.0,
                time_of_first_obs=epochs[0],
                approx_xyz_m=xyz,
            ),
            epochs=epochs,
            data=data,
        )
    return {
        "ref_coords": ref_coords,
        "ref_datasets": {k: datasets[k] for k in ref_coords},
        "target_coord": target_coord,
        "target_dataset": datasets["TGT"],
        "nav": nav,
        "iono_field": iono_field,
    }


def test_operational_phase7_gate_remains_strictly_intact() -> None:
    gate = correction_gate(
        {
            "status": "COMPLETE",
            "loocv": {
                "comparison_keys": 100,
                "best_model": "idw",
                "models": {
                    "zero": {"rmse_m": 1.0, "count": 100},
                    "nearest": {"rmse_m": 0.9, "count": 100},
                    "idw": {"rmse_m": 0.8, "count": 100},
                    "planar": {"rmse_m": 1.2, "count": 100},
                },
            },
        }
    )
    assert gate["mode"] == "VRS_GEOMETRY_ONLY"
    assert gate["spatial_correction"] == "ZERO"
    assert gate["automatic_correction_approved"] is False


def test_coordinate_validation_and_roundtrip() -> None:
    xyz = geodetic_to_ecef(9.0277, 7.49, 532.63)
    rec, err = validate_vrs_coordinate(
        station_id="OSGF",
        ecef_xyz_m=xyz,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        provenance_status="VERIFIED_IGS20",
    )
    assert err is None and rec is not None
    assert rec.roundtrip_error_m < 1e-4

    bad_rec, bad_err = validate_vrs_coordinate(
        station_id="BAD",
        ecef_xyz_m=(100.0, 200.0, 300.0),
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        provenance_status="VERIFIED_IGS20",
    )
    assert bad_rec is None and bad_err is not None


def test_experimental_vrs_dispersion_signs_and_held_out_validation() -> None:
    sc = _synthetic_vrs_scenario()
    ref_coords = sc["ref_coords"]
    ref_datasets = sc["ref_datasets"]
    target_coord = sc["target_coord"]
    target_dataset = sc["target_dataset"]
    nav = sc["nav"]
    iono_field = sc["iono_field"]
    assert isinstance(ref_coords, dict)
    assert isinstance(ref_datasets, dict)
    assert isinstance(target_coord, tuple)
    assert isinstance(target_dataset, StationDataset)
    assert isinstance(nav, dict)
    assert isinstance(iono_field, dict)

    vrs_zero = generate_experimental_vrs(
        experiment_id="unit-zero",
        target_station_id="TGT",
        target_ecef_m=target_coord,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC_UNIT_TEST",
        spatial_model="zero",
        tropo_mode="zero",
        require_interior_hull=True,
    )
    vrs_atmo = generate_experimental_vrs(
        experiment_id="unit-idw2",
        target_station_id="TGT",
        target_ecef_m=target_coord,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC_UNIT_TEST",
        spatial_model="idw2",
        iono_field_by_key=iono_field,
        tropo_mode="zero",
        require_interior_hull=True,
    )
    assert vrs_zero.outcome == VrsOutcome.EXPERIMENTAL_VRS_GENERATED
    assert vrs_zero.maturity == VrsMaturity.GEOMETRY_ONLY_VRS
    assert vrs_atmo.outcome == VrsOutcome.EXPERIMENTAL_VRS_GENERATED
    assert vrs_atmo.maturity == VrsMaturity.EXPERIMENTAL_OBSERVATION_VRS
    assert vrs_atmo.operational_approved is False
    assert vrs_atmo.inside_convex_hull is True

    # Verify opposite ionospheric dispersion sign between code (+I) and phase (-I)
    o0 = vrs_zero.observations[0]
    o1 = vrs_atmo.observations[0]
    di1 = o1.iono_l1_correction_m
    assert abs(di1) > 0.1
    assert (o1.c1_m - o0.c1_m) == pytest.approx(di1, abs=1e-6)
    assert (o1.p2_m - o0.p2_m) == pytest.approx(GAMMA_GPS * di1, abs=1e-6)
    assert (o1.l1_cycles - o0.l1_cycles) * GPS_L1_WAVELENGTH_M == pytest.approx(-di1, abs=1e-6)
    assert (o1.l2_cycles - o0.l2_cycles) * GPS_L2_WAVELENGTH_M == pytest.approx(
        -GAMMA_GPS * di1, abs=1e-6
    )

    val = validate_experimental_vrs_against_target(
        vrs_atmo, target_dataset, effective_interval_s=60.0
    )
    assert val["status"] == "COMPLETE"
    assert val["metrics_by_code"]["C1"]["rmse_m"] < 0.05

    # Regression: spatial_model="zero" with tropo_mode="network_ztd" must interpolate ZWD via idw2
    # rather than zeroing target ZWD against a non-zero anchor ZWD.
    ref_epochs = next(iter(ref_datasets.values())).epochs
    uniform_ztd = {(st, ep): (2.30, 0.20) for st in ref_coords for ep in ref_epochs}
    vrs_tropo_ztd = generate_experimental_vrs(
        experiment_id="unit-zero-iono-network-ztd",
        target_station_id="TGT",
        target_ecef_m=target_coord,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC_UNIT_TEST",
        spatial_model="zero",
        ztd_by_station_epoch=uniform_ztd,
        tropo_mode="network_ztd",
        require_interior_hull=True,
    )
    assert vrs_tropo_ztd.outcome == VrsOutcome.EXPERIMENTAL_VRS_GENERATED
    # With uniform 0.20 m ZWD at all refs, differential tropo must stay small (no -0.20*mw bias)
    assert all(abs(o.tropo_correction_m) < 0.25 for o in vrs_tropo_ztd.observations)


def test_experimental_vrs_fail_closed_gates() -> None:
    sc = _synthetic_vrs_scenario()
    ref_coords = sc["ref_coords"]
    ref_datasets = sc["ref_datasets"]
    target_coord = sc["target_coord"]
    nav = sc["nav"]
    assert isinstance(ref_coords, dict)
    assert isinstance(ref_datasets, dict)
    assert isinstance(target_coord, tuple)
    assert isinstance(nav, dict)

    # Gate 1: operational promotion blocked
    r_op = generate_experimental_vrs(
        experiment_id="op-block",
        target_station_id="TGT",
        target_ecef_m=target_coord,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC",
        requested_maturity=VrsMaturity.OPERATIONALLY_APPROVED_VRS,
    )
    assert r_op.outcome == VrsOutcome.VRS_GENERATION_BLOCKED
    with pytest.raises(VrsRtcmBridgeError):
        encode_experimental_vrs_to_rtcm(r_op)

    # Gate 4: extrapolation outside hull blocked when require_interior_hull=True
    r_ext = generate_experimental_vrs(
        experiment_id="ext-block",
        target_station_id="EXT",
        target_ecef_m=geodetic_to_ecef(14.0, 14.0, 300.0),
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC",
        spatial_model="zero",
        require_interior_hull=True,
    )
    assert r_ext.outcome == VrsOutcome.INSUFFICIENT_NETWORK_GEOMETRY

    # Gate 6: missing atmospheric model blocked
    r_atmo = generate_experimental_vrs(
        experiment_id="atmo-block",
        target_station_id="TGT",
        target_ecef_m=target_coord,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC",
        spatial_model="idw2",
        iono_field_by_key=None,
    )
    assert r_atmo.outcome == VrsOutcome.ATMOSPHERIC_MODEL_UNAVAILABLE


def test_rtcm_bridge_isolated_ntrip_loopback_and_decoders() -> None:
    sc = _synthetic_vrs_scenario()
    ref_coords = sc["ref_coords"]
    ref_datasets = sc["ref_datasets"]
    target_coord = sc["target_coord"]
    nav = sc["nav"]
    iono_field = sc["iono_field"]
    assert isinstance(ref_coords, dict)
    assert isinstance(ref_datasets, dict)
    assert isinstance(target_coord, tuple)
    assert isinstance(nav, dict)
    assert isinstance(iono_field, dict)

    vrs = generate_experimental_vrs(
        experiment_id="rtcm-ntrip-e2e",
        target_station_id="TGT",
        target_ecef_m=target_coord,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="SYNTHETIC_UNIT_TEST",
        spatial_model="idw2",
        iono_field_by_key=iono_field,
        tropo_mode="unb3m",
    )
    bundle = encode_experimental_vrs_to_rtcm(vrs, rtcm_station_id=2099, effective_interval_s=60.0)
    assert bundle.classification == OutputClassification.RESEARCH_VALIDATION
    assert bundle.operational_approved is False
    assert bundle.frames[0].message_number == 1005
    assert all(f.message_number == 1074 for f in bundle.frames[1:])
    assert len(bundle.integer_arc_offsets) >= 8  # 4 sats * 2 frequencies

    # Mountpoint policy: cannot mix synthetic and experimental flags
    with pytest.raises(MountpointError):
        MountpointDefinition(
            name="BAD_MIX", synthetic_only=True, experimental_vrs_only=True
        ).validate()

    # Stream over isolated NLGCP_VRS_EXP and verify NLGCP_TEST isolation
    vrs_mp = experimental_vrs_mountpoint()
    registry = MountpointRegistry((MountpointDefinition(name=DEFAULT_MOUNTPOINT), vrs_mp))
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={"lab": "secret-pass-2026"},
        source_credentials={"src": "secret-src-2026"},
    )
    with LocalNtripCaster(cfg, registry=registry) as caster:
        # Cross-publishing experimental VRS onto synthetic NLGCP_TEST MUST fail closed
        with pytest.raises(PublicationError):
            caster.publish_experimental_vrs_frames(
                bundle.frames, mountpoint=DEFAULT_MOUNTPOINT, artifact=bundle.artifact
            )
        # Publishing OPERATIONAL_APPROVED frame MUST fail closed
        op_frame = GeneratedCorrectionFrame(
            message_family="REFERENCE_STATION_1005",
            message_number=1005,
            payload_length=bundle.frames[0].payload_length,
            frame_length=bundle.frames[0].frame_length,
            crc_hex=bundle.frames[0].crc_hex,
            frame_sha256=bundle.frames[0].frame_sha256,
            raw_bytes=bundle.frames[0].raw_bytes,
            request_fingerprint=bundle.frames[0].request_fingerprint,
            encoder_version=bundle.frames[0].encoder_version,
            input_status="FORBIDDEN",
            classification=OutputClassification.OPERATIONAL_APPROVED,
            scientific_status="FORBIDDEN",
        )
        with pytest.raises(PublicationError):
            caster.publish_experimental_vrs_frames(
                (op_frame,), mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT, artifact=bundle.artifact
            )

        # Valid publication onto isolated NLGCP_VRS_EXP
        pub = caster.publish_experimental_vrs_frames(
            bundle.frames, mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT, artifact=bundle.artifact
        )
        assert len(pub) == len(bundle.frames)

        client = LocalNtripClient(
            ClientConfig(
                host=caster.host,
                port=caster.port,
                mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
                username="lab",
                password="secret-pass-2026",
                ntrip_version="2.0",
                read_timeout_s=2.0,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.1, max_attempts=1
                ),
            )
        )
        code, table = client.fetch_sourcetable()
        assert code == 200
        assert EXPERIMENTAL_VRS_MOUNTPOINT in table
        assert "NOT OPERATIONAL" in table
        rx = client.receive_frames(max_frames=len(bundle.frames), allow_reconnect=False)
        assert rx.ok is True
        assert len(rx.invalid_frames) == 0
        rx_bytes = b"".join(f.raw for f in rx.valid_frames)
        assert hashlib.sha256(rx_bytes).hexdigest() == bundle.stream_sha256

    # Independent RTKLIB verification when RTKLIB_SOURCE is set
    rtklib_src = os.environ.get("RTKLIB_SOURCE")
    if rtklib_src:
        conv = decode_with_convbin(rx_bytes, ref_date="2024/01/26", ref_time="00:00:00")
        assert conv.returncode == 0
        assert conv.station_id == 2099
        assert conv.approx_position_xyz is not None
        assert math.dist(conv.approx_position_xyz, target_coord) < 0.001
        assert len(conv.epochs) == len(bundle.frames) - 1

        exe, _ = build_rtklib_decoder(REPO_ROOT, Path(rtklib_src))
        nat = decode_with_rtklib_native(exe, rx_bytes, ref_epoch=(2024, 1, 26, 0, 0, 0.0))
        m1005 = [m for m in nat["events"] if m["msg_no"] == 1005 and m["crc_ok"]]
        assert len(m1005) == 1
        assert m1005[0]["staid"] == 2099
        assert math.dist(m1005[0]["pos_ecef"], target_coord) < 0.0002
        assert nat["summary"]["crc_errors"] == 0
        assert nat["summary"]["nmsg3_1074"] == len(bundle.frames) - 1

    # Independent non-RTKLIB ESA/gAGE-UPC gLAB v6.0.0 verification when installed
    if GLAB_DEFAULT_SOURCE.is_dir():
        try:
            g_exe, _ = build_glab_rtcm1005_decoder(REPO_ROOT, GLAB_DEFAULT_SOURCE)
            glab = decode_rtcm1005_with_glab(g_exe, rx_bytes)
            assert glab["summary"]["crc_fail_count"] == 0
            assert glab["summary"]["msg1005_decoded_count"] == 1
            f1005 = glab["frames"][0]
            assert f1005["station_id"] == 2099
            assert f1005["reference_station_indicator"] == 1
            assert (
                math.dist((f1005["ecef_x_m"], f1005["ecef_y_m"], f1005["ecef_z_m"]), target_coord)
                < 0.0002
            )
        except IndependentDecoderUnavailable:
            pass
