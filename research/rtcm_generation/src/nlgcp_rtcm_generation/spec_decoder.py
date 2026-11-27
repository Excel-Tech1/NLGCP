"""Clean-room independent RTCM 3.x (10403.3) binary frame & message decoder (B-07).

Design independence guarantees:
- Shares ZERO code with ``nlgcp_rtcm_generation.messages``, ``bitstream.py``,
  ``framing.py``, or ``nlgcp_rtcm_replay.crc``;
- Uses a standalone bit-by-bit CRC-24Q verifier (generator polynomial
  ``0x1864CFB``) rather than any lookup table from Phase 9;
- Decodes RTCM 3.x messages directly from RTCM 10403.3 bitfield definitions:
  ``1005``, ``1006``, ``1007``, ``1008``, ``1020``, ``1033``, ``1230``,
  and MSM4 ``1074`` (GPS), ``1084`` (GLONASS), ``1094`` (Galileo).

Honest scope note:
An in-repo clean-room specification decoder verifies bit-level self-consistency
and independently cross-checks RTKLIB v2.4.2-p13 + ESA/gAGE-UPC gLAB v6.0.0,
but does NOT substitute for physical commercial GNSS receiver hardware testing
(which remains ``BLOCKED_HARDWARE_ACCESS``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_CRC24Q_POLY = 0x1864CFB
_CLIGHT_M_S = 299_792_458.0
_RANGE_MS_M = _CLIGHT_M_S * 1.0e-3

_GPS_SIGNALS: dict[int, str] = {
    2: "1C", 3: "1P", 4: "1W", 5: "1Y", 6: "1M",
    8: "2C", 9: "2P", 10: "2W", 11: "2Y", 12: "2M",
    15: "2S", 16: "2L", 17: "2X",
    22: "5I", 23: "5Q", 24: "5X",
    30: "1S", 31: "1L", 32: "1X",
}
_GLONASS_SIGNALS: dict[int, str] = {
    2: "1C", 3: "1P", 8: "2C", 9: "2P", 11: "3I", 12: "3Q", 13: "3X",
}
_GALILEO_SIGNALS: dict[int, str] = {
    2: "1C", 3: "1A", 4: "1B", 5: "1X", 6: "1Z",
    8: "6C", 9: "6A", 10: "6B", 11: "6X", 12: "6Z",
    14: "7I", 15: "7Q", 16: "7X",
    18: "8I", 19: "8Q", 20: "8X",
    22: "5I", 23: "5Q", 24: "5X",
}


def standalone_crc24q(data: bytes) -> int:
    """Bit-by-bit CRC-24Q over preamble + header + payload (independent of Phase 9)."""
    crc = 0
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= _CRC24Q_POLY
    return crc & 0xFFFFFF


class _BitCursor:
    """Minimal standalone MSB-first bit cursor."""

    __slots__ = ("_buf", "_bit")

    def __init__(self, buf: bytes) -> None:
        self._buf = buf
        self._bit = 0

    @property
    def remaining_bits(self) -> int:
        return len(self._buf) * 8 - self._bit

    def u(self, nbits: int) -> int:
        if nbits < 0 or self._bit + nbits > len(self._buf) * 8:
            raise ValueError(f"bitstream underflow requesting {nbits} bits")
        val = 0
        for _ in range(nbits):
            b = self._buf[self._bit >> 3]
            shift = 7 - (self._bit & 7)
            val = (val << 1) | ((b >> shift) & 1)
            self._bit += 1
        return val

    def s(self, nbits: int) -> int:
        """Two's-complement signed integer."""
        raw = self.u(nbits)
        sign_bit = 1 << (nbits - 1)
        return raw - (1 << nbits) if (raw & sign_bit) else raw

    def sm(self, nbits: int) -> int:
        """Sign-magnitude integer (used by RTCM 1020 GLONASS ephemeris)."""
        sign = self.u(1)
        mag = self.u(nbits - 1)
        return -mag if sign else mag

    def ascii_len_prefixed(self) -> str:
        count = self.u(8)
        chars = bytes(self.u(8) for _ in range(count))
        return chars.decode("ascii", errors="replace")


def _decode_1005_1006(cur: _BitCursor, msg_no: int) -> dict[str, Any]:
    station_id = cur.u(12)
    itrf_year = cur.u(6)
    gps = bool(cur.u(1))
    glo = bool(cur.u(1))
    gal = bool(cur.u(1))
    ref_ind = bool(cur.u(1))
    x_m = cur.s(38) * 1.0e-4
    osc = bool(cur.u(1))
    _res = cur.u(1)
    y_m = cur.s(38) * 1.0e-4
    qci = cur.u(2)
    z_m = cur.s(38) * 1.0e-4
    out: dict[str, Any] = {
        "station_id": station_id,
        "itrf_realization_year": itrf_year,
        "gps_indicator": gps,
        "glonass_indicator": glo,
        "galileo_indicator": gal,
        "reference_station_indicator": ref_ind,
        "oscillator_indicator": osc,
        "quarter_cycle_indicator": qci,
        "ecef_x_m": round(x_m, 4),
        "ecef_y_m": round(y_m, 4),
        "ecef_z_m": round(z_m, 4),
    }
    if msg_no == 1006:
        out["antenna_height_m"] = round(cur.u(16) * 1.0e-4, 4)
    return out


def _decode_1007_1008_1033(cur: _BitCursor, msg_no: int) -> dict[str, Any]:
    station_id = cur.u(12)
    ant_desc = cur.ascii_len_prefixed()
    ant_setup = cur.u(8)
    out: dict[str, Any] = {
        "station_id": station_id,
        "antenna_descriptor": ant_desc,
        "antenna_setup_id": ant_setup,
    }
    if msg_no in (1008, 1033):
        out["antenna_serial"] = cur.ascii_len_prefixed()
    if msg_no == 1033:
        out["receiver_type"] = cur.ascii_len_prefixed()
        out["receiver_firmware"] = cur.ascii_len_prefixed()
        out["receiver_serial"] = cur.ascii_len_prefixed()
    return out


def _decode_1020(cur: _BitCursor) -> dict[str, Any]:
    sat_id = cur.u(6)
    fcn_code = cur.u(5)
    fcn = fcn_code - 7
    alm_health_p1 = cur.u(4)
    tk_h = cur.u(5)
    tk_m = cur.u(6)
    tk_s = cur.u(1) * 30
    bn_svh = cur.u(1)
    p2 = cur.u(1)
    tb = cur.u(7)
    vx_kms = cur.sm(24) * (2.0**-20)
    x_km = cur.sm(27) * (2.0**-11)
    ax_kms2 = cur.sm(5) * (2.0**-30)
    vy_kms = cur.sm(24) * (2.0**-20)
    y_km = cur.sm(27) * (2.0**-11)
    ay_kms2 = cur.sm(5) * (2.0**-30)
    vz_kms = cur.sm(24) * (2.0**-20)
    z_km = cur.sm(27) * (2.0**-11)
    az_kms2 = cur.sm(5) * (2.0**-30)
    p3 = cur.u(1)
    gamma_n = cur.sm(11) * (2.0**-40)
    _p_ln = cur.u(3)
    tau_n = cur.sm(22) * (2.0**-30)
    dtau_n = cur.sm(5) * (2.0**-30)
    en_age = cur.u(5)
    p4 = cur.u(1)
    ft = cur.u(4)
    nt = cur.u(11)
    m_type = cur.u(2)
    add_flag = cur.u(1)
    return {
        "satellite_id": sat_id,
        "fcn": fcn,
        "fcn_code": fcn_code,
        "alm_health_p1": alm_health_p1,
        "tk_hms": f"{tk_h:02d}:{tk_m:02d}:{tk_s:02d}",
        "svh": bn_svh,
        "p2": p2,
        "tb": tb,
        "pos_m": [x_km * 1000.0, y_km * 1000.0, z_km * 1000.0],
        "vel_m_s": [vx_kms * 1000.0, vy_kms * 1000.0, vz_kms * 1000.0],
        "acc_m_s2": [ax_kms2 * 1000.0, ay_kms2 * 1000.0, az_kms2 * 1000.0],
        "p3": p3,
        "gamma_n": gamma_n,
        "tau_n": tau_n,
        "dtau_n": dtau_n,
        "age_days": en_age,
        "p4": p4,
        "ft": ft,
        "nt": nt,
        "glonass_m": m_type,
        "additional_data_flag": add_flag,
    }


def _decode_1230(cur: _BitCursor) -> dict[str, Any]:
    station_id = cur.u(12)
    bias_indicator = bool(cur.u(1))
    _reserved = cur.u(3)
    fdma_mask = cur.u(4)
    signal_names = ("L1_CA", "L1_P", "L2_CA", "L2_P")
    biases_m: dict[str, float | None] = {}
    for idx, name in enumerate(signal_names):
        bit = (fdma_mask >> (3 - idx)) & 1
        if bit:
            raw = cur.s(16)
            biases_m[name] = None if raw == -(1 << 15) else round(raw * 0.02, 4)
    return {
        "station_id": station_id,
        "code_phase_bias_indicator": bias_indicator,
        "fdma_signals_mask": fdma_mask,
        "biases_m": biases_m,
    }


def _decode_msm4(cur: _BitCursor, msg_no: int) -> dict[str, Any]:
    sys_name, sig_table = {
        1074: ("GPS", _GPS_SIGNALS),
        1084: ("GLONASS", _GLONASS_SIGNALS),
        1094: ("GALILEO", _GALILEO_SIGNALS),
    }[msg_no]
    station_id = cur.u(12)
    epoch_raw = cur.u(30)
    multiple_message = bool(cur.u(1))
    iod = cur.u(3)
    _reserved = cur.u(7)
    clock_steering = cur.u(2)
    external_clock = cur.u(2)
    smoothing = bool(cur.u(1))
    smoothing_interval = cur.u(3)

    sats = [sat_id for sat_id in range(1, 65) if cur.u(1)]
    sigs = [sig_id for sig_id in range(1, 33) if cur.u(1)]
    cell_mask_len = len(sats) * len(sigs)
    if cell_mask_len > 64:
        raise ValueError(f"MSM4 cell mask size {cell_mask_len} exceeds RTCM limit 64")
    active_pairs: list[tuple[int, int]] = []
    for sat_id in sats:
        for sig_id in sigs:
            if cur.u(1):
                active_pairs.append((sat_id, sig_id))

    rough_int = [cur.u(8) for _ in sats]
    rough_mod = [cur.u(10) for _ in sats]
    rough_by_sat: dict[int, float | None] = {}
    for sat_id, ri, rm in zip(sats, rough_int, rough_mod, strict=True):
        rough_by_sat[sat_id] = None if ri == 255 else (ri + rm / 1024.0) * _RANGE_MS_M

    n_cells = len(active_pairs)
    fine_pr_raw = [cur.s(15) for _ in range(n_cells)]
    fine_ph_raw = [cur.s(22) for _ in range(n_cells)]
    lock_ind = [cur.u(4) for _ in range(n_cells)]
    half_cyc = [bool(cur.u(1)) for _ in range(n_cells)]
    cnr = [cur.u(6) for _ in range(n_cells)]

    cells: list[dict[str, Any]] = []
    for idx, (sat_id, sig_id) in enumerate(active_pairs):
        rough = rough_by_sat[sat_id]
        pr_m: float | None = None
        ph_m: float | None = None
        if rough is not None and fine_pr_raw[idx] != -(1 << 14):
            pr_m = rough + fine_pr_raw[idx] * _RANGE_MS_M / (1 << 24)
        if rough is not None and fine_ph_raw[idx] != -(1 << 21):
            ph_m = rough + fine_ph_raw[idx] * _RANGE_MS_M / (1 << 29)
        cells.append(
            {
                "satellite_id": sat_id,
                "signal_id": sig_id,
                "signal_code": sig_table.get(sig_id, f"UNKNOWN({sig_id})"),
                "pseudorange_m": pr_m,
                "phase_range_m": ph_m,
                "lock_indicator": lock_ind[idx],
                "half_cycle_ambiguity": half_cyc[idx],
                "cnr_dbhz": float(cnr[idx]),
            }
        )

    out: dict[str, Any] = {
        "system": sys_name,
        "station_id": station_id,
        "epoch_raw": epoch_raw,
        "multiple_message": multiple_message,
        "iod": iod,
        "clock_steering": clock_steering,
        "external_clock": external_clock,
        "smoothing": smoothing,
        "smoothing_interval": smoothing_interval,
        "satellites": sats,
        "signal_ids": sigs,
        "cells": cells,
    }
    if sys_name == "GLONASS":
        out["epoch_dow"] = epoch_raw >> 27
        out["epoch_tod_ms"] = epoch_raw & 0x07FFFFFF
    else:
        out["epoch_ms"] = epoch_raw
    return out


@dataclass(frozen=True, slots=True)
class DecodedSpecFrame:
    message_number: int
    payload_length: int
    frame_length: int
    crc_ok: bool
    decoded: bool
    fields: dict[str, Any]
    note: str = ""


def decode_rtcm_stream_independent_spec(raw: bytes) -> dict[str, Any]:
    """Decode an RTCM 3.x byte stream using the standalone RTCM 10403.3 parser."""
    frames: list[DecodedSpecFrame] = []
    pos = 0
    n = len(raw)
    stray_bytes = 0
    truncated_tail = False

    while pos < n:
        if raw[pos] != 0xD3:
            stray_bytes += 1
            pos += 1
            continue
        if pos + 6 > n:
            truncated_tail = True
            break
        reserved = (raw[pos + 1] >> 2) & 0x3F
        plen = ((raw[pos + 1] & 0x03) << 8) | raw[pos + 2]
        total = 3 + plen + 3
        if reserved != 0 or plen < 2:
            stray_bytes += 1
            pos += 1
            continue
        if pos + total > n:
            truncated_tail = True
            break
        body = raw[pos : pos + 3 + plen]
        declared_crc = (
            (raw[pos + 3 + plen] << 16) | (raw[pos + 4 + plen] << 8) | raw[pos + 5 + plen]
        )
        crc_ok = standalone_crc24q(body) == declared_crc
        payload = raw[pos + 3 : pos + 3 + plen]
        cur = _BitCursor(payload)
        msg_no = cur.u(12)

        if not crc_ok:
            frames.append(
                DecodedSpecFrame(msg_no, plen, total, False, False, {}, "CRC24Q_FAILED")
            )
            pos += total
            continue

        decoded = True
        note = ""
        fields: dict[str, Any] = {}
        try:
            if msg_no in (1005, 1006):
                fields = _decode_1005_1006(cur, msg_no)
            elif msg_no in (1007, 1008, 1033):
                fields = _decode_1007_1008_1033(cur, msg_no)
            elif msg_no == 1020:
                fields = _decode_1020(cur)
            elif msg_no == 1230:
                fields = _decode_1230(cur)
            elif msg_no in (1074, 1084, 1094):
                fields = _decode_msm4(cur, msg_no)
            else:
                decoded = False
                note = f"UNSUPPORTED_MESSAGE_TYPE_{msg_no}"
        except ValueError as exc:
            decoded = False
            note = f"DECODE_ERROR:{exc}"

        frames.append(DecodedSpecFrame(msg_no, plen, total, True, decoded, fields, note))
        pos += total

    msg_hist: dict[str, int] = {}
    for fr in frames:
        k = str(fr.message_number)
        msg_hist[k] = msg_hist.get(k, 0) + 1

    return {
        "decoder": "NLGCP Clean-Room RTCM 10403.3 Specification Decoder (B-07)",
        "shares_encoder_or_phase9_code": False,
        "frames": [
            {
                "message_number": fr.message_number,
                "payload_length": fr.payload_length,
                "frame_length": fr.frame_length,
                "crc_ok": fr.crc_ok,
                "decoded": fr.decoded,
                "fields": fr.fields,
                "note": fr.note,
            }
            for fr in frames
        ],
        "summary": {
            "total_bytes": n,
            "frame_count": len(frames),
            "crc_ok_count": sum(1 for f in frames if f.crc_ok),
            "crc_fail_count": sum(1 for f in frames if not f.crc_ok),
            "decoded_count": sum(1 for f in frames if f.decoded),
            "stray_bytes": stray_bytes,
            "truncated_tail": truncated_tail,
            "message_histogram": msg_hist,
        },
    }
