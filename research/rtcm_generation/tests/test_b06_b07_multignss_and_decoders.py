"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Milestones B-06 (Multi-GNSS & RTCM Expansion) and B-07 (Independent Protocol
Cross-Decoding Validation) test suite.

Verifies:
1. RTCM 1006 (ARP + 0.1710 m Nigerian antenna height), 1007, 1008, 1033
   (Trimble/Septentrio descriptors), 1020 (GLONASS ephemeris + FCN), 1230
   (GLONASS FDMA code-phase biases), and 1094 (Galileo MSM4);
2. Resolution of the Day 3 standalone 1084 GLONASS carrier-phase FCN blocker
   by streaming RTCM 1020 + 1084 into unmodified RTKLIB convbin & input_rtcm3()
   WITHOUT any test-only --glo-fcn injection;
3. Clean-room independent RTCM 10403.3 specification decoder (spec_decoder.py)
   sharing zero code with encoders or Phase 9 CRC;
4. Unmodified ESA/gAGE-UPC gLAB v6.0.0 cross-decoding of 1005, 1006, and 1008
   (when /opt/gLAB/source/core is available);
5. Fail-closed registry invariants (BeiDou 1124 DECLARED only; zero
   OPERATIONALLY_APPROVED or REAL_INPUT_VALIDATED claims).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from nlgcp_rtcm_generation.framing import frame_message_payload
from nlgcp_rtcm_generation.independent_decoder import (
    GLAB_DEFAULT_SOURCE,
    IndependentDecoderUnavailable,
    build_glab_rtcm1005_decoder,
    build_rtklib_decoder,
    decode_rtcm1005_with_glab,
    decode_with_convbin,
    decode_with_rtklib_native,
    glonass_wavelength_m,
    locate_convbin,
)
from nlgcp_rtcm_generation.messages import (
    GALILEO_MSM_SIGNAL_IDS,
    RANGE_MS,
    AntennaDescriptor1007,
    AntennaDescriptorSerial1008,
    GlonassCodePhaseBias1230,
    GlonassEphemeris1020,
    MessageInputError,
    Msm4Cell,
    Msm4Message,
    MsmSystem,
    ReceiverAntennaDescriptor1033,
    ReferenceStation1005,
    ReferenceStation1006,
)
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry, MessageFamilyStatus
from nlgcp_rtcm_generation.spec_decoder import (
    decode_rtcm_stream_independent_spec,
    standalone_crc24q,
)

FINE_PR_HALF_LSB_M = 0.5 * RANGE_MS / (1 << 24)
FINE_PH_HALF_LSB_M = 0.5 * RANGE_MS / (1 << 29)


def _sample_1006() -> ReferenceStation1006:
    return ReferenceStation1006(
        station_id=2011,
        itrf_realization_year=20,
        gps_indicator=True,
        glonass_indicator=True,
        galileo_indicator=True,
        reference_station_indicator=False,
        ecef_x_m=6246471.2763,
        ecef_y_m=820848.7363,
        ecef_z_m=994267.9301,
        oscillator_indicator=True,
        quarter_cycle_indicator=0,
        antenna_height_m=0.1710,
    )


def _sample_1007() -> AntennaDescriptor1007:
    return AntennaDescriptor1007(
        station_id=2011,
        antenna_descriptor="TRM59800.00     NONE",
        antenna_setup_id=0,
    )


def _sample_1008() -> AntennaDescriptorSerial1008:
    return AntennaDescriptorSerial1008(
        station_id=2011,
        antenna_descriptor="TRM59800.00     NONE",
        antenna_setup_id=0,
        antenna_serial="4923353217",
    )


def _sample_1033(station_id: int = 2011) -> ReceiverAntennaDescriptor1033:
    return ReceiverAntennaDescriptor1033(
        station_id=station_id,
        antenna_descriptor="SEPCHOKE_B3E6   SPKE",
        antenna_setup_id=0,
        antenna_serial="5440",
        receiver_type="SEPT POLARX5",
        receiver_firmware="5.5.0",
        receiver_serial="4502198",
    )


def _sample_1020(slot: int = 1, fcn: int = -4) -> GlonassEphemeris1020:
    return GlonassEphemeris1020(
        satellite_id=slot,
        fcn=fcn,
        tk_hour=3,
        tk_minute=0,
        tk_second_30s=0,
        svh=0,
        tb=13,
        pos_m=(-12_345_678.0, 15_678_901.0, 16_012_345.0),
        vel_m_s=(1_234.5, -2_345.6, 1_890.2),
        acc_m_s2=(1.8626451e-6, -9.3132257e-7, 2.7939677e-6),
        gamma_n=1.8189894e-12,
        tau_n=-1.2e-5,
        dtau_n=0.0,
        age_days=1,
        nt=1,
    )


def _sample_1230() -> GlonassCodePhaseBias1230:
    return GlonassCodePhaseBias1230(
        station_id=2011,
        code_phase_bias_indicator=True,
        l1_ca_bias_m=0.42,
        l1_p_bias_m=None,
        l2_ca_bias_m=-0.18,
        l2_p_bias_m=0.06,
    )


def _sample_1094(station_id: int = 2011) -> Msm4Message:
    return Msm4Message(
        system=MsmSystem.GALILEO,
        station_id=station_id,
        epoch=123_456,
        multiple_message=False,
        iod=1,
        clock_steering=0,
        external_clock=0,
        smoothing=False,
        smoothing_interval=0,
        cells=(
            Msm4Cell(
                satellite_id=4,
                signal_id=2,  # 1C
                pseudorange_m=23_123_456.78,
                phase_range_m=23_123_500.12,
                lock_time_s=64.0,
                half_cycle_ambiguity=False,
                cnr_dbhz=46.0,
            ),
            Msm4Cell(
                satellite_id=4,
                signal_id=23,  # 5Q
                pseudorange_m=23_123_460.11,
                phase_range_m=23_123_505.45,
                lock_time_s=64.0,
                half_cycle_ambiguity=True,
                cnr_dbhz=44.0,
            ),
            Msm4Cell(
                satellite_id=19,
                signal_id=15,  # 7Q
                pseudorange_m=24_500_000.00,
                phase_range_m=24_500_040.25,
                lock_time_s=32.0,
                half_cycle_ambiguity=False,
                cnr_dbhz=41.0,
            ),
        ),
    )


def test_b06_registry_honest_statuses_and_beidou_declared_only() -> None:
    reg = MessageFamilyRegistry()
    by_id = {row["family_id"]: row for row in reg.as_dict()}
    for fid in (
        "REFERENCE_STATION_1006",
        "ANTENNA_DESCRIPTOR_1007",
        "ANTENNA_DESCRIPTOR_SERIAL_1008",
        "RECEIVER_ANTENNA_DESCRIPTOR_1033",
        "GLONASS_EPHEMERIS_1020",
        "GLONASS_CODE_PHASE_BIAS_1230",
        "MSM4_GALILEO_1094",
    ):
        assert by_id[fid]["status"] == str(MessageFamilyStatus.SYNTHETICALLY_VALIDATED)
    assert by_id["MSM4_BEIDOU_1124"]["status"] == str(MessageFamilyStatus.DECLARED)
    assert by_id["MSM4_BEIDOU_1124"]["encoder_key"] is None
    assert "OPERATIONALLY_APPROVED" not in {r["status"] for r in by_id.values()}
    assert "REAL_INPUT_VALIDATED" not in {r["status"] for r in by_id.values()}


def test_b06_input_bounds_fail_closed() -> None:
    with pytest.raises(MessageInputError):
        ReferenceStation1006(
            station_id=1,
            itrf_realization_year=0,
            gps_indicator=True,
            glonass_indicator=False,
            galileo_indicator=False,
            reference_station_indicator=False,
            ecef_x_m=1.0,
            ecef_y_m=2.0,
            ecef_z_m=3.0,
            oscillator_indicator=True,
            quarter_cycle_indicator=0,
            antenna_height_m=7.0,  # > 6.5535 m
        ).encode()
    with pytest.raises(MessageInputError):
        AntennaDescriptor1007(station_id=1, antenna_descriptor="A" * 32).encode()
    with pytest.raises(MessageInputError):
        GlonassEphemeris1020(
            satellite_id=1,
            fcn=7,  # outside [-7, 6]
            tk_hour=0,
            tk_minute=0,
            tk_second_30s=0,
            svh=0,
            tb=1,
            pos_m=(1e7, 1e7, 1e7),
            vel_m_s=(1000.0, 0.0, 0.0),
            acc_m_s2=(0.0, 0.0, 0.0),
            gamma_n=0.0,
            tau_n=0.0,
        ).encode()


def test_b07_clean_room_spec_decoder_round_trips_all_b06_messages() -> None:
    m1005 = ReferenceStation1005(
        station_id=1234,
        itrf_realization_year=0,
        gps_indicator=True,
        glonass_indicator=True,
        galileo_indicator=True,
        reference_station_indicator=False,
        ecef_x_m=6246471.2763,
        ecef_y_m=820848.7363,
        ecef_z_m=994267.9301,
        oscillator_indicator=True,
        quarter_cycle_indicator=0,
    )
    m1006 = _sample_1006()
    m1007 = _sample_1007()
    m1008 = _sample_1008()
    m1033 = _sample_1033()
    m1020 = _sample_1020(slot=5, fcn=3)
    m1230 = _sample_1230()
    m1094 = _sample_1094()

    stream = b"".join(
        frame_message_payload(m.encode())
        for m in (m1005, m1006, m1007, m1008, m1033, m1020, m1230, m1094)
    )
    decoded = decode_rtcm_stream_independent_spec(stream)
    assert decoded["shares_encoder_or_phase9_code"] is False
    assert decoded["summary"]["frame_count"] == 8
    assert decoded["summary"]["crc_ok_count"] == 8
    assert decoded["summary"]["crc_fail_count"] == 0
    assert decoded["summary"]["decoded_count"] == 8

    by_no = {f["message_number"]: f["fields"] for f in decoded["frames"]}
    assert by_no[1006]["antenna_height_m"] == pytest.approx(0.1710, abs=1e-4)
    assert by_no[1006]["ecef_x_m"] == pytest.approx(6246471.2763, abs=1e-4)
    assert by_no[1007]["antenna_descriptor"] == "TRM59800.00     NONE"
    assert by_no[1008]["antenna_serial"] == "4923353217"
    assert by_no[1033]["receiver_type"] == "SEPT POLARX5"
    assert by_no[1033]["receiver_firmware"] == "5.5.0"
    assert by_no[1033]["receiver_serial"] == "4502198"
    assert by_no[1020]["satellite_id"] == 5
    assert by_no[1020]["fcn"] == 3
    assert by_no[1230]["biases_m"] == {"L1_CA": 0.42, "L2_CA": -0.18, "L2_P": 0.06}
    assert by_no[1094]["system"] == "GALILEO"
    assert len(by_no[1094]["cells"]) == 3
    assert by_no[1094]["cells"][0]["signal_code"] == GALILEO_MSM_SIGNAL_IDS[2]
    assert abs(by_no[1094]["cells"][0]["pseudorange_m"] - 23_123_456.78) <= (
        FINE_PR_HALF_LSB_M + 1e-6
    )

    # Bit-flip fails clean-room CRC-24Q independently
    corrupt = bytearray(frame_message_payload(m1006.encode()))
    corrupt[10] ^= 0x04
    bad = decode_rtcm_stream_independent_spec(bytes(corrupt))
    assert bad["summary"]["crc_fail_count"] == 1
    assert bad["frames"][0]["note"] == "CRC24Q_FAILED"
    assert standalone_crc24q(bytes(corrupt[:-3])) != int.from_bytes(corrupt[-3:], "big")


def test_b06_rtklib_convbin_decodes_1006_1033_1094_and_1020_resolves_1084_phase() -> None:
    try:
        convbin = locate_convbin()
    except IndependentDecoderUnavailable as exc:
        pytest.skip(str(exc))

    # 1. RTCM 1020 (slot 1 fcn=-4) + 1084 -> convbin recovers GLONASS phase natively!
    m1020 = _sample_1020(slot=1, fcn=-4)
    m1084 = Msm4Message(
        system=MsmSystem.GLONASS,
        station_id=2011,
        epoch=(1 << 27) | 3_600_000,
        multiple_message=False,
        iod=0,
        clock_steering=0,
        external_clock=0,
        smoothing=False,
        smoothing_interval=0,
        cells=(
            Msm4Cell(
                satellite_id=1,
                signal_id=2,  # 1C
                pseudorange_m=20_500_000.0,
                phase_range_m=20_500_040.0,
                lock_time_s=32.0,
                half_cycle_ambiguity=False,
                cnr_dbhz=45.0,
            ),
            Msm4Cell(
                satellite_id=1,
                signal_id=8,  # 2C
                pseudorange_m=20_500_004.0,
                phase_range_m=20_500_045.0,
                lock_time_s=32.0,
                half_cycle_ambiguity=False,
                cnr_dbhz=42.0,
            ),
        ),
    )
    stream_glo = (
        frame_message_payload(_sample_1006().encode())
        + frame_message_payload(_sample_1033().encode())
        + frame_message_payload(m1020.encode())
        + frame_message_payload(m1084.encode())
    )
    res_glo = decode_with_convbin(stream_glo, binary=convbin)
    assert res_glo.returncode == 0
    assert res_glo.approx_position_xyz == pytest.approx(
        (6246471.2763, 820848.7363, 994267.9301), abs=1e-4
    )
    # 1020 FCN=-4 unlocks GLONASS L1C and L2C carrier phase in unmodified convbin!
    assert "L1C" in res_glo.sys_obs_types["R"] and "L2C" in res_glo.sys_obs_types["R"]
    r01 = res_glo.epochs[0].satellites["R01"]
    l1_wl = glonass_wavelength_m(1, -4)
    l2_wl = glonass_wavelength_m(2, -4)
    assert abs(r01["L1C"].value * l1_wl - 20_500_040.0) <= FINE_PH_HALF_LSB_M + 1e-3
    assert abs(r01["L2C"].value * l2_wl - 20_500_045.0) <= FINE_PH_HALF_LSB_M + 1e-3

    # 2. RTCM 1006 + 1094 (Galileo MSM4: E04 1C+5Q, E19 7Q)
    stream_gal = frame_message_payload(_sample_1006().encode()) + frame_message_payload(
        _sample_1094().encode()
    )
    res_gal = decode_with_convbin(stream_gal, binary=convbin)
    assert res_gal.returncode == 0
    assert "E" in res_gal.sys_obs_types
    assert "E04" in res_gal.epochs[0].satellites
    assert abs(res_gal.epochs[0].satellites["E04"]["C1C"].value - 23_123_456.78) <= (
        FINE_PR_HALF_LSB_M + 1e-3
    )
    assert abs(res_gal.epochs[0].satellites["E04"]["C5Q"].value - 23_123_460.11) <= (
        FINE_PR_HALF_LSB_M + 1e-3
    )


def test_b06_b07_native_rtklib_and_glab_cross_decode() -> None:
    repo = Path(__file__).resolve().parents[3]
    source_env = os.environ.get("RTKLIB_SOURCE")
    if source_env:
        exe, _ = build_rtklib_decoder(repo, Path(source_env))
        stream = b"".join(
            frame_message_payload(m.encode())
            for m in (
                _sample_1006(),
                _sample_1033(),
                _sample_1020(slot=2, fcn=5),
                _sample_1230(),
                _sample_1094(),
            )
        )
        rep = decode_with_rtklib_native(exe, stream)
        assert rep["summary"]["crc_errors"] == 0
        assert rep["summary"]["nmsg3_1006"] == 1
        assert rep["summary"]["nmsg3_1033"] == 1
        assert rep["summary"]["nmsg3_1020"] == 1
        assert rep["summary"]["nmsg3_1094"] == 1
        assert rep["summary"]["nmsg3_1230"] == 1
        ev_1006 = rep["events"][0]
        assert ev_1006["hgt_m"] == pytest.approx(0.1710, abs=1e-4)
        ev_1033 = rep["events"][1]
        assert ev_1033["rectype"] == "SEPT POLARX5"
        assert ev_1033["antdes"] == "SEPCHOKE_B3E6   SPKE"
        ev_1020 = rep["events"][2]
        assert ev_1020["geph_fcns"]["2"] == 5

    if GLAB_DEFAULT_SOURCE.is_dir():
        glab_exe, _ = build_glab_rtcm1005_decoder(repo, GLAB_DEFAULT_SOURCE)
        stream_g = (
            frame_message_payload(_sample_1006().encode())
            + frame_message_payload(_sample_1008().encode())
            + frame_message_payload(_sample_1094().encode())
        )
        gres = decode_rtcm1005_with_glab(glab_exe, stream_g)
        assert gres["summary"]["frame_count"] == 3
        assert gres["summary"]["crc_ok_count"] == 3
        assert gres["summary"]["crc_fail_count"] == 0
        f1006 = gres["frames"][0]
        assert f1006["message_number"] == 1006
        assert f1006["decoded"] is True
        assert f1006["antenna_height_m"] == pytest.approx(0.1710, abs=1e-4)
        assert f1006["ecef_x_m"] == pytest.approx(6246471.2763, abs=1e-4)
        f1008 = gres["frames"][1]
        assert f1008["message_number"] == 1008
        assert f1008["antenna_descriptor"] == "TRM59800.00     NONE"
