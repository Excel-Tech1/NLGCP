"""End-to-end synthetic Phase 11 -> Phase 12 -> RTKLIB lab pipeline.

SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.

Connects the existing Phase 11 RTCM 1005/1074/1084 encoders to the local
loopback NTRIP caster (``NLGCP_TEST``), streams frames to an authenticated
local NTRIP client, validates CRC-24Q on reception, and optionally decodes
received frames through unmodified RTKLIB (``convbin`` and/or native
``input_rtcm3``).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nlgcp_ntrip_ingest.backoff import ReconnectPolicy
from nlgcp_rtcm_generation import ENCODER_VERSION_1005, ENCODER_VERSION_MSM4
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.independent_decoder import (
    IndependentDecoderUnavailable,
    build_rtklib_decoder,
    convbin_provenance,
    decode_with_convbin,
    decode_with_rtklib_native,
    locate_convbin,
)
from nlgcp_rtcm_generation.models import (
    CoordinateProvenance,
    CorrectionGenerationRequest,
    CorrectionGenerationResult,
    EpochContract,
    GenerationMode,
    GenerationStatus,
    OutputClassification,
    VerificationState,
)
from nlgcp_rtcm_generation.validation import validate_frame

from nlgcp_correction_service import (
    DEFAULT_MOUNTPOINT,
    LOOPBACK_HOST,
    SCIENTIFIC_READINESS_STATUS,
    SYNTHETIC_MOUNTPOINT_LABEL,
)
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.client import ClientReceiveResult, LocalNtripClient
from nlgcp_correction_service.config import CasterConfig, ClientConfig

# Deterministic synthetic fixtures (same canonical vectors as Day 2/Day 3).
# SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.
LAB_SYNTHETIC_1005_FIELDS: dict[str, object] = {
    "station_id": 1234,
    "itrf_realization_year": 0,
    "gps_indicator": True,
    "glonass_indicator": True,
    "galileo_indicator": False,
    "reference_station_indicator": False,
    "ecef_x_m": 111111.1111,
    "ecef_y_m": -222222.2222,
    "ecef_z_m": 3333333.3333,
    "oscillator_indicator": True,
    "quarter_cycle_indicator": 0,
}

LAB_SYNTHETIC_GPS_HEADER: dict[str, object] = {
    "station_id": 1234,
    "epoch_ms": 345_600_123,
    "multiple_message": False,
    "iod": 2,
    "clock_steering": 0,
    "external_clock": 0,
    "smoothing": False,
    "smoothing_interval": 0,
}

LAB_SYNTHETIC_GPS_CELLS: tuple[dict[str, object], ...] = (
    {
        "satellite_id": 1,
        "signal_id": 2,
        "pseudorange_m": 20_000_000.0,
        "phase_range_m": 20_000_050.0,
        "lock_time_s": 1.5,
        "half_cycle_ambiguity": False,
        "cnr_dbhz": 45.0,
    },
    {
        "satellite_id": 2,
        "signal_id": 2,
        "pseudorange_m": 21_000_000.0,
        "phase_range_m": 21_000_050.0,
        "lock_time_s": 3.0,
        "half_cycle_ambiguity": True,
        "cnr_dbhz": 40.0,
    },
    {
        "satellite_id": 3,
        "signal_id": 9,
        "pseudorange_m": 22_000_000.0,
        "phase_range_m": 22_000_050.0,
        "lock_time_s": 10.0,
        "half_cycle_ambiguity": False,
        "cnr_dbhz": 30.0,
    },
)

LAB_SYNTHETIC_GLONASS_HEADER: dict[str, object] = {
    "station_id": 3210,
    "epoch_dow": 3,
    "epoch_tod_ms": 45_296_789,
    "multiple_message": False,
    "iod": 5,
    "clock_steering": 1,
    "external_clock": 2,
    "smoothing": True,
    "smoothing_interval": 4,
}

LAB_SYNTHETIC_GLONASS_CELLS: tuple[dict[str, object], ...] = (
    {
        "satellite_id": 1,
        "signal_id": 2,
        "pseudorange_m": 19_100_000.0,
        "phase_range_m": 19_100_040.0,
        "lock_time_s": 0.25,
        "half_cycle_ambiguity": False,
        "cnr_dbhz": 50.0,
    },
    {
        "satellite_id": 1,
        "signal_id": 8,
        "pseudorange_m": 19_100_004.0,
        "phase_range_m": 19_100_044.0,
        "lock_time_s": 0.25,
        "half_cycle_ambiguity": False,
        "cnr_dbhz": 49.0,
    },
    {
        "satellite_id": 2,
        "signal_id": 2,
        "pseudorange_m": 20_500_000.0,
        "phase_range_m": 20_500_040.0,
        "lock_time_s": 2.5,
        "half_cycle_ambiguity": True,
        "cnr_dbhz": 42.0,
    },
    {
        "satellite_id": 2,
        "signal_id": 8,
        "pseudorange_m": 20_500_006.0,
        "phase_range_m": 20_500_046.0,
        "lock_time_s": 2.5,
        "half_cycle_ambiguity": False,
        "cnr_dbhz": 41.0,
    },
)


def _synthetic_phase11_request(
    *, request_id: str, family: str, encoder_version: str
) -> CorrectionGenerationRequest:
    coordinate = CoordinateProvenance(
        station_id="SYNA00SYN",
        ecef_xyz_m=(111111.1111, -222222.2222, 3333333.3333),
        reference_frame="SYNTHETIC_FRAME",
        coordinate_epoch="2026-01-01T00:00:00Z",
        source=SYNTHETIC_MOUNTPOINT_LABEL,
        fingerprint="phase12-synthetic-coord-fp",
        verification_state=VerificationState.SYNTHETIC_TEST_ONLY,
    )
    return CorrectionGenerationRequest(
        request_id=request_id,
        decision_id="phase12-synthetic-decision-001",
        decision_fingerprint="phase12-synthetic-decision-fp",
        decision_status="OK",
        mode=GenerationMode.SINGLE_BASE,
        reference_station_id="SYNA00SYN",
        virtual_station_id=None,
        coordinate=coordinate,
        epoch=EpochContract("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.100Z"),
        gnss_systems=("GLONASS",) if family == "MSM4_GLONASS_1084" else ("GPS",),
        input_source_fingerprint="phase12-synthetic-input-fp",
        input_source_admitted=True,
        station_identity_verified=True,
        coordinate_verified=True,
        correction_model_fingerprint="phase12-synthetic-model-fp",
        correction_model_approved=True,
        output_message_family=family,
        encoder_version=encoder_version,
        scientific_status="SYNTHETIC_TEST_ONLY",
        classification=OutputClassification.SYNTHETIC_TEST_ONLY,
        synthetic_fixture=True,
    )


def generate_phase11_synthetic_bundle() -> tuple[CorrectionGenerationResult, ...]:
    """Generate and Phase-9-validate synthetic 1005, 1074, and 1084 frames via Phase 11."""
    generator = CorrectionGenerator()
    specs: tuple[
        tuple[str, str, str, dict[str, object], tuple[dict[str, object], ...]], ...
    ] = (
        (
            "p12-req-1005",
            "REFERENCE_STATION_1005",
            ENCODER_VERSION_1005,
            dict(LAB_SYNTHETIC_1005_FIELDS),
            (),
        ),
        (
            "p12-req-1074",
            "MSM4_GPS_1074",
            ENCODER_VERSION_MSM4,
            dict(LAB_SYNTHETIC_GPS_HEADER),
            LAB_SYNTHETIC_GPS_CELLS,
        ),
        (
            "p12-req-1084",
            "MSM4_GLONASS_1084",
            ENCODER_VERSION_MSM4,
            dict(LAB_SYNTHETIC_GLONASS_HEADER),
            LAB_SYNTHETIC_GLONASS_CELLS,
        ),
    )
    results: list[CorrectionGenerationResult] = []
    for req_id, family, version, fields, obs in specs:
        req = _synthetic_phase11_request(
            request_id=req_id, family=family, encoder_version=version
        )
        res = generator.generate(req, fields=fields, observations=obs)
        if res.status != GenerationStatus.ENCODED or len(res.frames) != 1:
            raise RuntimeError(f"Phase 11 failed to encode {family}: {res.reason_codes}")
        check = validate_frame(res.frames[0])
        if not (check.framing_valid and check.phase9_compatible):
            raise RuntimeError(f"Phase 9 framing check failed for {family}: {check.findings}")
        results.append(res)
    return tuple(results)


@dataclass(frozen=True, slots=True)
class EndToEndDemoReport:
    ok: bool
    mountpoint: str
    sent_message_numbers: tuple[int, ...]
    received_message_numbers: tuple[int, ...]
    byte_exact_match: bool
    caster_diagnostics: dict[str, Any]
    client_result: ClientReceiveResult
    rtklib_validation: dict[str, Any]
    scientific_readiness: str
    stages: dict[str, Any] = field(default_factory=dict)


def run_local_end_to_end_demo(
    *,
    ntrip_version: str = "2.0",
    mountpoint: str = DEFAULT_MOUNTPOINT,
    rtklib_source: Path | None = None,
    repo_root: Path | None = None,
) -> EndToEndDemoReport:
    """Execute the full local synthetic Phase 11 -> Phase 12 -> RTKLIB pipeline."""
    # Ephemeral per-run credentials; never hardcoded, never logged.
    ephemeral_user = "lab_client"
    ephemeral_pass = secrets.token_urlsafe(16)

    phase11_results = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()

    caster_cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=mountpoint,
        client_credentials={ephemeral_user: ephemeral_pass},
    )
    caster = LocalNtripCaster(caster_cfg)
    with caster:
        caster_started = caster.is_running and caster.host == LOOPBACK_HOST and caster.port > 0
        published_count = 0
        for res in phase11_results:
            artifact = generator.handoff(res)
            published = caster.publish_phase11_result(
                res, mountpoint=mountpoint, artifact=artifact
            )
            published_count += len(published)

        client_cfg = ClientConfig(
            host=LOOPBACK_HOST,
            port=caster.port,
            mountpoint=mountpoint,
            username=ephemeral_user,
            password=ephemeral_pass,
            ntrip_version=ntrip_version,
            reconnect_policy=ReconnectPolicy(
                base_delay_s=0.05, max_delay_s=0.2, max_attempts=2
            ),
        )
        client = LocalNtripClient(client_cfg)
        st_code, st_body = client.fetch_sourcetable()
        mountpoint_available = (
            st_code == 200
            and f"STR;{mountpoint};" in st_body
            and "ENDSOURCETABLE" in st_body
        )
        client_res = client.receive_frames(max_frames=len(phase11_results))
        caster_snap = caster.status_snapshot()

    post_shutdown_snap = caster.status_snapshot()
    clean_shutdown = (
        not caster.is_running
        and post_shutdown_snap["caster_status"] == "STOPPED"
        and post_shutdown_snap["active_clients"] == 0
    )

    sent_raw = [r.frames[0].raw_bytes for r in phase11_results]
    recv_raw = [f.raw for f in client_res.valid_frames]
    byte_exact = sent_raw == recv_raw

    rtklib_summary: dict[str, Any] = {
        "convbin_performed": False,
        "native_input_rtcm3_performed": False,
    }
    if byte_exact and len(recv_raw) == 3:
        try:
            convbin_bin = locate_convbin()
            conv_1005_1074 = decode_with_convbin(
                recv_raw[0] + recv_raw[1], binary=convbin_bin
            )
            conv_1084 = decode_with_convbin(recv_raw[2], binary=convbin_bin)
            rtklib_summary["convbin_performed"] = True
            rtklib_summary["convbin_provenance"] = convbin_provenance(convbin_bin)
            rtklib_summary["convbin_1005_xyz"] = conv_1005_1074.approx_position_xyz
            rtklib_summary["convbin_1074_obs_types"] = conv_1005_1074.sys_obs_types.get("G")
            rtklib_summary["convbin_1084_obs_types"] = conv_1084.sys_obs_types.get("R")
        except IndependentDecoderUnavailable as exc:
            rtklib_summary["convbin_unavailable_reason"] = str(exc)

        if rtklib_source is not None and repo_root is not None:
            try:
                exe, prov = build_rtklib_decoder(repo_root, rtklib_source)
                dec_1005 = decode_with_rtklib_native(exe, recv_raw[0])
                dec_1074 = decode_with_rtklib_native(exe, recv_raw[1])
                dec_1084 = decode_with_rtklib_native(exe, recv_raw[2])
                rtklib_summary["native_input_rtcm3_performed"] = True
                rtklib_summary["native_provenance"] = prov
                rtklib_summary["native_1005_ecef"] = dec_1005["events"][0]["pos_ecef"]
                rtklib_summary["native_1074_msmtype"] = dec_1074["events"][0]["msmtype_gps"]
                rtklib_summary["native_1084_msmtype"] = dec_1084["events"][0]["msmtype_glo"]
            except IndependentDecoderUnavailable as exc:
                rtklib_summary["native_unavailable_reason"] = str(exc)

    sent_nums = tuple(r.frames[0].message_number for r in phase11_results)
    recv_nums = tuple(
        f.message_number for f in client_res.valid_frames if f.message_number is not None
    )
    crc_valid = (
        len(client_res.invalid_frames) == 0
        and client_res.diagnostics["crc_failures"] == 0
        and caster_snap["crc_failures"] == 0
        and len(client_res.valid_frames) == len(phase11_results)
    )
    stages: dict[str, Any] = {
        "caster_startup": {
            "ok": caster_started,
            "bind_host": caster_snap["listen_host"],
            "bind_port": caster_snap["listen_port"],
        },
        "mountpoint_availability": {
            "ok": mountpoint_available,
            "mountpoint": mountpoint,
            "sourcetable_status": st_code,
        },
        "authentication": {
            "ok": client_res.status_code == 200
            and caster_snap["authenticated_clients_total"] == 1
            and caster_snap["failed_auth_attempts"] == 0,
            "status_code": client_res.status_code,
            "ntrip_version": ntrip_version,
        },
        "rtcm_publication": {
            "ok": published_count == len(phase11_results),
            "published_frames": published_count,
            "message_numbers": list(sent_nums),
        },
        "client_reception": {
            "ok": client_res.ok and len(client_res.valid_frames) == len(phase11_results),
            "received_frames": len(client_res.valid_frames),
            "bytes_received": client_res.diagnostics["bytes_received"],
        },
        "byte_exact_comparison": {
            "ok": byte_exact,
            "sent_bytes": sum(len(b) for b in sent_raw),
            "received_bytes": sum(len(b) for b in recv_raw),
        },
        "crc_validation": {
            "ok": crc_valid,
            "caster_crc_failures": caster_snap["crc_failures"],
            "client_crc_failures": client_res.diagnostics["crc_failures"],
        },
        "message_type_identification": {
            "ok": sent_nums == recv_nums,
            "expected": list(sent_nums),
            "observed": list(recv_nums),
        },
        "independent_rtklib_decoding": {
            "convbin_performed": rtklib_summary["convbin_performed"],
            "native_input_rtcm3_performed": rtklib_summary["native_input_rtcm3_performed"],
        },
        "clean_shutdown": {
            "ok": clean_shutdown,
            "caster_status": post_shutdown_snap["caster_status"],
            "active_clients": post_shutdown_snap["active_clients"],
        },
    }
    overall_ok = (
        caster_started
        and mountpoint_available
        and client_res.ok
        and byte_exact
        and crc_valid
        and sent_nums == recv_nums
        and clean_shutdown
    )
    return EndToEndDemoReport(
        ok=overall_ok,
        mountpoint=mountpoint,
        sent_message_numbers=sent_nums,
        received_message_numbers=recv_nums,
        byte_exact_match=byte_exact,
        caster_diagnostics=caster_snap,
        client_result=client_res,
        rtklib_validation=rtklib_summary,
        scientific_readiness=SCIENTIFIC_READINESS_STATUS,
        stages=stages,
    )
