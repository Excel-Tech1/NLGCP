#!/usr/bin/env python3
"""Reproducible Phase 7 Experimental VRS, RTCM, NTRIP & Failure-Mode Runner.

Executes Experiments 5–8 against immutable historical GNSS archives under
``NLGCP_DATA_ROOT`` and writes derived evidence outside Git under
``${NLGCP_DATA_ROOT}/processed/vrs/sprint-phase67/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

_SERVICE_SRC = Path(__file__).resolve().parents[1] / "services" / "correction-service" / "src"
if str(_SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(_SERVICE_SRC))

from nlgcp_atmospheric_model.dataset_audit import load_osgof_provisional_coords  # noqa: E402
from nlgcp_atmospheric_model.ionosphere_estimation import (  # noqa: E402
    IonosphericPointEstimate,
    common_arc_sd_l1_iono,
    estimate_station_ionosphere,
    slm_mapping_and_ipp,
)
from nlgcp_atmospheric_model.observations import (  # noqa: E402
    Rinex2Header,
    SatObs,
    StationDataset,
    read_rinex2_from_zip,
    read_rinex2_observations,
)
from nlgcp_atmospheric_model.provenance import sha256_file, utc_now_iso  # noqa: E402
from nlgcp_atmospheric_model.satellite_geometry import (  # noqa: E402
    geometry_table,
    parse_gps_nav_auto,
)
from nlgcp_atmospheric_model.troposphere_estimation import parse_pride_ztd  # noqa: E402
from nlgcp_correction_service import (  # noqa: E402
    DEFAULT_MOUNTPOINT,
    EXPERIMENTAL_VRS_MOUNTPOINT,
    LOOPBACK_HOST,
)
from nlgcp_correction_service.caster import LocalNtripCaster  # noqa: E402
from nlgcp_correction_service.client import LocalNtripClient  # noqa: E402
from nlgcp_correction_service.config import CasterConfig, ClientConfig  # noqa: E402
from nlgcp_correction_service.mountpoints import (  # noqa: E402
    MountpointDefinition,
    MountpointRegistry,
    experimental_vrs_mountpoint,
)
from nlgcp_correction_service.publisher import PublicationError  # noqa: E402
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy  # noqa: E402
from nlgcp_rtcm_generation.independent_decoder import (  # noqa: E402
    GLAB_DEFAULT_SOURCE,
    build_glab_rtcm1005_decoder,
    build_rtklib_decoder,
    convbin_provenance,
    decode_rtcm1005_with_glab,
    decode_with_convbin,
    decode_with_rtklib_native,
)
from nlgcp_rtcm_generation.models import (  # noqa: E402
    GeneratedCorrectionFrame,
    OutputClassification,
)
from nlgcp_vrs.experimental_vrs import (  # noqa: E402
    ExperimentalVrsResult,
    VrsMaturity,
    VrsOutcome,
    generate_experimental_vrs,
    validate_experimental_vrs_against_target,
)
from nlgcp_vrs.rtcm_bridge import (  # noqa: E402
    ExperimentalVrsRtcmBundle,
    encode_experimental_vrs_to_rtcm,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _compute_ref_iono_field(
    *,
    ref_datasets: dict[str, StationDataset],
    ref_coords: dict[str, tuple[float, float, float]],
    target_station: str,
    target_ecef: tuple[float, float, float],
    nav_records: dict[str, Any],
    nav_hash: str,
    datum_station: str,
    stride: int,
) -> tuple[
    dict[tuple[str, str, str], float],
    dict[tuple[str, str, str], tuple[float, float]],
    dict[tuple[str, str], tuple[float, float]],
    dict[str, Any],
]:
    """Compute reference-only ionospheric field + IPPs with zero target-observation leakage."""
    all_epochs = sorted(set.union(*(set(ds.epochs) for ds in ref_datasets.values())))
    all_gps_sats = sorted(
        {
            sat
            for ds in ref_datasets.values()
            for ep_map in ds.data.values()
            for sat in ep_map
            if sat.startswith("G")
        }
    )
    coords_plus_target = {**ref_coords, target_station: target_ecef}
    topo_rows, _ = geometry_table(
        epochs=all_epochs,
        satellites=all_gps_sats,
        station_coords=coords_plus_target,
        nav_records=nav_records,
        nav_hash=nav_hash,
    )
    topo_by_st: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
        st: {} for st in coords_plus_target
    }
    for topo in topo_rows:
        topo_by_st[topo.station_id][(topo.epoch_iso, topo.satellite_id)] = (
            topo.elevation_deg,
            topo.azimuth_deg,
        )

    iono_by_st: dict[str, list[IonosphericPointEstimate]] = {}
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] = {}
    for st in sorted(ref_datasets):
        ests, _ = estimate_station_ionosphere(
            ref_datasets[st],
            ref_coords[st],
            topo_by_st[st],
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.35 if stride > 1 else 0.25,
        )
        iono_by_st[st] = ests
        for e in ests:
            ipp_by_key[(e.epoch_iso, e.satellite_id, st)] = (e.ipp_lat_deg, e.ipp_lon_deg)

    # Target IPPs depend ONLY on known target geometry + broadcast ephemeris (no target obs)
    target_ipps: dict[tuple[str, str], tuple[float, float]] = {}
    for (ep, sat), (el_deg, az_deg) in topo_by_st[target_station].items():
        if el_deg >= 15.0:
            _mf, ipp_lat, ipp_lon = slm_mapping_and_ipp(target_ecef, el_deg, az_deg)
            target_ipps[(ep, sat)] = (ipp_lat, ipp_lon)

    obs_field, meta = common_arc_sd_l1_iono(iono_by_st, datum_station)
    return obs_field, ipp_by_key, target_ipps, meta


def _verify_rtcm_bundle_with_decoders(
    *,
    bundle: ExperimentalVrsRtcmBundle,
    expected_ecef: tuple[float, float, float],
    ref_date_slash: str,
    ref_epoch_tuple: tuple[int, int, int, int, int, float],
    rtklib_exe: Path,
    glab_exe: Path,
) -> dict[str, Any]:
    """Decode RTCM 1005+1074 via RTKLIB convbin, RTKLIB native, and ESA/gAGE-UPC gLAB v6."""
    conv = decode_with_convbin(
        bundle.stream_bytes, ref_date=ref_date_slash, ref_time="00:00:00"
    )
    conv_pos_err_m = (
        round(math.dist(conv.approx_position_xyz, expected_ecef), 6)
        if conv.approx_position_xyz
        else None
    )

    native = decode_with_rtklib_native(
        rtklib_exe, bundle.stream_bytes, ref_epoch=ref_epoch_tuple
    )
    nat_events = native.get("events", [])
    nat_1005 = [m for m in nat_events if m.get("msg_no") == 1005 and m.get("crc_ok")]
    nat_1074 = [m for m in nat_events if m.get("msg_no") == 1074 and m.get("crc_ok")]
    nat_pos_err_m: float | None = None
    if nat_1005:
        pos = nat_1005[0]["pos_ecef"]
        nat_pos_err_m = round(
            math.dist((float(pos[0]), float(pos[1]), float(pos[2])), expected_ecef), 6
        )

    glab = decode_rtcm1005_with_glab(glab_exe, bundle.stream_bytes)
    glab_1005 = [f for f in glab.get("frames", []) if f.get("message_number") == 1005]
    glab_pos_err_m: float | None = None
    if glab_1005:
        g0 = glab_1005[0]
        glab_pos_err_m = round(
            math.dist(
                (float(g0["ecef_x_m"]), float(g0["ecef_y_m"]), float(g0["ecef_z_m"])),
                expected_ecef,
            ),
            6,
        )

    return {
        "stream_bytes_len": len(bundle.stream_bytes),
        "stream_sha256": bundle.stream_sha256,
        "frame_count": len(bundle.frames),
        "rtklib_convbin": {
            "returncode": conv.returncode,
            "station_id": conv.station_id,
            "approx_position_xyz": list(conv.approx_position_xyz)
            if conv.approx_position_xyz
            else None,
            "ecef_error_m": conv_pos_err_m,
            "sys_obs_types": {k: list(v) for k, v in conv.sys_obs_types.items()},
            "decoded_epoch_count": len(conv.epochs),
            "decoded_sat_obs_total": sum(len(ep.satellites) for ep in conv.epochs),
            "passed": (
                conv.returncode == 0
                and conv.station_id == bundle.rtcm_station_id
                and conv_pos_err_m is not None
                and conv_pos_err_m < 0.001
                and len(conv.epochs) == len(bundle.frames) - 1
            ),
        },
        "rtklib_native_input_rtcm3": {
            "msg1005_count": len(nat_1005),
            "msg1074_count": len(nat_1074),
            "station_id": nat_1005[0]["staid"] if nat_1005 else None,
            "ecef_error_m": nat_pos_err_m,
            "decoded_obs_total": sum(len(m.get("obs", [])) for m in nat_1074),
            "summary": native.get("summary"),
            "passed": (
                len(nat_1005) == 1
                and len(nat_1074) == len(bundle.frames) - 1
                and native.get("summary", {}).get("crc_errors") == 0
                and native.get("summary", {}).get("decode_errors") == 0
                and nat_pos_err_m is not None
                and nat_pos_err_m < 0.0002
            ),
        },
        "glab_v6_non_rtklib_cross_decoder": {
            "decoder": glab.get("decoder"),
            "msm4_supported": glab.get("msm4_supported"),
            "summary": glab.get("summary"),
            "msg1005_station_id": glab_1005[0]["station_id"] if glab_1005 else None,
            "msg1005_reference_station_indicator": (
                glab_1005[0]["reference_station_indicator"] if glab_1005 else None
            ),
            "msg1005_ecef_error_m": glab_pos_err_m,
            "non_rtklib_1005_and_crc24q_passed": (
                glab.get("summary", {}).get("crc_fail_count") == 0
                and glab.get("summary", {}).get("frame_count") == len(bundle.frames)
                and glab.get("summary", {}).get("msg1005_decoded_count") == 1
                and glab_pos_err_m is not None
                and glab_pos_err_m < 0.0002
            ),
            "non_rtklib_msm4_status": "NOT_SUPPORTED_BY_GLAB_V6",
        },
    }


def _run_ntrip_loopback_experiment(
    *,
    bundle: ExperimentalVrsRtcmBundle,
    expected_ecef: tuple[float, float, float],
    ref_date_slash: str,
    ref_epoch_tuple: tuple[int, int, int, int, int, float],
    rtklib_exe: Path,
    glab_exe: Path,
    target_lat_deg: float,
    target_lon_deg: float,
) -> dict[str, Any]:
    """Experiment 7: Stream experimental VRS RTCM over isolated NLGCP_VRS_EXP loopback caster."""
    vrs_mp = experimental_vrs_mountpoint(
        name=EXPERIMENTAL_VRS_MOUNTPOINT,
        latitude=target_lat_deg,
        longitude=target_lon_deg,
        format_details="1005(1),1074(1)",
    )
    registry = MountpointRegistry((MountpointDefinition(name=DEFAULT_MOUNTPOINT), vrs_mp))
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={"vrs-research-client": "ephemeral-lab-pass-2026"},
        source_credentials={"vrs-research-src": "ephemeral-src-pass-2026"},
    )
    with LocalNtripCaster(cfg, registry=registry) as caster:
        host, port = caster.host, caster.port
        published = caster.publish_experimental_vrs_frames(
            bundle.frames,
            mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
            artifact=bundle.artifact,
        )
        client = LocalNtripClient(
            ClientConfig(
                host=host,
                port=port,
                mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
                username="vrs-research-client",
                password="ephemeral-lab-pass-2026",
                ntrip_version="2.0",
                read_timeout_s=2.0,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.1, max_attempts=2
                ),
            )
        )
        st_code, sourcetable = client.fetch_sourcetable()
        recv = client.receive_frames(max_frames=len(bundle.frames), allow_reconnect=False)
        received_bytes = b"".join(f.raw for f in recv.valid_frames)
        received_sha = hashlib.sha256(received_bytes).hexdigest()
        caster_snap = caster.status_snapshot()

    # Independently decode the bytes actually received over TCP/NTRIP!
    rx_conv = decode_with_convbin(
        received_bytes, ref_date=ref_date_slash, ref_time="00:00:00"
    )
    rx_nat = decode_with_rtklib_native(
        rtklib_exe, received_bytes, ref_epoch=ref_epoch_tuple
    )
    rx_glab = decode_rtcm1005_with_glab(glab_exe, received_bytes)
    rx_pos_err = (
        round(math.dist(rx_conv.approx_position_xyz, expected_ecef), 6)
        if rx_conv.approx_position_xyz
        else None
    )
    return {
        "mountpoint": EXPERIMENTAL_VRS_MOUNTPOINT,
        "loopback_host": LOOPBACK_HOST,
        "sourcetable_http_status": st_code,
        "sourcetable_contains_vrs_exp": EXPERIMENTAL_VRS_MOUNTPOINT in sourcetable,
        "sourcetable_contains_not_operational_label": "NOT OPERATIONAL" in sourcetable,
        "sourcetable_preserves_synthetic_mountpoint": DEFAULT_MOUNTPOINT in sourcetable,
        "frames_published": len(published),
        "frames_received_valid": len(recv.valid_frames),
        "frames_received_invalid": len(recv.invalid_frames),
        "client_ok": recv.ok,
        "byte_exact_sha256_match": received_sha == bundle.stream_sha256,
        "received_stream_sha256": received_sha,
        "emitted_stream_sha256": bundle.stream_sha256,
        "received_decode_convbin_epochs": len(rx_conv.epochs),
        "received_decode_convbin_ecef_err_m": rx_pos_err,
        "received_decode_rtklib_native_msgs": len(rx_nat.get("events", [])),
        "received_decode_glab_summary": rx_glab.get("summary"),
        "caster_diagnostics": caster_snap,
    }


def _run_failure_mode_suite(
    *,
    ref_coords_2011: dict[str, tuple[float, float, float]],
    ref_ds_2011: dict[str, StationDataset],
    target_ecef_2011: tuple[float, float, float],
    nav_2011: dict[str, Any],
    iono_2011: dict[tuple[str, str, str], float],
    ref_coords_2024: dict[str, tuple[float, float, float]],
    ref_ds_2024: dict[str, StationDataset],
    target_ecef_2024: tuple[float, float, float],
    nav_2024: dict[str, Any],
    bundle_2011: ExperimentalVrsRtcmBundle,
) -> dict[str, Any]:
    """Experiment 8: Exercise all 11 required fail-closed & boundary security scenarios."""
    results: dict[str, Any] = {}

    # 1. Missing observations (empty dataset)
    empty_ds = {
        k: StationDataset(
            station_id=k,
            header=v.header,
            epochs=[],
            data={},
        )
        for k, v in ref_ds_2011.items()
    }
    r1 = generate_experimental_vrs(
        experiment_id="fail-missing-obs",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords=ref_coords_2011,
        reference_datasets=empty_ds,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
        spatial_model="zero",
        tropo_mode="unb3m",
    )
    results["1_missing_observations"] = {
        "outcome": str(r1.outcome),
        "reason_codes": list(r1.reason_codes),
        "passed": r1.outcome == VrsOutcome.INSUFFICIENT_OBSERVATION_COVERAGE,
    }

    # 2. Poor geometry / outside convex hull (2024 PHRI00NGA with strict interior hull)
    r2 = generate_experimental_vrs(
        experiment_id="fail-extrapolation",
        target_station_id="PHRI00NGA",
        target_ecef_m=target_ecef_2024,
        reference_coords=ref_coords_2024,
        reference_datasets=ref_ds_2024,
        nav_records=nav_2024,
        doy=26,
        reference_frame="IGS20",
        coordinate_epoch="2024.07",
        coordinate_provenance="VERIFIED_IGS20",
        spatial_model="zero",
        tropo_mode="unb3m",
        require_interior_hull=True,
    )
    results["2_poor_geometry_extrapolation"] = {
        "outcome": str(r2.outcome),
        "reason_codes": list(r2.reason_codes),
        "inside_convex_hull": r2.inside_convex_hull,
        "passed": r2.outcome == VrsOutcome.INSUFFICIENT_NETWORK_GEOMETRY,
    }

    # 3. Missing dual-frequency observables (anchor restricted to L1/C1 single-frequency)
    sf_ds = dict(ref_ds_2011)
    anchor_id = "CGGT"
    orig_anc = ref_ds_2011[anchor_id]
    sf_header = Rinex2Header(
        path=orig_anc.header.path,
        obs_types=("C1", "L1"),
        interval_s=orig_anc.header.interval_s,
        time_of_first_obs=orig_anc.header.time_of_first_obs,
        approx_xyz_m=orig_anc.header.approx_xyz_m,
    )
    sf_data: dict[str, dict[str, SatObs]] = {}
    for ep, smap in list(orig_anc.data.items())[:5]:
        sf_data[ep] = {
            sat: SatObs(
                values={k: v for k, v in o.values.items() if k in ("C1", "L1")},
                lli={},
            )
            for sat, o in smap.items()
        }
    sf_ds[anchor_id] = StationDataset(
        station_id=anchor_id,
        header=sf_header,
        epochs=sorted(sf_data),
        data=sf_data,
    )
    r3 = generate_experimental_vrs(
        experiment_id="fail-single-freq",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords=ref_coords_2011,
        reference_datasets=sf_ds,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
        spatial_model="zero",
        tropo_mode="unb3m",
    )
    results["3_missing_dual_frequency"] = {
        "outcome": str(r3.outcome),
        "reason_codes": list(r3.reason_codes),
        "passed": r3.outcome == VrsOutcome.INSUFFICIENT_OBSERVATION_COVERAGE,
    }

    # 4. Invalid station coordinates (non-terrestrial radius)
    r4 = generate_experimental_vrs(
        experiment_id="fail-invalid-coord",
        target_station_id="OSGF",
        target_ecef_m=(1000.0, 2000.0, 3000.0),
        reference_coords=ref_coords_2011,
        reference_datasets=ref_ds_2011,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
    )
    results["4_invalid_station_coordinates"] = {
        "outcome": str(r4.outcome),
        "reason_codes": list(r4.reason_codes),
        "passed": r4.outcome == VrsOutcome.INVALID_STATION_COORDINATES,
    }

    # 5. Insufficient reference stations (<3 refs)
    two_refs = list(sorted(ref_coords_2011))[:2]
    r5 = generate_experimental_vrs(
        experiment_id="fail-lt3-refs",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords={k: ref_coords_2011[k] for k in two_refs},
        reference_datasets={k: ref_ds_2011[k] for k in two_refs},
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
    )
    results["5_insufficient_reference_stations"] = {
        "outcome": str(r5.outcome),
        "reason_codes": list(r5.reason_codes),
        "passed": r5.outcome == VrsOutcome.INSUFFICIENT_NETWORK_GEOMETRY,
    }

    # 6. Atmospheric model failure (non-zero spatial model with missing iono field)
    r6 = generate_experimental_vrs(
        experiment_id="fail-atmo-missing",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords=ref_coords_2011,
        reference_datasets=ref_ds_2011,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
        spatial_model="idw2",
        iono_field_by_key=None,
    )
    results["6_atmospheric_model_unavailable"] = {
        "outcome": str(r6.outcome),
        "reason_codes": list(r6.reason_codes),
        "passed": r6.outcome == VrsOutcome.ATMOSPHERIC_MODEL_UNAVAILABLE,
    }

    # 7. Invalid RTCM frame (flipped CRC bit rejected by Phase 12 publisher)
    vrs_mp = experimental_vrs_mountpoint()
    registry = MountpointRegistry((MountpointDefinition(name=DEFAULT_MOUNTPOINT), vrs_mp))
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={"c": "pass-123456"},
        source_credentials={"s": "src-123456"},
    )
    corrupt_raw = bytearray(bundle_2011.frames[0].raw_bytes)
    corrupt_raw[-1] ^= 0xFF
    corrupt_bytes = bytes(corrupt_raw)
    corrupt_frame = GeneratedCorrectionFrame(
        message_family=bundle_2011.frames[0].message_family,
        message_number=bundle_2011.frames[0].message_number,
        payload_length=bundle_2011.frames[0].payload_length,
        frame_length=len(corrupt_bytes),
        crc_hex=corrupt_bytes[-3:].hex(),
        frame_sha256=hashlib.sha256(corrupt_bytes).hexdigest(),
        raw_bytes=corrupt_bytes,
        request_fingerprint=bundle_2011.frames[0].request_fingerprint,
        encoder_version=bundle_2011.frames[0].encoder_version,
        input_status=bundle_2011.frames[0].input_status,
        classification=OutputClassification.RESEARCH_VALIDATION,
        scientific_status=bundle_2011.frames[0].scientific_status,
    )
    caster_err = LocalNtripCaster(cfg, registry=registry)
    crc_rejected = False
    crc_msg = ""
    try:
        caster_err.publish_experimental_vrs_frames(
            (corrupt_frame,),
            mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
            artifact=bundle_2011.artifact,
        )
    except PublicationError as exc:
        crc_rejected = "CRC-24Q" in str(exc)
        crc_msg = str(exc)
    results["7_invalid_rtcm_crc_frame"] = {
        "rejected": crc_rejected,
        "error": crc_msg,
        "passed": crc_rejected,
    }

    # 8. Unsupported GNSS message family
    r8 = generate_experimental_vrs(
        experiment_id="fail-unsupported-family",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords=ref_coords_2011,
        reference_datasets=ref_ds_2011,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
        supported_message_families=("MSM7_GALILEO_1097",),
    )
    results["8_unsupported_gnss_message_family"] = {
        "outcome": str(r8.outcome),
        "reason_codes": list(r8.reason_codes),
        "passed": r8.outcome == VrsOutcome.VALIDATION_FAILED,
    }

    # 9. Interrupted NTRIP stream + clean reconnect recovery
    with LocalNtripCaster(cfg, registry=registry) as caster_int:
        # Publish 2 frames, force disconnect mid-stream, then publish remaining frames
        caster_int.publish_experimental_vrs_frames(
            bundle_2011.frames[:2],
            mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
            artifact=bundle_2011.artifact,
            retain_in_backlog=True,
        )
        client_int = LocalNtripClient(
            ClientConfig(
                host=caster_int.host,
                port=caster_int.port,
                mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
                username="c",
                password="pass-123456",
                ntrip_version="2.0",
                read_timeout_s=1.0,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.1, max_attempts=3
                ),
            )
        )

        def _interrupt_and_resume() -> None:
            time.sleep(0.15)
            caster_int.disconnect_clients(EXPERIMENTAL_VRS_MOUNTPOINT)
            time.sleep(0.05)
            caster_int.publish_experimental_vrs_frames(
                bundle_2011.frames[2:4],
                mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
                artifact=bundle_2011.artifact,
                retain_in_backlog=True,
            )

        t = threading.Thread(target=_interrupt_and_resume, daemon=True)
        t.start()
        rx_int = client_int.receive_frames(max_frames=4, allow_reconnect=True)
        t.join(timeout=2.0)

    results["9_interrupted_ntrip_stream_recovery"] = {
        "client_ok": rx_int.ok,
        "valid_frames": len(rx_int.valid_frames),
        "invalid_frames": len(rx_int.invalid_frames),
        "reconnection_attempts": rx_int.reconnection_attempts,
        "passed": rx_int.ok and rx_int.reconnection_attempts >= 1,
    }

    # 10. Invalid provenance / held-out target leakage
    r10a = generate_experimental_vrs(
        experiment_id="fail-missing-provenance",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords=ref_coords_2011,
        reference_datasets=ref_ds_2011,
        nav_records=nav_2011,
        doy=79,
        reference_frame="",
        coordinate_epoch="",
        coordinate_provenance="",
    )
    r10b = generate_experimental_vrs(
        experiment_id="fail-target-leakage",
        target_station_id="CGGT",
        target_ecef_m=ref_coords_2011["CGGT"],
        reference_coords=ref_coords_2011,
        reference_datasets=ref_ds_2011,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
    )
    results["10_invalid_provenance_and_target_leakage"] = {
        "missing_provenance_outcome": str(r10a.outcome),
        "target_leakage_outcome": str(r10b.outcome),
        "passed": (
            r10a.outcome == VrsOutcome.INVALID_STATION_COORDINATES
            and r10b.outcome == VrsOutcome.VRS_GENERATION_BLOCKED
        ),
    }

    # 11. Attempted operational promotion & synthetic/experimental cross-mountpoint isolation
    r11 = generate_experimental_vrs(
        experiment_id="fail-op-promo",
        target_station_id="OSGF",
        target_ecef_m=target_ecef_2011,
        reference_coords=ref_coords_2011,
        reference_datasets=ref_ds_2011,
        nav_records=nav_2011,
        doy=79,
        reference_frame="ITRF2008_OSGOF",
        coordinate_epoch="2011-01-01",
        coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
        spatial_model="idw2",
        iono_field_by_key=iono_2011,
        requested_maturity=VrsMaturity.OPERATIONALLY_APPROVED_VRS,
    )
    cross_to_synthetic_blocked = False
    try:
        caster_err.publish_experimental_vrs_frames(
            bundle_2011.frames[:1],
            mountpoint=DEFAULT_MOUNTPOINT,
            artifact=bundle_2011.artifact,
        )
    except PublicationError:
        cross_to_synthetic_blocked = True

    op_frame = GeneratedCorrectionFrame(
        message_family=bundle_2011.frames[0].message_family,
        message_number=bundle_2011.frames[0].message_number,
        payload_length=bundle_2011.frames[0].payload_length,
        frame_length=bundle_2011.frames[0].frame_length,
        crc_hex=bundle_2011.frames[0].crc_hex,
        frame_sha256=bundle_2011.frames[0].frame_sha256,
        raw_bytes=bundle_2011.frames[0].raw_bytes,
        request_fingerprint=bundle_2011.frames[0].request_fingerprint,
        encoder_version=bundle_2011.frames[0].encoder_version,
        input_status=bundle_2011.frames[0].input_status,
        classification=OutputClassification.OPERATIONAL_APPROVED,
        scientific_status="FORBIDDEN",
    )
    op_frame_blocked = False
    try:
        caster_err.publish_experimental_vrs_frames(
            (op_frame,),
            mountpoint=EXPERIMENTAL_VRS_MOUNTPOINT,
            artifact=bundle_2011.artifact,
        )
    except PublicationError:
        op_frame_blocked = True

    results["11_operational_promotion_and_mountpoint_isolation"] = {
        "vrs_op_maturity_outcome": str(r11.outcome),
        "vrs_op_maturity_reasons": list(r11.reason_codes),
        "cross_publish_to_NLGCP_TEST_blocked": cross_to_synthetic_blocked,
        "operational_approved_frame_blocked": op_frame_blocked,
        "passed": (
            r11.outcome == VrsOutcome.VRS_GENERATION_BLOCKED
            and cross_to_synthetic_blocked
            and op_frame_blocked
        ),
    }

    return {
        "total_scenarios": len(results),
        "all_passed": all(v["passed"] for v in results.values()),
        "scenarios": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NLGCP Phase 7 Experimental VRS Sprint Runner")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data")),
    )
    parser.add_argument(
        "--rtklib-source",
        type=Path,
        default=Path(os.environ.get("RTKLIB_SOURCE", "/home/excellence/RTKLIB")),
    )
    parser.add_argument("--stride", type=int, default=4, help="Epoch stride (4=120s, 720 ep/day)")
    parser.add_argument(
        "--rtcm-epochs",
        type=int,
        default=30,
        help="Number of epochs to encode into RTCM 1074 stream",
    )
    args = parser.parse_args(argv)

    data_root: Path = args.data_root
    out_dir = data_root / "processed/vrs/sprint-phase67"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build native independent decoders (RTKLIB v2.4.2-p13 + ESA/gAGE-UPC gLAB v6.0.0)
    rtklib_exe, rtklib_prov = build_rtklib_decoder(REPO_ROOT, args.rtklib_source)
    glab_exe, glab_prov = build_glab_rtcm1005_decoder(REPO_ROOT, GLAB_DEFAULT_SOURCE)
    conv_prov = convbin_provenance()

    # =========================================================================
    # EXPERIMENT 5A: 2011-03-20 (DOY 079) Interior Target OSGF (8 refs)
    # =========================================================================
    zip_2011 = data_root / "incoming/southern-nignet/NIGNET2011.zip"
    audit_csv = (
        data_root / "validation/southern-nignet/run-20261030T125136Z/rinex_header_audit.csv"
    )
    osgof_csv = (
        data_root
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261030T132927Z/coordinate_provenance.csv"
    )
    nav_2011_path = (
        data_root
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261123T163056Z/navigation-products/attempts/bkg/brdc0790.11n.Z"
    )
    osgof_coords = load_osgof_provisional_coords(osgof_csv)
    stations_2011 = ("ABUZ", "BKFP", "CGGT", "FUTY", "MDGR", "OSGF", "RUST", "ULAG", "UNEC")
    members_2011: dict[str, str] = {}
    with audit_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["observation_date_from_filename"] == "2011-03-20":
                st4 = row["canonical_station_id"][:4]
                if st4 in stations_2011:
                    members_2011[st4] = row["relative_path"]

    ds_2011_all = {
        st: read_rinex2_from_zip(zip_2011, members_2011[st], st, stride=args.stride)
        for st in sorted(stations_2011)
    }
    target_2011 = "OSGF"
    ref_ds_2011 = {k: v for k, v in ds_2011_all.items() if k != target_2011}
    ref_coords_2011 = {k: osgof_coords[k] for k in ref_ds_2011}
    target_ds_2011 = ds_2011_all[target_2011]
    target_ecef_2011 = osgof_coords[target_2011]

    nav_2011 = parse_gps_nav_auto(nav_2011_path)
    nav_2011_hash = sha256_file(nav_2011_path)

    # Anchor for OSGF is CGGT (216 km); compute reference-only iono field relative to CGGT
    iono_2011, ipp_2011, tgt_ipp_2011, iono_meta_2011 = _compute_ref_iono_field(
        ref_datasets=ref_ds_2011,
        ref_coords=ref_coords_2011,
        target_station=target_2011,
        target_ecef=target_ecef_2011,
        nav_records=nav_2011,
        nav_hash=nav_2011_hash,
        datum_station="CGGT",
        stride=args.stride,
    )

    exp5a_variants: dict[str, dict[str, Any]] = {}
    vrs_2011_primary: ExperimentalVrsResult | None = None
    for variant_name, sp_model, tr_mode in (
        ("zero_geom_only", "zero", "zero"),
        ("tropo_unb3m_only", "zero", "unb3m"),
        ("idw2_unb3m", "idw2", "unb3m"),
        ("planar_unb3m", "planar", "unb3m"),
        ("ipp_idw2_unb3m", "ipp_idw2", "unb3m"),
    ):
        vrs = generate_experimental_vrs(
            experiment_id=f"2011-03-20-osgf-{variant_name}",
            target_station_id=target_2011,
            target_ecef_m=target_ecef_2011,
            reference_coords=ref_coords_2011,
            reference_datasets=ref_ds_2011,
            nav_records=nav_2011,
            doy=79,
            reference_frame="ITRF2008_OSGOF",
            coordinate_epoch="2011-01-01",
            coordinate_provenance="PROVISIONAL_OSGOF_2011_01_01",
            spatial_model=sp_model,
            iono_field_by_key=iono_2011 if sp_model != "zero" else None,
            ipp_by_key=ipp_2011 if sp_model == "ipp_idw2" else None,
            target_ipp_by_epoch_sat=tgt_ipp_2011 if sp_model == "ipp_idw2" else None,
            tropo_mode=tr_mode,
            require_interior_hull=True,
        )
        val = validate_experimental_vrs_against_target(
            vrs, target_ds_2011, effective_interval_s=30.0 * args.stride
        )
        exp5a_variants[variant_name] = {
            "vrs_summary": vrs.summary_dict(),
            "held_out_validation": val,
        }
        if variant_name == "idw2_unb3m":
            vrs_2011_primary = vrs

    assert vrs_2011_primary is not None

    # =========================================================================
    # EXPERIMENT 5B: 2024-01-26 (DOY 026) Verified-IGS20 Target PHRI00NGA
    # =========================================================================
    dc = json.loads((data_root / "processed/single-base/derived-coordinates.json").read_text())
    p5_adm = json.loads(
        (data_root / "processed/network-rtk/experiments/net-2024d026-phri-rover/admission.json")
        .read_text()
    )
    coords_2024: dict[str, tuple[float, float, float]] = {}
    ds_2024_all: dict[str, StationDataset] = {}
    nav_2024_path: Path | None = None
    for s in p5_adm["admitted"]:
        sid = s["station_id"]
        if dc["stations"].get(sid, {}).get("scientifically_valid") is not True:
            continue
        e = dc["stations"][sid]["ecef"]
        coords_2024[sid] = (float(e["x_m"]), float(e["y_m"]), float(e["z_m"]))
        ds_2024_all[sid] = read_rinex2_observations(
            Path(s["observation_path"]), sid, stride=args.stride
        )
        if nav_2024_path is None:
            nav_2024_path = data_root / s["navigation_path"]

    assert nav_2024_path is not None
    target_2024 = "PHRI00NGA"
    ref_ds_2024 = {k: v for k, v in ds_2024_all.items() if k != target_2024}
    ref_coords_2024 = {k: coords_2024[k] for k in ref_ds_2024}
    target_ds_2024 = ds_2024_all[target_2024]
    target_ecef_2024 = coords_2024[target_2024]
    nav_2024 = parse_gps_nav_auto(nav_2024_path)
    nav_2024_hash = sha256_file(nav_2024_path)

    # Load PRIDE PPP-AR ZTD strictly for the 3 reference stations (zero target ZTD leakage)
    pride_ref_paths = {
        "ABFC00NGA": data_root / "working/pride-test/2024/026/ztd_2024026",
        "EKAK00NGA": data_root / "working/pride/run-EKAK00NGA/2024/026/ztd_2024026_ekak",
        "MGBO00NGA": data_root / "working/pride/run-MGBO00NGA/2024/026/ztd_2024026_mgbo",
    }
    ref_ztd_2024: dict[tuple[str, str], tuple[float, float]] = {}
    for sid, p in pride_ref_paths.items():
        if p.is_file():
            recs, _ = parse_pride_ztd(p, station_id=sid)
            for rec in recs:
                ref_ztd_2024[(sid, rec.epoch_iso)] = (rec.zhd_m, rec.zwd_total_m)

    iono_2024, ipp_2024, tgt_ipp_2024, iono_meta_2024 = _compute_ref_iono_field(
        ref_datasets=ref_ds_2024,
        ref_coords=ref_coords_2024,
        target_station=target_2024,
        target_ecef=target_ecef_2024,
        nav_records=nav_2024,
        nav_hash=nav_2024_hash,
        datum_station="EKAK00NGA",
        stride=args.stride,
    )

    exp5b_variants: dict[str, dict[str, Any]] = {}
    vrs_2024_primary: ExperimentalVrsResult | None = None
    for variant_name, sp_model, tr_mode in (
        ("zero_geom_only", "zero", "zero"),
        ("tropo_unb3m_only", "zero", "unb3m"),
        ("tropo_pride_ztd_only", "zero", "network_ztd"),
        ("idw2_pride_ztd", "idw2", "network_ztd"),
        ("planar_unb3m", "planar", "unb3m"),
    ):
        vrs = generate_experimental_vrs(
            experiment_id=f"2024-01-26-phri-{variant_name}",
            target_station_id=target_2024,
            target_ecef_m=target_ecef_2024,
            reference_coords=ref_coords_2024,
            reference_datasets=ref_ds_2024,
            nav_records=nav_2024,
            doy=26,
            reference_frame="IGS20",
            coordinate_epoch="2024.07",
            coordinate_provenance="VERIFIED_IGS20",
            spatial_model=sp_model,
            iono_field_by_key=iono_2024 if sp_model != "zero" else None,
            ipp_by_key=ipp_2024 if sp_model == "ipp_idw2" else None,
            target_ipp_by_epoch_sat=tgt_ipp_2024 if sp_model == "ipp_idw2" else None,
            ztd_by_station_epoch=ref_ztd_2024 if tr_mode == "network_ztd" else None,
            tropo_mode=tr_mode,
            require_interior_hull=False,
        )
        val = validate_experimental_vrs_against_target(
            vrs, target_ds_2024, effective_interval_s=30.0 * args.stride
        )
        exp5b_variants[variant_name] = {
            "vrs_summary": vrs.summary_dict(),
            "held_out_validation": val,
        }
        if variant_name == "idw2_pride_ztd":
            vrs_2024_primary = vrs

    assert vrs_2024_primary is not None

    # =========================================================================
    # EXPERIMENT 6: RTCM 1005 + 1074 Encoding & Multi-Decoder Verification
    # =========================================================================
    bundle_2011 = encode_experimental_vrs_to_rtcm(
        vrs_2011_primary,
        rtcm_station_id=2011,
        effective_interval_s=30.0 * args.stride,
        max_epochs=args.rtcm_epochs,
    )
    bundle_2024 = encode_experimental_vrs_to_rtcm(
        vrs_2024_primary,
        rtcm_station_id=2024,
        effective_interval_s=30.0 * args.stride,
        max_epochs=args.rtcm_epochs,
    )
    (out_dir / "vrs_2011_03_20_osgf_exp.rtcm3").write_bytes(bundle_2011.stream_bytes)
    (out_dir / "vrs_2024_01_26_phri_exp.rtcm3").write_bytes(bundle_2024.stream_bytes)

    rtcm_val_2011 = _verify_rtcm_bundle_with_decoders(
        bundle=bundle_2011,
        expected_ecef=target_ecef_2011,
        ref_date_slash="2011/03/20",
        ref_epoch_tuple=(2011, 3, 20, 0, 0, 0.0),
        rtklib_exe=rtklib_exe,
        glab_exe=glab_exe,
    )
    rtcm_val_2024 = _verify_rtcm_bundle_with_decoders(
        bundle=bundle_2024,
        expected_ecef=target_ecef_2024,
        ref_date_slash="2024/01/26",
        ref_epoch_tuple=(2024, 1, 26, 0, 0, 0.0),
        rtklib_exe=rtklib_exe,
        glab_exe=glab_exe,
    )

    # =========================================================================
    # EXPERIMENT 7: Isolated NTRIP Loopback Distribution (NLGCP_VRS_EXP)
    # =========================================================================
    assert vrs_2011_primary.target_coordinate is not None
    ntrip_exp7_2011 = _run_ntrip_loopback_experiment(
        bundle=bundle_2011,
        expected_ecef=target_ecef_2011,
        ref_date_slash="2011/03/20",
        ref_epoch_tuple=(2011, 3, 20, 0, 0, 0.0),
        rtklib_exe=rtklib_exe,
        glab_exe=glab_exe,
        target_lat_deg=vrs_2011_primary.target_coordinate.latitude_deg,
        target_lon_deg=vrs_2011_primary.target_coordinate.longitude_deg,
    )
    assert vrs_2024_primary.target_coordinate is not None
    ntrip_exp7_2024 = _run_ntrip_loopback_experiment(
        bundle=bundle_2024,
        expected_ecef=target_ecef_2024,
        ref_date_slash="2024/01/26",
        ref_epoch_tuple=(2024, 1, 26, 0, 0, 0.0),
        rtklib_exe=rtklib_exe,
        glab_exe=glab_exe,
        target_lat_deg=vrs_2024_primary.target_coordinate.latitude_deg,
        target_lon_deg=vrs_2024_primary.target_coordinate.longitude_deg,
    )

    # =========================================================================
    # EXPERIMENT 8: Failure-Mode & Boundary Security Verification (11 cases)
    # =========================================================================
    exp8_failures = _run_failure_mode_suite(
        ref_coords_2011=ref_coords_2011,
        ref_ds_2011=ref_ds_2011,
        target_ecef_2011=target_ecef_2011,
        nav_2011=nav_2011,
        iono_2011=iono_2011,
        ref_coords_2024=ref_coords_2024,
        ref_ds_2024=ref_ds_2024,
        target_ecef_2024=target_ecef_2024,
        nav_2024=nav_2024,
        bundle_2011=bundle_2011,
    )

    summary = {
        "generated_utc": utc_now_iso(),
        "stride": args.stride,
        "effective_interval_s": 30.0 * args.stride,
        "rtcm_epochs_encoded": args.rtcm_epochs,
        "operational_approved": False,
        "decoder_provenance": {
            "rtklib_convbin": conv_prov,
            "rtklib_native": rtklib_prov,
            "glab_v6_non_rtklib": glab_prov,
        },
        "experiment5a_2011_03_20_osgf_interior": {
            "target_station": target_2011,
            "coordinate_provenance": "PROVISIONAL_OSGOF_2011_01_01",
            "iono_field_meta": iono_meta_2011,
            "variants": exp5a_variants,
        },
        "experiment5b_2024_01_26_phri_verified_extrapolated": {
            "target_station": target_2024,
            "coordinate_provenance": "VERIFIED_IGS20",
            "iono_field_meta": iono_meta_2024,
            "variants": exp5b_variants,
        },
        "experiment6_rtcm_validation": {
            "2011_03_20_osgf_bundle": bundle_2011.summary_dict(),
            "2011_03_20_osgf_decoders": rtcm_val_2011,
            "2024_01_26_phri_bundle": bundle_2024.summary_dict(),
            "2024_01_26_phri_decoders": rtcm_val_2024,
        },
        "experiment7_ntrip_loopback": {
            "2011_03_20_osgf": ntrip_exp7_2011,
            "2024_01_26_phri": ntrip_exp7_2024,
        },
        "experiment8_failure_modes": exp8_failures,
    }
    _write_json(out_dir / "phase7_vrs_sprint_results.json", summary)

    print(f"Phase 7 sprint results written to {out_dir / 'phase7_vrs_sprint_results.json'}")
    print(
        f"Exp 6 2011 decoders: convbin={rtcm_val_2011['rtklib_convbin']['passed']}, "
        f"native={rtcm_val_2011['rtklib_native_input_rtcm3']['passed']}, "
        f"gLAB_1005={rtcm_val_2011['glab_v6_non_rtklib_cross_decoder']['non_rtklib_1005_and_crc24q_passed']}"
    )
    print(
        f"Exp 6 2024 decoders: convbin={rtcm_val_2024['rtklib_convbin']['passed']}, "
        f"native={rtcm_val_2024['rtklib_native_input_rtcm3']['passed']}, "
        f"gLAB_1005={rtcm_val_2024['glab_v6_non_rtklib_cross_decoder']['non_rtklib_1005_and_crc24q_passed']}"
    )
    print(
        f"Exp 7 NTRIP loopback: 2011_match={ntrip_exp7_2011['byte_exact_sha256_match']} "
        f"({ntrip_exp7_2011['frames_received_valid']} frames), "
        f"2024_match={ntrip_exp7_2024['byte_exact_sha256_match']} "
        f"({ntrip_exp7_2024['frames_received_valid']} frames)"
    )
    print(
        f"Exp 8 failure modes: {exp8_failures['total_scenarios']} scenarios, "
        f"all_passed={exp8_failures['all_passed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
