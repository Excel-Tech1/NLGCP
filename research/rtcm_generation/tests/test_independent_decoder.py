"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Day 3 independent RTCM 3.x decoder validation tests using unmodified
RTKLIB v2.4.2-p13 (both the external ``convbin`` binary and the read-only
native C ``input_rtcm3`` adapter).

These tests validate deterministic synthetic fixtures only.  They do NOT
establish non-RTKLIB decoder conformance, receiver interoperability, authentic
station observations, RTK FIX, positioning accuracy, or operational approval.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from nlgcp_rtcm_generation.bitstream import BitWriter
from nlgcp_rtcm_generation.framing import frame_message_payload
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.independent_decoder import (
    IndependentDecoderUnavailable,
    build_rtklib_decoder,
    convbin_provenance,
    decode_with_convbin,
    decode_with_rtklib_native,
    glonass_wavelength_m,
    gps_wavelength_m,
    locate_convbin,
)
from nlgcp_rtcm_generation.messages import (
    GLONASS_MSM_SIGNAL_IDS,
    GPS_MSM_SIGNAL_IDS,
    RANGE_MS,
    Msm4Message,
    MsmSystem,
    ReferenceStation1005,
)
from nlgcp_rtcm_generation.models import (
    CoordinateProvenance,
    CorrectionGenerationRequest,
    EpochContract,
    GenerationMode,
    OutputClassification,
    VerificationState,
)
from nlgcp_rtcm_replay.framing import encode_payload_frame
from test_rtcm_messages import (
    SYNTHETIC_1005_FIELDS,
    SYNTHETIC_GLONASS_CELLS,
    SYNTHETIC_GLONASS_HEADER,
    SYNTHETIC_GPS_CELLS,
    SYNTHETIC_GPS_HEADER,
)

FINE_PR_HALF_LSB_M = 0.5 * RANGE_MS / (1 << 24)
FINE_PH_HALF_LSB_M = 0.5 * RANGE_MS / (1 << 29)


@pytest.fixture(scope="module")
def convbin_bin() -> Path:
    try:
        return locate_convbin()
    except IndependentDecoderUnavailable as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def native_decoder() -> tuple[Path, dict[str, Any]]:
    source = os.environ.get("RTKLIB_SOURCE")
    if not source:
        pytest.skip(
            "external pinned RTKLIB_SOURCE is required for native input_rtcm3 checks"
        )
    repo = Path(__file__).resolve().parents[3]
    try:
        return build_rtklib_decoder(repo, Path(source))
    except IndependentDecoderUnavailable as exc:
        pytest.skip(str(exc))


def _day2_1005_frame() -> bytes:
    return frame_message_payload(
        ReferenceStation1005.from_mapping(SYNTHETIC_1005_FIELDS).encode()
    )


def _day2_1074_frame() -> bytes:
    return frame_message_payload(
        Msm4Message.from_mapping(
            MsmSystem.GPS, SYNTHETIC_GPS_HEADER, SYNTHETIC_GPS_CELLS
        ).encode()
    )


def _day2_1084_frame(*, multiple_message: bool = True) -> bytes:
    header = {**SYNTHETIC_GLONASS_HEADER, "multiple_message": multiple_message}
    return frame_message_payload(
        Msm4Message.from_mapping(
            MsmSystem.GLONASS, header, SYNTHETIC_GLONASS_CELLS
        ).encode()
    )


def _lab_4095_frame() -> bytes:
    from nlgcp_rtcm_generation import ENCODER_VERSION

    coordinate = CoordinateProvenance(
        station_id="SYNA00SYN",
        ecef_xyz_m=(1.0, 2.0, 3.0),
        reference_frame="SYNTHETIC_FRAME",
        coordinate_epoch="2026-01-01T00:00:00Z",
        source="SYNTHETIC TEST DATA",
        fingerprint="synthetic-coordinate-fp",
        verification_state=VerificationState.SYNTHETIC_TEST_ONLY,
    )
    request = CorrectionGenerationRequest(
        request_id="request-day3-4095",
        decision_id="decision-day3-4095",
        decision_fingerprint="decision-fp",
        decision_status="OK",
        mode=GenerationMode.SINGLE_BASE,
        reference_station_id="SYNA00SYN",
        virtual_station_id=None,
        coordinate=coordinate,
        epoch=EpochContract("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.100Z"),
        gnss_systems=("GPS",),
        input_source_fingerprint="synthetic-input-fp",
        input_source_admitted=True,
        station_identity_verified=True,
        coordinate_verified=True,
        correction_model_fingerprint="synthetic-model-fp",
        correction_model_approved=True,
        output_message_family="SYNTHETIC_TEST_FRAME",
        encoder_version=ENCODER_VERSION,
        scientific_status="SYNTHETIC_TEST_ONLY",
        classification=OutputClassification.SYNTHETIC_TEST_ONLY,
        synthetic_fixture=True,
    )
    result = CorrectionGenerator().generate(request, fields={"value": 7})
    return result.frames[0].raw_bytes


# ---------------------------------------------------------------------------
# A. External unmodified RTKLIB convbin CLI binary tests
# ---------------------------------------------------------------------------


def test_convbin_provenance_recorded(convbin_bin: Path) -> None:
    prov = convbin_provenance(convbin_bin)
    assert prov["decoder_name"] == "RTKLIB convbin"
    assert len(str(prov["binary_sha256"])) == 64
    assert prov["non_rtklib_decoder_available"] is False


def test_convbin_decodes_1005_and_1074_synthetic_vectors(convbin_bin: Path) -> None:
    stream = _day2_1005_frame() + _day2_1074_frame()
    result = decode_with_convbin(stream, binary=convbin_bin)
    assert result.returncode == 0
    assert result.station_id == 1234
    assert result.approx_position_xyz == pytest.approx(
        (111111.1111, -222222.2222, 3333333.3333), abs=1e-4
    )
    assert result.sys_obs_types["G"] == ("C1C", "L1C", "S1C", "C2P", "L2P", "S2P")
    assert result.time_of_first_obs is not None
    assert "2026     1     1     0     0    0.1230000     GPS" in result.time_of_first_obs
    assert len(result.epochs) == 1
    sats = result.epochs[0].satellites
    assert set(sats) == {"G01", "G02", "G03"}

    l1_wl = gps_wavelength_m(1)
    l2_wl = gps_wavelength_m(2)

    assert abs(sats["G01"]["C1C"].value - 20_000_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert abs(sats["G01"]["L1C"].value * l1_wl - 20_000_050.0) <= FINE_PH_HALF_LSB_M + 1e-3
    assert sats["G01"]["L1C"].lli is None
    assert sats["G01"]["S1C"].value == pytest.approx(45.0, abs=1e-3)

    assert abs(sats["G02"]["C1C"].value - 21_000_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert abs(sats["G02"]["L1C"].value * l1_wl - 21_000_050.0) <= FINE_PH_HALF_LSB_M + 1e-3
    assert sats["G02"]["L1C"].lli == 3  # half_cycle_ambiguity=True
    assert sats["G02"]["S1C"].value == pytest.approx(40.0, abs=1e-3)

    assert abs(sats["G03"]["C2P"].value - 22_000_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert abs(sats["G03"]["L2P"].value * l2_wl - 22_000_050.0) <= FINE_PH_HALF_LSB_M + 1e-3
    assert sats["G03"]["L2P"].lli is None
    assert sats["G03"]["S2P"].value == pytest.approx(30.0, abs=1e-3)


def test_convbin_decodes_1084_and_exposes_glonass_fcn_phase_limitation(
    convbin_bin: Path,
) -> None:
    stream = _day2_1084_frame(multiple_message=False)
    result = decode_with_convbin(stream, binary=convbin_bin)
    assert result.returncode == 0
    assert result.station_id == 3210
    # Corrected GLONASS signals 2 -> 1C and 8 -> 2C; L1C/L2C absent without FCN.
    assert result.sys_obs_types["R"] == ("C1C", "S1C", "C2C", "S2C")
    assert result.time_of_first_obs is not None
    assert "2026     1     1     9    35   14.7890000     GPS" in result.time_of_first_obs
    assert len(result.epochs) == 1
    sats = result.epochs[0].satellites
    assert set(sats) == {"R01", "R02"}

    assert abs(sats["R01"]["C1C"].value - 19_100_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert sats["R01"]["S1C"].value == pytest.approx(50.0, abs=1e-3)
    assert abs(sats["R01"]["C2C"].value - 19_100_004.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert sats["R01"]["S2C"].value == pytest.approx(49.0, abs=1e-3)

    assert abs(sats["R02"]["C1C"].value - 20_500_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert sats["R02"]["S1C"].value == pytest.approx(42.0, abs=1e-3)
    assert abs(sats["R02"]["C2C"].value - 20_500_006.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert sats["R02"]["S2C"].value == pytest.approx(41.0, abs=1e-3)


def test_convbin_rejects_corrupted_crc_and_truncated_frames(convbin_bin: Path) -> None:
    base = _day2_1074_frame()
    bad_crc = bytearray(base)
    bad_crc[-1] ^= 0x01
    bad_payload = bytearray(base)
    bad_payload[10] ^= 0x01
    bad_preamble = bytearray(base)
    bad_preamble[0] = 0xD2
    truncated = base[:-4]

    for corrupted in (bytes(bad_crc), bytes(bad_payload), bytes(bad_preamble), truncated):
        result = decode_with_convbin(corrupted, binary=convbin_bin)
        assert result.epochs == ()


def test_convbin_ignores_synthetic_lab_4095_frame(convbin_bin: Path) -> None:
    result = decode_with_convbin(_lab_4095_frame(), binary=convbin_bin)
    assert result.epochs == ()
    assert result.approx_position_xyz is None


# ---------------------------------------------------------------------------
# B. Native unmodified RTKLIB v2.4.2-p13 input_rtcm3() C adapter tests
# ---------------------------------------------------------------------------


def test_native_rtklib_decodes_1005_synthetic_and_edge_cases(
    native_decoder: tuple[Path, dict[str, Any]],
) -> None:
    exe, prov = native_decoder
    assert prov["commit"] == "71db0ffa0d9735697c6adfd06fdf766d0e5ce807"
    assert prov["non_rtklib_decoder_available"] is False

    decoded = decode_with_rtklib_native(exe, _day2_1005_frame())
    assert decoded["summary"]["crc_errors"] == 0
    assert decoded["summary"]["decode_errors"] == 0
    assert decoded["summary"]["nmsg3_1005"] == 1
    ev = decoded["events"][0]
    assert ev["ret"] == 5
    assert ev["crc_ok"] is True
    assert ev["msg_no"] == 1005
    assert ev["staid"] == 1234
    assert ev["itrf"] == 0
    assert ev["pos_ecef"] == pytest.approx(
        [111111.1111, -222222.2222, 3333333.3333], abs=1e-4
    )

    # Boundary station ID, non-zero ITRF year, negative/positive extreme coordinates
    # within 38-bit 0.1 mm range, and flipped indicators (which RTKLIB skips).
    edge_fields = {
        **SYNTHETIC_1005_FIELDS,
        "station_id": 4095,
        "itrf_realization_year": 14,
        "gps_indicator": False,
        "glonass_indicator": False,
        "galileo_indicator": True,
        "reference_station_indicator": True,
        "oscillator_indicator": False,
        "quarter_cycle_indicator": 2,
        "ecef_x_m": -6_378_137.1234,
        "ecef_y_m": 4_123_456.7891,
        "ecef_z_m": -1_000_000.0001,
    }
    edge_frame = frame_message_payload(
        ReferenceStation1005.from_mapping(edge_fields).encode()
    )
    edge_dec = decode_with_rtklib_native(exe, edge_frame)
    edge_ev = edge_dec["events"][0]
    assert edge_ev["ret"] == 5
    assert edge_ev["staid"] == 4095
    assert edge_ev["itrf"] == 14
    assert edge_ev["pos_ecef"] == pytest.approx(
        [-6_378_137.1234, 4_123_456.7891, -1_000_000.0001], abs=1e-4
    )


def test_native_rtklib_decodes_1074_vector_and_all_gps_signal_mappings(
    native_decoder: tuple[Path, dict[str, Any]],
) -> None:
    exe, _ = native_decoder
    decoded = decode_with_rtklib_native(exe, _day2_1074_frame())
    assert decoded["summary"]["crc_errors"] == 0
    assert decoded["summary"]["decode_errors"] == 0
    assert decoded["summary"]["nmsg3_1074"] == 1
    ev = decoded["events"][0]
    assert ev["ret"] == 1
    assert ev["crc_ok"] is True
    assert ev["msg_no"] == 1074
    assert ev["staid"] == 1234
    assert ev["gps_tow_s"] == pytest.approx(345600.123, abs=1e-6)
    assert ev["msmtype_gps"] == "L1C,L2P"
    assert "nsat= 3 nsig= 2 iod= 2 ncell= 3 sync=0" in ev["msgtype"]

    by_key = {(o["prn"], o["code"]): o for o in ev["obs"]}
    assert set(by_key) == {(1, "1C"), (2, "1C"), (3, "2P")}
    assert abs(by_key[(1, "1C")]["P_m"] - 20_000_000.0) <= FINE_PR_HALF_LSB_M + 1e-6
    assert (
        abs(by_key[(1, "1C")]["L_cyc"] * gps_wavelength_m(1) - 20_000_050.0)
        <= FINE_PH_HALF_LSB_M + 1e-6
    )
    assert by_key[(1, "1C")]["SNR_dbhz"] == pytest.approx(45.0)
    assert by_key[(1, "1C")]["LLI"] == 0
    assert by_key[(2, "1C")]["LLI"] == 3
    assert by_key[(3, "2P")]["SNR_dbhz"] == pytest.approx(30.0)
    assert (
        abs(by_key[(3, "2P")]["L_cyc"] * gps_wavelength_m(2) - 22_000_050.0)
        <= FINE_PH_HALF_LSB_M + 1e-6
    )

    # Verify EVERY defined 1-based GPS MSM signal ID matches RTKLIB msm_sig_gps.
    for sig_id, expected_code in GPS_MSM_SIGNAL_IDS.items():
        cell = {**SYNTHETIC_GPS_CELLS[0], "satellite_id": 5, "signal_id": sig_id}
        frame = frame_message_payload(
            Msm4Message.from_mapping(
                MsmSystem.GPS, SYNTHETIC_GPS_HEADER, (cell,)
            ).encode()
        )
        res = decode_with_rtklib_native(exe, frame)
        sig_ev = res["events"][0]
        assert sig_ev["ret"] == 1
        assert sig_ev["msmtype_gps"] == f"L{expected_code}"
        assert len(sig_ev["obs"]) == 1
        assert sig_ev["obs"][0]["code"] == expected_code


def test_native_rtklib_decodes_1084_standalone_and_with_synthetic_fcn(
    native_decoder: tuple[Path, dict[str, Any]],
) -> None:
    exe, _ = native_decoder

    # 1. Exact Day 2 vector has multiple_message=True (sync=1 -> ret=0, obsflag=0).
    dec_sync1 = decode_with_rtklib_native(exe, _day2_1084_frame(multiple_message=True))
    ev1 = dec_sync1["events"][0]
    assert ev1["ret"] == 0
    assert ev1["obsflag"] == 0
    assert ev1["crc_ok"] is True
    assert ev1["msg_no"] == 1084
    assert ev1["staid"] == 3210
    assert ev1["msmtype_glo"] == "L1C,L2C"
    assert "nsat= 2 nsig= 2 iod= 5 ncell= 4 sync=1" in ev1["msgtype"]
    # Standalone 1084 has no GLONASS FCN -> RTKLIB cannot compute wavelength -> L_cyc == 0.
    assert len(ev1["obs"]) == 4
    assert all(o["L_cyc"] == 0.0 for o in ev1["obs"])

    # 2. Same vector with multiple_message=False (sync=0 -> ret=1) AND synthetic test-only FCNs
    #    verifies RTKLIB decodes the 1084 fine phase-range (DF401) bits to sub-mm precision.
    fcns = {1: 1, 2: -4}
    dec_fcn = decode_with_rtklib_native(
        exe, _day2_1084_frame(multiple_message=False), glo_fcns=fcns
    )
    ev2 = dec_fcn["events"][0]
    assert ev2["ret"] == 1
    assert ev2["obsflag"] == 1
    # 2026-01-01 09:35:14.789 GPST = 4 * 86400 + 9*3600 + 35*60 + 14.789 = 380114.789 s
    assert ev2["gps_tow_s"] == pytest.approx(380114.789, abs=1e-6)
    by_key = {(o["prn"], o["code"]): o for o in ev2["obs"]}
    assert set(by_key) == {(1, "1C"), (1, "2C"), (2, "1C"), (2, "2C")}
    expected = {
        (1, "1C"): (19_100_000.0, 19_100_040.0, 50.0, 0, 1),
        (1, "2C"): (19_100_004.0, 19_100_044.0, 49.0, 0, 2),
        (2, "1C"): (20_500_000.0, 20_500_040.0, 42.0, 3, 1),
        (2, "2C"): (20_500_006.0, 20_500_046.0, 41.0, 0, 2),
    }
    for (prn, code), (pr, ph, cnr, lli, freq) in expected.items():
        obs = by_key[(prn, code)]
        assert abs(obs["P_m"] - pr) <= FINE_PR_HALF_LSB_M + 1e-6
        wl = glonass_wavelength_m(freq, fcns[prn])
        assert abs(obs["L_cyc"] * wl - ph) <= FINE_PH_HALF_LSB_M + 1e-6
        assert obs["SNR_dbhz"] == pytest.approx(cnr)
        assert obs["LLI"] == lli

    # 3. Verify EVERY defined 1-based GLONASS MSM signal ID matches RTKLIB msm_sig_glo.
    for sig_id, expected_code in GLONASS_MSM_SIGNAL_IDS.items():
        cell = {**SYNTHETIC_GLONASS_CELLS[0], "satellite_id": 1, "signal_id": sig_id}
        header = {**SYNTHETIC_GLONASS_HEADER, "multiple_message": False}
        frame = frame_message_payload(
            Msm4Message.from_mapping(MsmSystem.GLONASS, header, (cell,)).encode()
        )
        res = decode_with_rtklib_native(exe, frame)
        sig_ev = res["events"][0]
        assert sig_ev["ret"] == 1
        assert sig_ev["msmtype_glo"] == f"L{expected_code}"
        assert len(sig_ev["obs"]) == 1
        assert sig_ev["obs"][0]["code"] == expected_code


def test_native_rtklib_proves_reserved_signal_id_1_is_unknown(
    native_decoder: tuple[Path, dict[str, Any]],
) -> None:
    """Confirm the Day 2 off-by-one bug: signal ID 1 is unknown to RTKLIB."""
    exe, _ = native_decoder
    for msg_no, msm_key in ((1074, "msmtype_gps"), (1084, "msmtype_glo")):
        w = BitWriter(max_bits=512)
        w.write_unsigned(msg_no, 12)
        w.write_unsigned(1234, 12)
        w.write_unsigned(1000, 30)
        w.write_unsigned(0, 1)  # sync=0
        w.write_unsigned(0, 3)  # iod
        w.write_unsigned(0, 7)  # reserved
        w.write_unsigned(0, 2)  # clock_steering
        w.write_unsigned(0, 2)  # external_clock
        w.write_unsigned(0, 1)  # smoothing
        w.write_unsigned(0, 3)  # smoothing_interval
        w.write_unsigned(1 << 63, 64)  # satellite 1
        w.write_unsigned(1 << 31, 32)  # RESERVED signal ID 1
        w.write_unsigned(1, 1)  # 1x1 cell mask
        w.write_unsigned(66, 8)  # rough int ms
        w.write_unsigned(512, 10)  # rough mod ms
        w.write_signed(0, 15)  # fine pr
        w.write_signed(0, 22)  # fine ph
        w.write_unsigned(5, 4)  # lock
        w.write_unsigned(0, 1)  # half
        w.write_unsigned(40, 6)  # cnr
        frame = encode_payload_frame(w.to_bytes())
        res = decode_with_rtklib_native(exe, frame)
        ev = res["events"][0]
        assert ev["crc_ok"] is True
        assert ev[msm_key] == "(1)"
        assert ev["obs"] == []


def test_native_rtklib_rejects_corrupted_and_malformed_messages(
    native_decoder: tuple[Path, dict[str, Any]],
) -> None:
    exe, _ = native_decoder

    # 1. CRC and payload single-bit flips fail rtk_crc24q on 1005, 1074, 1084.
    for frame in (_day2_1005_frame(), _day2_1074_frame(), _day2_1084_frame()):
        for offset in (4, len(frame) // 2, len(frame) - 1):
            mutated = bytearray(frame)
            mutated[offset] ^= 0x01
            res = decode_with_rtklib_native(exe, bytes(mutated))
            assert res["summary"]["crc_errors"] == 1
            assert res["events"][0]["crc_ok"] is False
            assert res["events"][0]["ret"] == 0

    # 2. Truncated frame and bad preamble yield zero completed frames.
    trunc = decode_with_rtklib_native(exe, _day2_1074_frame()[:-5])
    assert trunc["summary"]["events"] == 0
    assert trunc["summary"]["trailing_nbyte"] > 0

    bad_pre = bytearray(_day2_1005_frame())
    bad_pre[0] = 0xD2
    res_pre = decode_with_rtklib_native(exe, bytes(bad_pre))
    assert res_pre["summary"]["events"] == 0

    # 3. Valid-CRC 1005 with wrong length (18 bytes instead of 19) -> ret = -1.
    short_1005_payload = ReferenceStation1005.from_mapping(
        SYNTHETIC_1005_FIELDS
    ).encode()[:-1]
    res_short_1005 = decode_with_rtklib_native(
        exe, encode_payload_frame(short_1005_payload)
    )
    assert res_short_1005["events"][0]["crc_ok"] is True
    assert res_short_1005["events"][0]["ret"] == -1
    assert res_short_1005["summary"]["decode_errors"] == 1

    # 4. Valid-CRC 1074 with nsat * nsig > 64 (9 sats x 8 sigs = 72) -> ret = -1.
    w = BitWriter(max_bits=512)
    w.write_unsigned(1074, 12)
    w.write_unsigned(1234, 12)
    w.write_unsigned(1000, 30)
    w.write_unsigned(0, 1)
    w.write_unsigned(0, 3)
    w.write_unsigned(0, 7)
    w.write_unsigned(0, 2)
    w.write_unsigned(0, 2)
    w.write_unsigned(0, 1)
    w.write_unsigned(0, 3)
    w.write_unsigned(0x1FF << (64 - 9), 64)  # 9 satellites
    w.write_unsigned(0xFF << (32 - 8), 32)  # 8 signals -> 72 > 64
    res_over64 = decode_with_rtklib_native(exe, encode_payload_frame(w.to_bytes()))
    assert res_over64["events"][0]["crc_ok"] is True
    assert res_over64["events"][0]["ret"] == -1

    # 5. Valid-CRC 1074 with truncated signal body -> ret = -1.
    trunc_body = Msm4Message.from_mapping(
        MsmSystem.GPS, SYNTHETIC_GPS_HEADER, SYNTHETIC_GPS_CELLS
    ).encode()[:-2]
    res_trunc_body = decode_with_rtklib_native(exe, encode_payload_frame(trunc_body))
    assert res_trunc_body["events"][0]["crc_ok"] is True
    assert res_trunc_body["events"][0]["ret"] == -1

    # 6. Synthetic lab 4095 frame: CRC passes, RTKLIB does not decode obs or station.
    res_4095 = decode_with_rtklib_native(exe, _lab_4095_frame())
    assert res_4095["events"][0]["crc_ok"] is True
    assert res_4095["events"][0]["msg_no"] == 4095
    assert res_4095["events"][0]["ret"] == 0
    assert res_4095["events"][0]["obs"] == []
    assert res_4095["summary"]["nmsg3_other"] == 1
