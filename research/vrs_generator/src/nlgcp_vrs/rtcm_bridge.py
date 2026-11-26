"""Phase 7 -> Phase 11/12 Experimental VRS RTCM bridge.

Converts an ``ExperimentalVrsResult`` into CRC-24Q-framed RTCM 3.x messages
(1005 Reference Station ARP + 1074 GPS MSM4) strictly reusing:
- Phase 11 ``ReferenceStation1005``, ``Msm4Message``, ``Msm4Cell`` (zero
  duplicate RTCM bit-level encoders);
- Phase 9 ``frame_rtcm()`` and ``crc24q()`` (zero duplicate CRC logic);
- Phase 11 ``CorrectionStreamArtifact`` handoff schema.

Carrier-phase integer-cycle alignment:
RTCM MSM4 fine phase range must lie within +/-1171.0 m of the satellite's
rough range.  Real RINEX carrier phases have arbitrary initial integer cycle
counts, so this bridge applies ONE fixed exact integer offset
``delta_n = round((P_init - L_init * lambda) / lambda)`` (an integer in Z) per
continuous satellite/frequency arc.  This preserves exact fractional phases,
epoch-to-epoch phase differences, and integer double-difference ambiguity
structure while transparently recording every applied integer offset.

All outputs are classified ``OutputClassification.RESEARCH_VALIDATION`` and
NEVER ``OPERATIONAL_APPROVED``.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from nlgcp_atmospheric_model.observations import GPS_L1_WAVELENGTH_M, GPS_L2_WAVELENGTH_M
from nlgcp_atmospheric_model.satellite_geometry import gps_datetime_to_tow
from nlgcp_rtcm_generation.handoff import CorrectionStreamArtifact
from nlgcp_rtcm_generation.messages import (
    FINE_PSEUDORANGE_LIMIT_M,
    Msm4Cell,
    Msm4Message,
    MsmSystem,
    ReferenceStation1005,
)
from nlgcp_rtcm_generation.models import (
    GeneratedCorrectionFrame,
    GenerationStatus,
    OutputClassification,
)
from nlgcp_rtcm_generation.provenance import fingerprint
from nlgcp_rtcm_replay.framing import encode_payload_frame

from nlgcp_vrs.experimental_vrs import (
    EXPERIMENTAL_VRS_VERSION,
    ExperimentalVrsObs,
    ExperimentalVrsResult,
    VrsOutcome,
)

VRS_RTCM_BRIDGE_VERSION = "phase7-rtcm-bridge-v1.0"
GPS_SIGNAL_1C = 2  # GPS L1 C/A (RINEX C1/L1)
GPS_SIGNAL_2P = 9  # GPS L2 P(Y) (RINEX P2/L2)
MAX_FINE_PHASE_REBASE_M = 900.0
MAX_P2_C1_SPREAD_M = FINE_PSEUDORANGE_LIMIT_M - 30.0


class VrsRtcmBridgeError(ValueError):
    """Raised when an experimental VRS result cannot be safely encoded into RTCM."""


@dataclass(frozen=True, slots=True)
class IntegerArcOffset:
    """Audit record for one exact integer-cycle carrier-phase alignment."""

    satellite_id: str
    signal_code: str
    arc_start_epoch: str
    delta_cycles: int


@dataclass(frozen=True, slots=True)
class ExperimentalVrsRtcmBundle:
    """Encoded RTCM 1005 + 1074 stream bundle for an experimental VRS run."""

    experiment_id: str
    virtual_station_id: str
    rtcm_station_id: int
    classification: OutputClassification
    operational_approved: bool
    frames: tuple[GeneratedCorrectionFrame, ...]
    artifact: CorrectionStreamArtifact
    stream_bytes: bytes
    stream_sha256: str
    integer_arc_offsets: tuple[IntegerArcOffset, ...]
    excluded_cells: dict[str, int] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "virtual_station_id": self.virtual_station_id,
            "rtcm_station_id": self.rtcm_station_id,
            "classification": str(self.classification),
            "operational_approved": self.operational_approved,
            "frame_count": len(self.frames),
            "message_numbers": sorted({f.message_number for f in self.frames}),
            "stream_bytes_len": len(self.stream_bytes),
            "stream_sha256": self.stream_sha256,
            "integer_arc_offset_count": len(self.integer_arc_offsets),
            "excluded_cells": dict(self.excluded_cells),
            "artifact": self.artifact.as_dict(),
            "provenance": dict(self.provenance),
        }


def _wrap_frame(
    *,
    payload: bytes,
    message_family: str,
    message_number: int,
    request_fp: str,
) -> GeneratedCorrectionFrame:
    raw = encode_payload_frame(payload)
    crc_hex = raw[-3:].hex()
    return GeneratedCorrectionFrame(
        message_family=message_family,
        message_number=message_number,
        payload_length=len(payload),
        frame_length=len(raw),
        crc_hex=crc_hex,
        frame_sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes=raw,
        request_fingerprint=request_fp,
        encoder_version=f"{VRS_RTCM_BRIDGE_VERSION}+phase11-messages",
        input_status="AUTHENTIC_HISTORICAL_EXPERIMENTAL_VRS",
        classification=OutputClassification.RESEARCH_VALIDATION,
        scientific_status="EXPERIMENTAL_RESEARCH_ONLY_NOT_OPERATIONALLY_APPROVED",
    )


def _sanitized_cnr(value: float | None) -> float:
    if value is None or value < 0.0:
        return 0.0
    return min(63.0, value)


def encode_experimental_vrs_to_rtcm(
    vrs: ExperimentalVrsResult,
    *,
    rtcm_station_id: int = 2001,
    itrf_realization_year: int = 0,
    effective_interval_s: float = 30.0,
    max_epochs: int | None = None,
) -> ExperimentalVrsRtcmBundle:
    """Encode an ``ExperimentalVrsResult`` into RTCM 1005 + 1074 frames.

    Strictly refuses blocked VRS results or operational promotion.
    """
    if vrs.operational_approved:
        raise VrsRtcmBridgeError("operational VRS encoding is strictly forbidden")
    if vrs.outcome != VrsOutcome.EXPERIMENTAL_VRS_GENERATED:
        raise VrsRtcmBridgeError(
            f"cannot encode experimental VRS with outcome={vrs.outcome}"
        )
    if vrs.target_coordinate is None or not vrs.observations:
        raise VrsRtcmBridgeError("experimental VRS has no validated coordinate or observations")
    if not 0 <= rtcm_station_id <= 4095:
        raise VrsRtcmBridgeError(f"rtcm_station_id {rtcm_station_id} outside [0, 4095]")

    by_epoch: dict[str, list[ExperimentalVrsObs]] = defaultdict(list)
    for obs in vrs.observations:
        by_epoch[obs.epoch_iso].append(obs)
    epochs = sorted(by_epoch)
    if max_epochs is not None and max_epochs > 0:
        epochs = epochs[:max_epochs]

    prov_payload: dict[str, Any] = {
        "bridge_version": VRS_RTCM_BRIDGE_VERSION,
        "vrs_version": EXPERIMENTAL_VRS_VERSION,
        "experiment_id": vrs.experiment_id,
        "virtual_station_id": vrs.virtual_station_id,
        "rtcm_station_id": rtcm_station_id,
        "anchor_station": vrs.anchor_station,
        "reference_stations": list(vrs.reference_stations),
        "atmospheric_model": vrs.atmospheric_model,
        "coordinate_provenance": vrs.target_coordinate.provenance_status,
        "reference_frame": vrs.target_coordinate.reference_frame,
        "inside_convex_hull": vrs.inside_convex_hull,
        "epochs_encoded": len(epochs),
    }
    req_fp = fingerprint(prov_payload)

    # RTCM 1005: Reference-Station Indicator = True explicitly flags a computed/non-physical VRS.
    msg_1005 = ReferenceStation1005(
        station_id=rtcm_station_id,
        itrf_realization_year=itrf_realization_year,
        gps_indicator=True,
        glonass_indicator=False,
        galileo_indicator=False,
        reference_station_indicator=True,
        ecef_x_m=vrs.target_coordinate.ecef_xyz_m[0],
        ecef_y_m=vrs.target_coordinate.ecef_xyz_m[1],
        ecef_z_m=vrs.target_coordinate.ecef_xyz_m[2],
        oscillator_indicator=True,
        quarter_cycle_indicator=0,
    )
    frames: list[GeneratedCorrectionFrame] = [
        _wrap_frame(
            payload=msg_1005.encode(),
            message_family="REFERENCE_STATION_1005",
            message_number=1005,
            request_fp=req_fp,
        )
    ]

    # Per-(sat, signal) continuous arc state: (delta_n_cycles, last_epoch_dt, lock_time_s)
    arc_state: dict[tuple[str, str], tuple[int, datetime, float]] = {}
    arc_records: list[IntegerArcOffset] = []
    excluded: dict[str, int] = defaultdict(int)

    for ep_iso in epochs:
        moment = datetime.fromisoformat(ep_iso)
        _week, tow_s = gps_datetime_to_tow(moment)
        epoch_ms = int(round(tow_s * 1000.0)) % 604_800_000
        cells: list[Msm4Cell] = []

        for obs in sorted(by_epoch[ep_iso], key=lambda o: o.satellite_id):
            if not obs.satellite_id.startswith("G"):
                excluded["non_gps_skipped"] += 1
                continue
            prn = int(obs.satellite_id[1:])
            if abs(obs.p2_m - obs.c1_m) > MAX_P2_C1_SPREAD_M:
                excluded["p2_c1_fine_range_exceeded"] += 1
                continue

            # Align L1 and L2 with exact integer cycle offsets per continuous arc.
            aligned: list[tuple[int, float, float, float, float]] = []
            for sig_code, sig_id, pr_m, phase_cyc, wl_m, lli, cnr in (
                (
                    "1C",
                    GPS_SIGNAL_1C,
                    obs.c1_m,
                    obs.l1_cycles,
                    GPS_L1_WAVELENGTH_M,
                    obs.source_l1_lli,
                    obs.s1_dbhz,
                ),
                (
                    "2P",
                    GPS_SIGNAL_2P,
                    obs.p2_m,
                    obs.l2_cycles,
                    GPS_L2_WAVELENGTH_M,
                    obs.source_l2_lli,
                    obs.s2_dbhz,
                ),
            ):
                key = (obs.satellite_id, sig_code)
                prev = arc_state.get(key)
                slip = bool(lli & 1)
                if prev is not None and not slip:
                    delta_n, prev_dt, prev_lock = prev
                    dt_s = (moment - prev_dt).total_seconds()
                    if 0.0 < dt_s <= max(effective_interval_s * 2.5, 90.0):
                        phase_m = (phase_cyc + delta_n) * wl_m
                        if abs(phase_m - obs.c1_m) <= MAX_FINE_PHASE_REBASE_M:
                            lock_s = prev_lock + dt_s
                            arc_state[key] = (delta_n, moment, lock_s)
                            aligned.append((sig_id, pr_m, phase_m, lock_s, _sanitized_cnr(cnr)))
                            continue
                # Start new continuous arc with exact integer cycle offset.
                delta_n = round((pr_m - phase_cyc * wl_m) / wl_m)
                phase_m = (phase_cyc + delta_n) * wl_m
                arc_state[key] = (delta_n, moment, 0.0)
                arc_records.append(
                    IntegerArcOffset(
                        satellite_id=obs.satellite_id,
                        signal_code=sig_code,
                        arc_start_epoch=ep_iso,
                        delta_cycles=delta_n,
                    )
                )
                aligned.append((sig_id, pr_m, phase_m, 0.0, _sanitized_cnr(cnr)))

            for sig_id, pr_m, phase_m, lock_s, cnr_val in aligned:
                cells.append(
                    Msm4Cell(
                        satellite_id=prn,
                        signal_id=sig_id,
                        pseudorange_m=pr_m,
                        phase_range_m=phase_m,
                        lock_time_s=lock_s,
                        half_cycle_ambiguity=False,
                        cnr_dbhz=cnr_val,
                    )
                )

        if not cells:
            excluded["empty_epoch_skipped"] += 1
            continue
        msg_1074 = Msm4Message(
            system=MsmSystem.GPS,
            station_id=rtcm_station_id,
            epoch=epoch_ms,
            multiple_message=False,
            iod=0,
            clock_steering=0,
            external_clock=0,
            smoothing=False,
            smoothing_interval=0,
            cells=tuple(cells),
        )
        frames.append(
            _wrap_frame(
                payload=msg_1074.encode(),
                message_family="MSM4_GPS_1074",
                message_number=1074,
                request_fp=req_fp,
            )
        )

    if len(frames) < 2:
        raise VrsRtcmBridgeError("no RTCM 1074 observation epochs survived MSM4 encoding gates")

    stream_bytes = b"".join(f.raw_bytes for f in frames)
    stream_sha = hashlib.sha256(stream_bytes).hexdigest()
    prov_payload["frame_count"] = len(frames)
    prov_payload["stream_sha256"] = stream_sha
    prov_payload["integer_arc_offset_count"] = len(arc_records)
    prov_fp = fingerprint(prov_payload)

    artifact = CorrectionStreamArtifact(
        schema_version="nlgcp.correction_stream.v1",
        stream_id=f"vrs-exp-{vrs.experiment_id}-{stream_sha[:12]}",
        decision_id=f"experimental-vrs-{vrs.experiment_id}",
        mode="VRS_EXPERIMENTAL",
        station_id=vrs.anchor_station,
        virtual_station_id=vrs.virtual_station_id,
        message_families=("REFERENCE_STATION_1005", "MSM4_GPS_1074"),
        generation_status=str(GenerationStatus.ENCODED),
        frame_source=f"phase7:{VRS_RTCM_BRIDGE_VERSION}",
        validity_start=epochs[0],
        validity_end=epochs[-1],
        classification=str(OutputClassification.RESEARCH_VALIDATION),
        provenance_fingerprint=prov_fp,
    )
    return ExperimentalVrsRtcmBundle(
        experiment_id=vrs.experiment_id,
        virtual_station_id=vrs.virtual_station_id,
        rtcm_station_id=rtcm_station_id,
        classification=OutputClassification.RESEARCH_VALIDATION,
        operational_approved=False,
        frames=tuple(frames),
        artifact=artifact,
        stream_bytes=stream_bytes,
        stream_sha256=stream_sha,
        integer_arc_offsets=tuple(arc_records),
        excluded_cells=dict(sorted(excluded.items())),
        provenance=prov_payload,
    )
