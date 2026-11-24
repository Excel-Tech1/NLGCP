"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Bit-level tests for the RTCM 1005, 1074 and 1084 encoders.  The fixture
coordinates, station IDs and observations are deterministic synthetic
values.  They are not NIGNET station coordinates, not measured carrier
phase, and not usable corrections.

Expected payload and frame hex strings were produced independently with a
separate bit-string packer implementing the documented RTKLIB layout.  The
same vectors are also checked against explicit field offsets with an
independent bit reader.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from nlgcp_rtcm_generation import ENCODER_VERSION_1005, ENCODER_VERSION_MSM4
from nlgcp_rtcm_generation.framing import frame_message_payload
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.messages import (
    GLONASS_MSM_SIGNAL_IDS,
    GPS_MSM_SIGNAL_IDS,
    MAX_MSM_CELLS,
    RANGE_MS,
    MessageInputError,
    Msm4Cell,
    Msm4Message,
    MsmSystem,
    ReferenceStation1005,
)
from nlgcp_rtcm_generation.models import (
    CorrectionGenerationRequest,
    EpochContract,
    GenerationMode,
    GenerationStatus,
    OutputClassification,
    ReasonCode,
    VerificationState,
)
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry
from nlgcp_rtcm_generation.validation import validate_frame

SYNTHETIC_STATION_1005 = 1234
SYNTHETIC_STATION_GPS = 1234
SYNTHETIC_STATION_GLONASS = 3210

SYNTHETIC_1005_FIELDS: dict[str, object] = {
    "station_id": SYNTHETIC_STATION_1005,
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

SYNTHETIC_GPS_HEADER: dict[str, object] = {
    "station_id": SYNTHETIC_STATION_GPS,
    "epoch_ms": 345600123,
    "multiple_message": False,
    "iod": 2,
    "clock_steering": 0,
    "external_clock": 0,
    "smoothing": False,
    "smoothing_interval": 0,
}

SYNTHETIC_GPS_CELLS: tuple[dict[str, object], ...] = (
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

SYNTHETIC_GLONASS_HEADER: dict[str, object] = {
    "station_id": SYNTHETIC_STATION_GLONASS,
    "epoch_dow": 3,
    "epoch_tod_ms": 45_296_789,
    "multiple_message": True,
    "iod": 5,
    "clock_steering": 1,
    "external_clock": 2,
    "smoothing": True,
    "smoothing_interval": 4,
}

SYNTHETIC_GLONASS_CELLS: tuple[dict[str, object], ...] = (
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

EXPECTED_1005_PAYLOAD = "3ed4d20300423a35c7bf7b8b947207c2d24d55"
EXPECTED_1005_FRAME = "d300133ed4d20300423a35c7bf7b8b947207c2d24d555f8fb0"
EXPECTED_1074_PAYLOAD = (
    "4324d25265c1ec800070000000000000002040000052848c936d064c4fb4fcfc051c00c7a4f"
    "966f03ebd467956d0f0"
)
EXPECTED_1074_FRAME = (
    "d3002f4324d25265c1ec800070000000000000002040000052848c936d064c4fb4fcfc051c0"
    "0c7a4f966f03ebd467956d0f0c0396f"
)
EXPECTED_1084_PAYLOAD = (
    "43cc8a6accb257403660000000000000002080000079fa25b0c37333e827c65f973fefc69fcd"
    "17fe9579fba5a99bb9658d5480"
)
EXPECTED_1084_FRAME = (
    "d3003343cc8a6accb257403660000000000000002080000079fa25b0c37333e827c65f973fef"
    "c69fcd17fe9579fba5a99bb9658d5480787e97"
)


def read_bits(data: bytes, start: int, length: int) -> int:
    value = 0
    for position in range(start, start + length):
        value = (value << 1) | ((data[position // 8] >> (7 - position % 8)) & 1)
    return value


def read_signed(data: bytes, start: int, length: int) -> int:
    value = read_bits(data, start, length)
    return value - (1 << length) if value & (1 << (length - 1)) else value


def payload_of(frame: bytes) -> bytes:
    return frame[3:-3]


def synthetic_request(
    *,
    family: str,
    encoder_version: str,
    mode: GenerationMode = GenerationMode.SINGLE_BASE,
) -> CorrectionGenerationRequest:
    from nlgcp_rtcm_generation.models import CoordinateProvenance

    coordinate = CoordinateProvenance(
        station_id="SYNA00SYN",
        ecef_xyz_m=(1.0, 2.0, 3.0),
        reference_frame="SYNTHETIC_FRAME",
        coordinate_epoch="2026-01-01T00:00:00Z",
        source="SYNTHETIC TEST DATA",
        fingerprint="synthetic-coordinate-fp",
        verification_state=VerificationState.SYNTHETIC_TEST_ONLY,
    )
    return CorrectionGenerationRequest(
        request_id="request-rtcm-syn-001",
        decision_id="decision-rtcm-syn-001",
        decision_fingerprint="decision-fp",
        decision_status="OK",
        mode=mode,
        reference_station_id="SYNA00SYN",
        virtual_station_id=None,
        coordinate=coordinate,
        epoch=EpochContract("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.100Z"),
        gnss_systems=("GPS",)
        if family != "MSM4_GLONASS_1084"
        else ("GLONASS",),
        input_source_fingerprint="synthetic-input-fp",
        input_source_admitted=True,
        station_identity_verified=True,
        coordinate_verified=True,
        correction_model_fingerprint="synthetic-model-fp",
        correction_model_approved=True,
        output_message_family=family,
        encoder_version=encoder_version,
        scientific_status="SYNTHETIC_TEST_ONLY",
        classification=OutputClassification.SYNTHETIC_TEST_ONLY,
        synthetic_fixture=True,
    )


def gps_message() -> Msm4Message:
    return Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, SYNTHETIC_GPS_CELLS)


def glonass_message() -> Msm4Message:
    return Msm4Message.from_mapping(
        MsmSystem.GLONASS, SYNTHETIC_GLONASS_HEADER, SYNTHETIC_GLONASS_CELLS
    )


def test_1005_payload_and_frame_match_independent_vectors() -> None:
    payload = ReferenceStation1005.from_mapping(SYNTHETIC_1005_FIELDS).encode()
    assert payload.hex() == EXPECTED_1005_PAYLOAD
    assert len(payload) == 19
    frame = frame_message_payload(payload)
    assert frame.hex() == EXPECTED_1005_FRAME
    assert len(frame) == 25
    assert frame[0] == 0xD3
    assert read_bits(frame, 14, 10) == 19
    assert read_bits(frame, 24, 12) == 1005
    assert payload_of(frame) == payload


def test_1005_bit_field_placement_and_signedness() -> None:
    frame = frame_message_payload(
        ReferenceStation1005.from_mapping(SYNTHETIC_1005_FIELDS).encode()
    )
    assert read_bits(frame, 24, 12) == 1005
    assert read_bits(frame, 36, 12) == SYNTHETIC_STATION_1005
    assert read_bits(frame, 48, 6) == 0
    assert read_bits(frame, 54, 1) == 1
    assert read_bits(frame, 55, 1) == 1
    assert read_bits(frame, 56, 1) == 0
    assert read_bits(frame, 57, 1) == 0
    assert read_signed(frame, 58, 38) == 1111111111
    assert read_bits(frame, 96, 1) == 1
    assert read_bits(frame, 97, 1) == 0
    assert read_signed(frame, 98, 38) == -2222222222
    assert read_bits(frame, 136, 2) == 0
    assert read_signed(frame, 138, 38) == 33333333333


@pytest.mark.parametrize(
    ("x", "y", "z", "x_code", "y_code", "z_code"),
    [
        (1.0, -1.0, 0.0, 10_000, -10_000, 0),
        (-1.0, 1.0, -0.0001, -10_000, 10_000, -1),
        (
            13_743_895.3471,
            -13_743_895.3472,
            0.0001,
            137_438_953_471,
            -137_438_953_472,
            1,
        ),
    ],
)
def test_1005_positive_negative_and_boundary_coordinates(
    x: float, y: float, z: float, x_code: int, y_code: int, z_code: int
) -> None:
    fields = dict(SYNTHETIC_1005_FIELDS)
    fields.update({"ecef_x_m": x, "ecef_y_m": y, "ecef_z_m": z})
    frame = frame_message_payload(ReferenceStation1005.from_mapping(fields).encode())
    assert read_signed(frame, 58, 38) == x_code
    assert read_signed(frame, 98, 38) == y_code
    assert read_signed(frame, 138, 38) == z_code


def test_1005_quantisation_is_rtklib_half_up() -> None:
    fields = dict(SYNTHETIC_1005_FIELDS)
    fields.update(
        {
            "ecef_x_m": 0.00005,
            "ecef_y_m": -0.00005,
            "ecef_z_m": 0.00025,
        }
    )
    frame = frame_message_payload(ReferenceStation1005.from_mapping(fields).encode())
    assert read_signed(frame, 58, 38) == 1
    assert read_signed(frame, 98, 38) == 0
    assert read_signed(frame, 138, 38) == 3


@pytest.mark.parametrize(
    ("updates", "missing"),
    [
        ({"station_id": -1}, False),
        ({"station_id": 4096}, False),
        ({"station_id": True}, False),
        ({"station_id": 1.0}, False),
        ({"itrf_realization_year": 64}, False),
        ({"gps_indicator": 2}, False),
        ({"quarter_cycle_indicator": 4}, False),
        ({"ecef_x_m": float("nan")}, False),
        ({"ecef_y_m": float("inf")}, False),
        ({"ecef_z_m": 13743895.3473}, False),
        ({"ecef_z_m": -13743895.3473}, False),
    ],
)
def test_1005_rejects_unrepresentable_fields(
    updates: dict[str, Any], missing: bool
) -> None:
    fields = dict(SYNTHETIC_1005_FIELDS)
    fields.update(updates)
    with pytest.raises(MessageInputError) as excinfo:
        ReferenceStation1005.from_mapping(fields)
    assert excinfo.value.missing is missing


def test_1005_rejects_missing_and_unknown_fields() -> None:
    fields = dict(SYNTHETIC_1005_FIELDS)
    del fields["ecef_x_m"]
    with pytest.raises(MessageInputError) as excinfo:
        ReferenceStation1005.from_mapping(fields)
    assert excinfo.value.missing
    fields = dict(SYNTHETIC_1005_FIELDS)
    fields["unexpected"] = 1
    with pytest.raises(MessageInputError):
        ReferenceStation1005.from_mapping(fields)


def test_1074_payload_and_frame_match_independent_vectors() -> None:
    payload = gps_message().encode()
    assert payload.hex() == EXPECTED_1074_PAYLOAD
    assert len(payload) == 47
    frame = frame_message_payload(payload)
    assert frame.hex() == EXPECTED_1074_FRAME
    assert len(frame) == 53
    assert read_bits(frame, 24, 12) == 1074


def test_1084_payload_and_frame_match_independent_vectors() -> None:
    payload = glonass_message().encode()
    assert payload.hex() == EXPECTED_1084_PAYLOAD
    assert len(payload) == 51
    frame = frame_message_payload(payload)
    assert frame.hex() == EXPECTED_1084_FRAME
    assert len(frame) == 57
    assert read_bits(frame, 24, 12) == 1084


def test_1074_header_fields() -> None:
    frame = frame_message_payload(gps_message().encode())
    assert read_bits(frame, 36, 12) == SYNTHETIC_STATION_GPS
    assert read_bits(frame, 48, 30) == 345600123
    assert read_bits(frame, 78, 1) == 0
    assert read_bits(frame, 79, 3) == 2
    assert read_bits(frame, 82, 7) == 0
    assert read_bits(frame, 89, 2) == 0
    assert read_bits(frame, 91, 2) == 0
    assert read_bits(frame, 93, 1) == 0
    assert read_bits(frame, 94, 3) == 0


def test_1084_header_and_glonass_epoch_packing() -> None:
    frame = frame_message_payload(glonass_message().encode())
    assert read_bits(frame, 36, 12) == SYNTHETIC_STATION_GLONASS
    epoch = read_bits(frame, 48, 30)
    assert epoch == (3 << 27) | 45_296_789
    assert epoch >> 27 == 3
    assert epoch & 0x07FFFFFF == 45_296_789
    assert read_bits(frame, 78, 1) == 1
    assert read_bits(frame, 79, 3) == 5
    assert read_bits(frame, 82, 7) == 0
    assert read_bits(frame, 89, 2) == 1
    assert read_bits(frame, 91, 2) == 2
    assert read_bits(frame, 93, 1) == 1
    assert read_bits(frame, 94, 3) == 4


def test_1074_masks_and_sparse_cell_mask() -> None:
    frame = frame_message_payload(gps_message().encode())
    satellite_mask = read_bits(frame, 97, 64)
    signal_mask = read_bits(frame, 161, 32)
    assert satellite_mask == (1 << 63) | (1 << 62) | (1 << 61)
    assert signal_mask == (1 << 30) | (1 << 23)
    assert read_bits(frame, 193, 6) == 0b101001
    assert read_bits(frame, 199, 8) == 66
    assert read_bits(frame, 207, 8) == 70
    assert read_bits(frame, 215, 8) == 73
    assert read_bits(frame, 223, 10) == 730
    assert read_bits(frame, 233, 10) == 50
    assert read_bits(frame, 243, 10) == 393


def test_1074_signal_data_column_order() -> None:
    frame = frame_message_payload(gps_message().encode())
    pseudoranges_start = 253
    assert read_signed(frame, pseudoranges_start, 15) == -1201
    assert read_signed(frame, pseudoranges_start + 15, 15) == -6176
    assert read_signed(frame, pseudoranges_start + 30, 15) == 5232
    phases_start = pseudoranges_start + 45
    assert read_signed(frame, phases_start, 22) == 51108
    assert read_signed(frame, phases_start + 22, 22) == -108100
    assert read_signed(frame, phases_start + 44, 22) == 256980
    locks_start = phases_start + 66
    assert read_bits(frame, locks_start, 4) == 6
    assert read_bits(frame, locks_start + 4, 4) == 7
    assert read_bits(frame, locks_start + 8, 4) == 9
    halves_start = locks_start + 12
    assert read_bits(frame, halves_start, 1) == 0
    assert read_bits(frame, halves_start + 1, 1) == 1
    assert read_bits(frame, halves_start + 2, 1) == 0
    cnrs_start = halves_start + 3
    assert read_bits(frame, cnrs_start, 6) == 45
    assert read_bits(frame, cnrs_start + 6, 6) == 40
    assert read_bits(frame, cnrs_start + 12, 6) == 30


def test_1084_masks_and_glonass_signal_data() -> None:
    frame = frame_message_payload(glonass_message().encode())
    assert read_bits(frame, 97, 64) == (1 << 63) | (1 << 62)
    assert read_bits(frame, 161, 32) == (1 << 30) | (1 << 24)
    assert read_bits(frame, 193, 4) == 0b1111
    assert read_bits(frame, 197, 8) == 63
    assert read_bits(frame, 205, 8) == 68
    assert read_bits(frame, 213, 10) == 728
    assert read_bits(frame, 223, 10) == 390
    pseudoranges_start = 233
    assert read_signed(frame, pseudoranges_start, 15) == -3277
    assert read_signed(frame, pseudoranges_start + 15, 15) == -3053
    assert read_signed(frame, pseudoranges_start + 30, 15) == -3689
    assert read_signed(frame, pseudoranges_start + 45, 15) == -3353
    phases_start = pseudoranges_start + 60
    assert read_signed(frame, phases_start, 22) == -33228
    assert read_signed(frame, phases_start + 22, 22) == -26065
    assert read_signed(frame, phases_start + 44, 22) == -46404
    assert read_signed(frame, phases_start + 66, 22) == -35659
    locks_start = phases_start + 88
    assert [read_bits(frame, locks_start + index * 4, 4) for index in range(4)] == [
        3,
        3,
        7,
        7,
    ]
    halves_start = locks_start + 16
    assert [read_bits(frame, halves_start + index, 1) for index in range(4)] == [
        0,
        0,
        1,
        0,
    ]
    cnrs_start = halves_start + 4
    assert [read_bits(frame, cnrs_start + index * 6, 6) for index in range(4)] == [
        50,
        49,
        42,
        41,
    ]


def test_msm4_minimum_one_cell() -> None:
    message = Msm4Message.from_mapping(
        MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (SYNTHETIC_GPS_CELLS[0],)
    )
    frame = frame_message_payload(message.encode())
    assert read_bits(frame, 97, 64) == 1 << 63
    assert read_bits(frame, 161, 32) == 1 << 30
    assert read_bits(frame, 193, 1) == 1


def test_msm4_sparse_three_signal_layout() -> None:
    cells = (
        {**SYNTHETIC_GPS_CELLS[0], "satellite_id": 1, "signal_id": 2},
        {**SYNTHETIC_GPS_CELLS[1], "satellite_id": 2, "signal_id": 3},
        {
            **SYNTHETIC_GPS_CELLS[0],
            "satellite_id": 1,
            "signal_id": 4,
            "phase_range_m": 20_000_060.0,
        },
    )
    message = Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, cells)
    frame = frame_message_payload(message.encode())
    assert read_bits(frame, 161, 32) == 0b111 << 28
    assert read_bits(frame, 193, 6) == 0b101010


@pytest.mark.parametrize(
    ("header", "observations"),
    [
        ({"epoch_ms": -1}, SYNTHETIC_GPS_CELLS),
        ({"epoch_ms": 604_800_000}, SYNTHETIC_GPS_CELLS),
        ({"epoch_ms": 0}, SYNTHETIC_GPS_CELLS),
        ({"epoch_ms": 604_799_999}, SYNTHETIC_GPS_CELLS),
    ],
)
def test_1074_epoch_boundaries(
    header: dict[str, object], observations: tuple[dict[str, object], ...]
) -> None:
    fields = dict(SYNTHETIC_GPS_HEADER)
    fields.update(header)
    epoch_ms = fields["epoch_ms"]
    assert isinstance(epoch_ms, int)
    if 0 <= epoch_ms < 604_800_000:
        assert Msm4Message.from_mapping(MsmSystem.GPS, fields, observations)
    else:
        with pytest.raises(MessageInputError):
            Msm4Message.from_mapping(MsmSystem.GPS, fields, observations)


@pytest.mark.parametrize(
    ("updates", "valid"),
    [
        ({"epoch_dow": 0, "epoch_tod_ms": 0}, True),
        ({"epoch_dow": 6, "epoch_tod_ms": 86_399_999}, True),
        ({"epoch_dow": 7, "epoch_tod_ms": 0}, False),
        ({"epoch_dow": 0, "epoch_tod_ms": -1}, False),
        ({"epoch_dow": 0, "epoch_tod_ms": 86_400_000}, False),
    ],
)
def test_1084_glonass_epoch_boundaries(
    updates: dict[str, object], valid: bool
) -> None:
    fields = dict(SYNTHETIC_GLONASS_HEADER)
    fields.update(updates)
    if valid:
        assert Msm4Message.from_mapping(
            MsmSystem.GLONASS, fields, SYNTHETIC_GLONASS_CELLS
        )
    else:
        with pytest.raises(MessageInputError):
            Msm4Message.from_mapping(
                MsmSystem.GLONASS, fields, SYNTHETIC_GLONASS_CELLS
            )


@pytest.mark.parametrize(
    "updates",
    [
        {"satellite_id": 0},
        {"satellite_id": 33},
        {"signal_id": 0},
        {"signal_id": 1},
        {"signal_id": 7},
        {"signal_id": 13},
        {"signal_id": 33},
        {"pseudorange_m": 0.0},
        {"pseudorange_m": -1.0},
        {"pseudorange_m": RANGE_MS * 255.0},
        {"phase_range_m": 20_010_000.0},
        {"lock_time_s": -0.1},
        {"cnr_dbhz": -1.0},
        {"cnr_dbhz": 64.0},
        {"pseudorange_m": float("nan")},
        {"phase_range_m": float("inf")},
        {"lock_time_s": float("nan")},
        {"cnr_dbhz": float("nan")},
        {"frequency_channel": 1},
    ],
)
def test_1074_rejects_unrepresentable_observations(updates: dict[str, Any]) -> None:
    row = dict(SYNTHETIC_GPS_CELLS[0])
    row.update(updates)
    rows = (row, *SYNTHETIC_GPS_CELLS[1:])
    with pytest.raises(MessageInputError):
        Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, rows)


@pytest.mark.parametrize(
    "updates",
    [
        {"satellite_id": 0},
        {"satellite_id": 25},
        {"signal_id": 0},
        {"signal_id": 1},
        {"signal_id": 4},
        {"signal_id": 7},
        {"signal_id": 10},
        {"signal_id": 14},
        {"frequency_channel": 1},
    ],
)
def test_1084_rejects_unrepresentable_observations(updates: dict[str, Any]) -> None:
    row = dict(SYNTHETIC_GLONASS_CELLS[0])
    row.update(updates)
    rows = (row, *SYNTHETIC_GLONASS_CELLS[1:])
    with pytest.raises(MessageInputError):
        Msm4Message.from_mapping(MsmSystem.GLONASS, SYNTHETIC_GLONASS_HEADER, rows)


def test_msm4_rejects_missing_observations_and_duplicate_cells() -> None:
    with pytest.raises(MessageInputError) as excinfo:
        Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, ())
    assert excinfo.value.missing
    duplicate = (SYNTHETIC_GPS_CELLS[0], SYNTHETIC_GPS_CELLS[0])
    with pytest.raises(MessageInputError):
        Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, duplicate)


def test_msm4_accepts_exact_sixty_four_and_rejects_above() -> None:
    signal_ids = [2, 3, 4, 5, 6, 8, 9, 10]
    exact_cells = tuple(
        {
            **SYNTHETIC_GPS_CELLS[0],
            "satellite_id": satellite_id,
            "signal_id": signal_id,
        }
        for satellite_id in range(1, 9)
        for signal_id in signal_ids
    )
    assert len(exact_cells) == MAX_MSM_CELLS
    payload = Msm4Message.from_mapping(
        MsmSystem.GPS, SYNTHETIC_GPS_HEADER, exact_cells
    ).encode()
    expected_bits = 169 + 64 + 8 * 18 + 64 * 48
    assert len(payload) == (expected_bits + 7) // 8

    too_many_cells = tuple(
        {
            **SYNTHETIC_GPS_CELLS[0],
            "satellite_id": satellite_id,
            "signal_id": signal_id,
        }
        for satellite_id in range(1, 10)
        for signal_id in signal_ids
    )
    assert len(too_many_cells) > MAX_MSM_CELLS
    with pytest.raises(MessageInputError):
        Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, too_many_cells)


def test_msm4_rejects_unknown_header_and_cell_keys() -> None:
    fields = dict(SYNTHETIC_GPS_HEADER)
    fields["reserved"] = 1
    with pytest.raises(MessageInputError):
        Msm4Message.from_mapping(MsmSystem.GPS, fields, SYNTHETIC_GPS_CELLS)
    row = dict(SYNTHETIC_GPS_CELLS[0])
    row["unexpected"] = 1
    with pytest.raises(MessageInputError):
        Msm4Message.from_mapping(
            MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (row, *SYNTHETIC_GPS_CELLS[1:])
        )


def test_signal_tables_match_rtklib_one_based_indices() -> None:
    assert GPS_MSM_SIGNAL_IDS == {
        2: "1C",
        3: "1P",
        4: "1W",
        5: "1Y",
        6: "1M",
        8: "2C",
        9: "2P",
        10: "2W",
        11: "2Y",
        12: "2M",
        15: "2S",
        16: "2L",
        17: "2X",
        22: "5I",
        23: "5Q",
        24: "5X",
        30: "1S",
        31: "1L",
        32: "1X",
    }
    assert 1 not in GPS_MSM_SIGNAL_IDS
    assert 7 not in GPS_MSM_SIGNAL_IDS
    assert GLONASS_MSM_SIGNAL_IDS == {
        2: "1C",
        3: "1P",
        8: "2C",
        9: "2P",
        11: "3I",
        12: "3Q",
        13: "3X",
    }
    assert 1 not in GLONASS_MSM_SIGNAL_IDS
    assert 4 not in GLONASS_MSM_SIGNAL_IDS
    assert 10 not in GLONASS_MSM_SIGNAL_IDS


def test_direct_model_construction_is_validated() -> None:
    with pytest.raises(MessageInputError):
        ReferenceStation1005(
            station_id=4096,
            itrf_realization_year=0,
            gps_indicator=True,
            glonass_indicator=True,
            galileo_indicator=False,
            reference_station_indicator=False,
            ecef_x_m=0.0,
            ecef_y_m=0.0,
            ecef_z_m=0.0,
            oscillator_indicator=True,
            quarter_cycle_indicator=0,
        ).encode()
    with pytest.raises(MessageInputError):
        ReferenceStation1005(
            station_id=100,
            itrf_realization_year=True,  # bool must not be accepted as int
            gps_indicator=True,
            glonass_indicator=True,
            galileo_indicator=False,
            reference_station_indicator=False,
            ecef_x_m=0.0,
            ecef_y_m=0.0,
            ecef_z_m=0.0,
            oscillator_indicator=True,
            quarter_cycle_indicator=0,
        ).encode()
    with pytest.raises(MessageInputError):
        Msm4Cell(
            satellite_id=1,
            signal_id=2,
            pseudorange_m=20_000_000.0,
            phase_range_m=20_000_050.0,
            lock_time_s=-1.0,
            half_cycle_ambiguity=False,
            cnr_dbhz=40.0,
        ).validate()
    valid_cell = Msm4Cell(
        satellite_id=1,
        signal_id=2,
        pseudorange_m=20_000_000.0,
        phase_range_m=20_000_050.0,
        lock_time_s=1.0,
        half_cycle_ambiguity=False,
        cnr_dbhz=40.0,
    )
    with pytest.raises(MessageInputError):
        Msm4Message(
            system=MsmSystem.GPS,
            station_id=1,
            epoch=604_800_000,
            multiple_message=False,
            iod=0,
            clock_steering=0,
            external_clock=0,
            smoothing=False,
            smoothing_interval=0,
            cells=(valid_cell,),
        ).encode()
    with pytest.raises(MessageInputError):
        Msm4Message(
            system=MsmSystem.GLONASS,
            station_id=1,
            epoch=(7 << 27) | 1000,
            multiple_message=False,
            iod=0,
            clock_steering=0,
            external_clock=0,
            smoothing=False,
            smoothing_interval=0,
            cells=(valid_cell,),
        ).encode()
    with pytest.raises(MessageInputError):
        Msm4Message(
            system=MsmSystem.GPS,
            station_id=1,
            epoch=1000,
            multiple_message=False,
            iod=0,
            clock_steering=0,
            external_clock=0,
            smoothing=False,
            smoothing_interval=0,
            cells=(replace(valid_cell, signal_id=1),),
        ).encode()
    with pytest.raises(MessageInputError):
        Msm4Message(
            system=MsmSystem.GLONASS,
            station_id=1,
            epoch=1000,
            multiple_message=False,
            iod=0,
            clock_steering=0,
            external_clock=0,
            smoothing=False,
            smoothing_interval=0,
            cells=(replace(valid_cell, satellite_id=25),),
        ).encode()


def test_generator_encodes_all_three_rtcm_families() -> None:
    generator = CorrectionGenerator()
    cases = (
        (
            "REFERENCE_STATION_1005",
            ENCODER_VERSION_1005,
            SYNTHETIC_1005_FIELDS,
            (),
            1005,
        ),
        (
            "MSM4_GPS_1074",
            ENCODER_VERSION_MSM4,
            SYNTHETIC_GPS_HEADER,
            SYNTHETIC_GPS_CELLS,
            1074,
        ),
        (
            "MSM4_GLONASS_1084",
            ENCODER_VERSION_MSM4,
            SYNTHETIC_GLONASS_HEADER,
            SYNTHETIC_GLONASS_CELLS,
            1084,
        ),
    )
    for family, version, fields, observations, message_number in cases:
        request = synthetic_request(family=family, encoder_version=version)
        result = generator.generate(
            request, fields=dict(fields), observations=tuple(observations)
        )
        assert result.status == GenerationStatus.ENCODED
        assert result.reason_codes == ()
        assert len(result.frames) == 1
        frame = result.frames[0]
        assert frame.message_number == message_number
        assert frame.classification == OutputClassification.SYNTHETIC_TEST_ONLY
        validation = validate_frame(frame)
        assert validation.framing_valid
        assert validation.phase9_compatible
        assert validation.semantic_validation == "NOT_PERFORMED_NO_INDEPENDENT_DECODER"


def test_generator_rtcm_frames_are_deterministic() -> None:
    generator = CorrectionGenerator()
    request = synthetic_request(
        family="REFERENCE_STATION_1005", encoder_version=ENCODER_VERSION_1005
    )
    first = generator.generate(request, fields=dict(SYNTHETIC_1005_FIELDS))
    second = generator.generate(request, fields=dict(SYNTHETIC_1005_FIELDS))
    assert first.frames[0].raw_bytes == second.frames[0].raw_bytes
    assert first.frames[0].frame_sha256 == second.frames[0].frame_sha256


def test_generator_blocks_non_synthetic_rtcm_classification() -> None:
    request = replace(
        synthetic_request(
            family="REFERENCE_STATION_1005", encoder_version=ENCODER_VERSION_1005
        ),
        classification=OutputClassification.RESEARCH_VALIDATION,
        synthetic_fixture=False,
    )
    result = CorrectionGenerator().generate(request, fields=dict(SYNTHETIC_1005_FIELDS))
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.ENCODER_NOT_VALIDATED in result.reason_codes
    assert result.frames == ()


def test_generator_blocks_operational_approved_even_with_encoder() -> None:
    request = replace(
        synthetic_request(
            family="MSM4_GPS_1074", encoder_version=ENCODER_VERSION_MSM4
        ),
        classification=OutputClassification.OPERATIONAL_APPROVED,
    )
    result = CorrectionGenerator().generate(
        request, fields=dict(SYNTHETIC_GPS_HEADER), observations=SYNTHETIC_GPS_CELLS
    )
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.OPERATIONAL_CLASSIFICATION_FORBIDDEN in result.reason_codes
    assert result.frames == ()


def test_generator_blocks_missing_rtcm_fields() -> None:
    request = synthetic_request(
        family="MSM4_GPS_1074", encoder_version=ENCODER_VERSION_MSM4
    )
    result = CorrectionGenerator().generate(request)
    assert result.status == GenerationStatus.BLOCKED
    assert result.reason_codes == (ReasonCode.MISSING_REQUIRED_FIELD,)


def test_generator_blocks_unknown_family() -> None:
    request = replace(
        synthetic_request(
            family="REFERENCE_STATION_1005", encoder_version=ENCODER_VERSION_1005
        ),
        output_message_family="NOT_A_MESSAGE_FAMILY",
    )
    result = CorrectionGenerator().generate(request, fields=dict(SYNTHETIC_1005_FIELDS))
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.UNSUPPORTED_MESSAGE_TYPE in result.reason_codes


def test_synthetic_rtcm_requires_synthetic_coordinate_state() -> None:
    request = synthetic_request(
        family="REFERENCE_STATION_1005", encoder_version=ENCODER_VERSION_1005
    )
    assert request.coordinate is not None
    coordinate = replace(request.coordinate, verification_state=VerificationState.VERIFIED)
    result = CorrectionGenerator().generate(
        replace(request, coordinate=coordinate), fields=dict(SYNTHETIC_1005_FIELDS)
    )
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.COORDINATE_UNVERIFIED in result.reason_codes


def test_registry_reports_only_synthetic_validation_for_rtcm_families() -> None:
    statuses = {
        str(row["family_id"]): row["status"]
        for row in MessageFamilyRegistry().as_dict()
    }
    assert statuses["REFERENCE_STATION_1005"] == "SYNTHETICALLY_VALIDATED"
    assert statuses["MSM4_GPS_1074"] == "SYNTHETICALLY_VALIDATED"
    assert statuses["MSM4_GLONASS_1084"] == "SYNTHETICALLY_VALIDATED"
    assert statuses["SYNTHETIC_TEST_FRAME"] == "SYNTHETICALLY_VALIDATED"
    assert "OPERATIONALLY_APPROVED" not in statuses.values()
    assert "REAL_INPUT_VALIDATED" not in statuses.values()


def test_mutated_frame_fails_phase9_validation() -> None:
    frame = bytearray(frame_message_payload(gps_message().encode()))
    frame[27] ^= 0x01
    from nlgcp_rtcm_generation.framing import validate_with_phase9

    ok, findings = validate_with_phase9(bytes(frame), 1074)
    assert not ok
    assert any("CRC_FAIL" in finding for finding in findings)


def test_1005_and_msm4_physical_round_trip_within_resolution() -> None:
    frame_1005 = frame_message_payload(
        ReferenceStation1005.from_mapping(SYNTHETIC_1005_FIELDS).encode()
    )
    assert read_signed(frame_1005, 58, 38) * 0.0001 == pytest.approx(111111.1111, abs=1e-4)
    assert read_signed(frame_1005, 98, 38) * 0.0001 == pytest.approx(-222222.2222, abs=1e-4)
    assert read_signed(frame_1005, 138, 38) * 0.0001 == pytest.approx(3333333.3333, abs=1e-4)

    frame_1084 = frame_message_payload(glonass_message().encode())
    rough_sat1 = (
        read_bits(frame_1084, 197, 8) + read_bits(frame_1084, 213, 10) / 1024.0
    ) * RANGE_MS
    rough_sat2 = (
        read_bits(frame_1084, 205, 8) + read_bits(frame_1084, 223, 10) / 1024.0
    ) * RANGE_MS
    expected_pr = [19_100_000.0, 19_100_004.0, 20_500_000.0, 20_500_006.0]
    expected_ph = [19_100_040.0, 19_100_044.0, 20_500_040.0, 20_500_046.0]
    rough_for_cell = [rough_sat1, rough_sat1, rough_sat2, rough_sat2]
    pr_lsb = RANGE_MS / (1 << 24)
    ph_lsb = RANGE_MS / (1 << 29)
    for idx in range(4):
        pr_code = read_signed(frame_1084, 233 + idx * 15, 15)
        ph_code = read_signed(frame_1084, 293 + idx * 22, 22)
        reconstructed_pr = rough_for_cell[idx] + pr_code * pr_lsb
        reconstructed_ph = rough_for_cell[idx] + ph_code * ph_lsb
        assert abs(reconstructed_pr - expected_pr[idx]) <= 0.5 * pr_lsb + 1e-9
        assert abs(reconstructed_ph - expected_ph[idx]) <= 0.5 * ph_lsb + 1e-9


@pytest.mark.parametrize(
    ("lock_time_s", "expected_code"),
    [
        (0.0, 0),
        (0.031, 0),
        (0.032, 1),
        (0.064, 2),
        (0.128, 3),
        (0.256, 4),
        (0.512, 5),
        (1.024, 6),
        (2.048, 7),
        (4.096, 8),
        (8.192, 9),
        (16.384, 10),
        (32.768, 11),
        (65.536, 12),
        (131.072, 13),
        (262.144, 14),
        (524.288, 15),
        (10000.0, 15),
    ],
)
def test_msm4_lock_time_indicator_all_sixteen_bins(
    lock_time_s: float, expected_code: int
) -> None:
    cell = {**SYNTHETIC_GPS_CELLS[0], "lock_time_s": lock_time_s}
    frame = frame_message_payload(
        Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (cell,)).encode()
    )
    # 24 frame header + 169 msm header + 1 cell + 18 sat + 15 fine pr + 22 fine ph = 249
    assert read_bits(frame, 249, 4) == expected_code


def test_msm4_fine_pseudorange_and_phase_signed_boundaries() -> None:
    # Base pseudorange quantized exactly to an integer 1/1024 ms rough range so
    # fine_pseudorange and fine_phase are exact offsets.
    rough_m = 68.5 * RANGE_MS
    ref_cell = {
        **SYNTHETIC_GPS_CELLS[0],
        "satellite_id": 1,
        "signal_id": 2,
        "pseudorange_m": rough_m,
        "phase_range_m": rough_m,
    }
    pos_cell = {
        **SYNTHETIC_GPS_CELLS[0],
        "satellite_id": 1,
        "signal_id": 8,
        "pseudorange_m": rough_m + 292.6,
        "phase_range_m": rough_m + 1170.9,
    }
    neg_cell = {
        **SYNTHETIC_GPS_CELLS[0],
        "satellite_id": 1,
        "signal_id": 9,
        "pseudorange_m": rough_m - 292.6,
        "phase_range_m": rough_m - 1170.9,
    }
    frame = frame_message_payload(
        Msm4Message.from_mapping(
            MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (ref_cell, pos_cell, neg_cell)
        ).encode()
    )
    # 24 header + 169 msm header + 3 cells + 18 sat = 214
    assert read_signed(frame, 214, 15) == 0
    assert read_signed(frame, 214 + 15, 15) > 16000
    assert read_signed(frame, 214 + 30, 15) < -16000
    assert read_signed(frame, 214 + 45, 22) == 0
    assert read_signed(frame, 214 + 45 + 22, 22) > 2_000_000
    assert read_signed(frame, 214 + 45 + 44, 22) < -2_000_000

    for bad_pr in (rough_m + 292.8, rough_m - 292.8):
        bad_cell = {**pos_cell, "pseudorange_m": bad_pr}
        with pytest.raises(MessageInputError):
            Msm4Message.from_mapping(
                MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (ref_cell, bad_cell)
            )
    for bad_ph in (rough_m + 1171.1, rough_m - 1171.1):
        bad_cell = {**pos_cell, "phase_range_m": bad_ph}
        with pytest.raises(MessageInputError):
            Msm4Message.from_mapping(
                MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (ref_cell, bad_cell)
            )


def test_msm4_high_satellite_and_signal_mask_bits() -> None:
    gps_high = {**SYNTHETIC_GPS_CELLS[0], "satellite_id": 32, "signal_id": 32}
    gps_frame = frame_message_payload(
        Msm4Message.from_mapping(MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (gps_high,)).encode()
    )
    assert read_bits(gps_frame, 97, 64) == 1 << (64 - 32)
    assert read_bits(gps_frame, 161, 32) == 1 << (32 - 32)

    glo_high = {**SYNTHETIC_GLONASS_CELLS[0], "satellite_id": 24, "signal_id": 13}
    glo_frame = frame_message_payload(
        Msm4Message.from_mapping(
            MsmSystem.GLONASS, SYNTHETIC_GLONASS_HEADER, (glo_high,)
        ).encode()
    )
    assert read_bits(glo_frame, 97, 64) == 1 << (64 - 24)
    assert read_bits(glo_frame, 161, 32) == 1 << (32 - 13)


def test_msm4_observation_order_invariance() -> None:
    forward_gps = Msm4Message.from_mapping(
        MsmSystem.GPS, SYNTHETIC_GPS_HEADER, SYNTHETIC_GPS_CELLS
    ).encode()
    reversed_gps = Msm4Message.from_mapping(
        MsmSystem.GPS, SYNTHETIC_GPS_HEADER, tuple(reversed(SYNTHETIC_GPS_CELLS))
    ).encode()
    assert forward_gps == reversed_gps

    forward_glo = Msm4Message.from_mapping(
        MsmSystem.GLONASS, SYNTHETIC_GLONASS_HEADER, SYNTHETIC_GLONASS_CELLS
    ).encode()
    reversed_glo = Msm4Message.from_mapping(
        MsmSystem.GLONASS,
        SYNTHETIC_GLONASS_HEADER,
        tuple(reversed(SYNTHETIC_GLONASS_CELLS)),
    ).encode()
    assert forward_glo == reversed_glo


def test_msm4_payload_length_and_zero_padding_bits() -> None:
    cases = (
        (gps_message(), 3, 2, 3),
        (glonass_message(), 2, 2, 4),
        (
            Msm4Message.from_mapping(
                MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (SYNTHETIC_GPS_CELLS[0],)
            ),
            1,
            1,
            1,
        ),
    )
    for message, nsat, nsig, ncell in cases:
        payload = message.encode()
        total_bits = 169 + nsat * nsig + nsat * 18 + ncell * 48
        expected_bytes = (total_bits + 7) // 8
        assert len(payload) == expected_bytes
        pad_bits = expected_bytes * 8 - total_bits
        if pad_bits:
            assert read_bits(payload, total_bits, pad_bits) == 0


def test_crc24q_standard_vector_and_mutation_rejection_across_families() -> None:
    from nlgcp_rtcm_generation.framing import validate_with_phase9
    from nlgcp_rtcm_replay.crc import crc24q

    assert crc24q(b"123456789") == 0xCDE703

    frame_1005 = frame_message_payload(
        ReferenceStation1005.from_mapping(SYNTHETIC_1005_FIELDS).encode()
    )
    frames = (
        (1005, frame_1005),
        (1074, frame_message_payload(gps_message().encode())),
        (1084, frame_message_payload(glonass_message().encode())),
    )
    for msg_no, frame in frames:
        ok, findings = validate_with_phase9(frame, msg_no)
        assert ok and not findings
        # Flip one bit in payload and one bit in trailing CRC
        for offset in (3, len(frame) // 2, len(frame) - 1):
            mutated = bytearray(frame)
            mutated[offset] ^= 0x01
            mut_ok, mut_findings = validate_with_phase9(bytes(mutated), msg_no)
            assert not mut_ok
            assert any("CRC_FAIL" in finding for finding in mut_findings)


def test_encode_payload_frame_rejects_short_and_oversize_payloads() -> None:
    from nlgcp_rtcm_replay.framing import encode_payload_frame

    with pytest.raises(ValueError, match="12-bit message number"):
        encode_payload_frame(b"\x01")
    with pytest.raises(ValueError, match="payload too long"):
        encode_payload_frame(b"\x00" * 1024)
