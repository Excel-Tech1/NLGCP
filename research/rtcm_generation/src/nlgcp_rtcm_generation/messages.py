"""Bit-level RTCM 3.x message layouts for 1005, 1074 and 1084.

Layout references (no licensed RTCM standard text is reproduced here):

* RTKLIB v2.4.2-p13, commit ``71db0ffa0d9735697c6adfd06fdf766d0e5ce807``
  (the provenance pinned by NLGCP):
  - ``src/rtcm3e.c`` ``encode_type1005`` for RTCM 1005;
  - ``src/rtcm3e.c`` ``encode_msm_head`` / ``encode_msm4`` and the
    helper field encoders for MSM4;
  - ``src/rtcm3.c`` ``decode_type1005`` / ``decode_msm_head`` /
    ``decode_msm4`` for length and field-position cross-checks;
  - ``src/rtcm3.c`` signal-ID tables for GPS and GLONASS;
  - ``src/rtklib.h`` satellite PRN limits.

These encoders serialize caller-supplied fields only.  They do not
measure, interpolate, admit, or scientifically validate coordinates or
observations.  Every value used in the NLGCP test-suite is synthetic test
data and must never be attributed to a real station.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from nlgcp_rtcm_generation.bitstream import BitWriter

MESSAGE_NUMBER_1005 = 1005
MESSAGE_NUMBER_1006 = 1006
MESSAGE_NUMBER_1007 = 1007
MESSAGE_NUMBER_1008 = 1008
MESSAGE_NUMBER_1020 = 1020
MESSAGE_NUMBER_1033 = 1033
MESSAGE_NUMBER_1074 = 1074
MESSAGE_NUMBER_1084 = 1084
MESSAGE_NUMBER_1094 = 1094
MESSAGE_NUMBER_1230 = 1230

RANGE_MS = 299_792_458.0 * 1e-3
GPS_WEEK_MS = 604_800_000
GLONASS_DAY_MS = 86_400_000
MAX_STATION_ID = 4095
MAX_MSM_CELLS = 64
MSM_SATELLITE_MASK_BITS = 64
MSM_SIGNAL_MASK_BITS = 32
MSM4_SATELLITE_BITS = 18
MSM4_SIGNAL_BITS = 48
MSM4_HEADER_BITS = 169

ECEF_SCALE_M = 0.0001
ECEF_MIN = -(1 << 37)
ECEF_MAX = (1 << 37) - 1
FINE_PSEUDORANGE_LIMIT_M = 292.7
FINE_PHASE_LIMIT_M = 1171.0
FINE_PSEUDORANGE_MISSING = -(1 << 14)
FINE_PHASE_MISSING = -(1 << 21)

GPS_SATELLITE_ID_MAX = 32
GLONASS_SATELLITE_ID_MAX = 24
GALILEO_SATELLITE_ID_MAX = 36
MAX_ANTENNA_HEIGHT_M = 6.5535
MAX_DESCRIPTOR_LEN = 31

# RTKLIB v2.4.2-p13 src/rtcm3.c lines 64-75 (1-based RTCM MSM signal IDs;
# C array index 0 / signal ID 1 is reserved "" in both GPS and GLONASS).
GPS_MSM_SIGNAL_IDS: dict[int, str] = {
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
GLONASS_MSM_SIGNAL_IDS: dict[int, str] = {
    2: "1C",
    3: "1P",
    8: "2C",
    9: "2P",
    11: "3I",
    12: "3Q",
    13: "3X",
}
# RTKLIB v2.4.2-p13 src/rtcm3.c lines 76-81 (1-based Galileo MSM signal IDs).
GALILEO_MSM_SIGNAL_IDS: dict[int, str] = {
    2: "1C",
    3: "1A",
    4: "1B",
    5: "1X",
    6: "1Z",
    8: "6C",
    9: "6A",
    10: "6B",
    11: "6X",
    12: "6Z",
    14: "7I",
    15: "7Q",
    16: "7X",
    18: "8I",
    19: "8Q",
    20: "8X",
    22: "5I",
    23: "5Q",
    24: "5X",
}


class MsmSystem(StrEnum):
    GPS = "GPS"
    GLONASS = "GLONASS"
    GALILEO = "GALILEO"


class MessageInputError(ValueError):
    """A caller-supplied RTCM message field is missing or unrepresentable."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


def _require_exact_keys(
    mapping: Mapping[str, object], required: frozenset[str], name: str
) -> None:
    keys = set(mapping)
    missing = required - keys
    if missing:
        raise MessageInputError(
            f"{name}: missing required field(s): {', '.join(sorted(missing))}",
            missing=True,
        )
    unknown = keys - required
    if unknown:
        raise MessageInputError(
            f"{name}: unexpected field(s): {', '.join(sorted(unknown))}"
        )


def _as_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MessageInputError(f"{name}: an integer is required")
    if not minimum <= value <= maximum:
        raise MessageInputError(
            f"{name}: {value} is outside the representable range "
            f"[{minimum}, {maximum}]"
        )
    return value


def _as_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MessageInputError(f"{name}: a numeric value is required")
    converted = float(value)
    if not math.isfinite(converted):
        raise MessageInputError(f"{name}: NaN and infinity are not representable")
    return converted


def _as_bool(name: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise MessageInputError(f"{name}: a boolean (or 0/1 integer) is required")


def _round_half_up(value: float) -> int:
    """RTKLIB ``ROUND`` semantics: floor(value + 0.5)."""
    return int(math.floor(value + 0.5))


def _quantize_ecef(name: str, value: float) -> int:
    scaled = _round_half_up(value / ECEF_SCALE_M)
    if not ECEF_MIN <= scaled <= ECEF_MAX:
        raise MessageInputError(
            f"{name}: {value} m is outside the signed 38-bit 0.1 mm range"
        )
    return scaled


def _to_msm_lock(lock_time_s: float) -> int:
    """RTKLIB v2.4.2-p13 ``to_msm_lock`` (rtcm3e.c lines 114-131)."""
    if lock_time_s < 0.0:
        raise MessageInputError("lock_time_s: a non-negative duration is required")
    if lock_time_s < 0.032:
        return 0
    if lock_time_s < 0.064:
        return 1
    if lock_time_s < 0.128:
        return 2
    if lock_time_s < 0.256:
        return 3
    if lock_time_s < 0.512:
        return 4
    if lock_time_s < 1.024:
        return 5
    if lock_time_s < 2.048:
        return 6
    if lock_time_s < 4.096:
        return 7
    if lock_time_s < 8.192:
        return 8
    if lock_time_s < 16.384:
        return 9
    if lock_time_s < 32.768:
        return 10
    if lock_time_s < 65.536:
        return 11
    if lock_time_s < 131.072:
        return 12
    if lock_time_s < 262.144:
        return 13
    if lock_time_s < 524.288:
        return 14
    return 15


@dataclass(frozen=True, slots=True)
class ReferenceStation1005:
    """RTCM 1005 Reference Station ARP position payload."""

    station_id: int
    itrf_realization_year: int
    gps_indicator: bool
    glonass_indicator: bool
    galileo_indicator: bool
    reference_station_indicator: bool
    ecef_x_m: float
    ecef_y_m: float
    ecef_z_m: float
    oscillator_indicator: bool
    quarter_cycle_indicator: int

    _REQUIRED_FIELDS = frozenset(
        {
            "station_id",
            "itrf_realization_year",
            "gps_indicator",
            "glonass_indicator",
            "galileo_indicator",
            "reference_station_indicator",
            "ecef_x_m",
            "ecef_y_m",
            "ecef_z_m",
            "oscillator_indicator",
            "quarter_cycle_indicator",
        }
    )

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1005")
        message = cls(
            station_id=_as_int("station_id", fields["station_id"], 0, MAX_STATION_ID),
            itrf_realization_year=_as_int(
                "itrf_realization_year", fields["itrf_realization_year"], 0, 63
            ),
            gps_indicator=_as_bool("gps_indicator", fields["gps_indicator"]),
            glonass_indicator=_as_bool(
                "glonass_indicator", fields["glonass_indicator"]
            ),
            galileo_indicator=_as_bool(
                "galileo_indicator", fields["galileo_indicator"]
            ),
            reference_station_indicator=_as_bool(
                "reference_station_indicator", fields["reference_station_indicator"]
            ),
            ecef_x_m=_as_float("ecef_x_m", fields["ecef_x_m"]),
            ecef_y_m=_as_float("ecef_y_m", fields["ecef_y_m"]),
            ecef_z_m=_as_float("ecef_z_m", fields["ecef_z_m"]),
            oscillator_indicator=_as_bool(
                "oscillator_indicator", fields["oscillator_indicator"]
            ),
            quarter_cycle_indicator=_as_int(
                "quarter_cycle_indicator", fields["quarter_cycle_indicator"], 0, 3
            ),
        )
        message.validate()
        return message

    def validate(self) -> None:
        _as_int("station_id", self.station_id, 0, MAX_STATION_ID)
        _as_int("itrf_realization_year", self.itrf_realization_year, 0, 63)
        for flag_name, flag_value in (
            ("gps_indicator", self.gps_indicator),
            ("glonass_indicator", self.glonass_indicator),
            ("galileo_indicator", self.galileo_indicator),
            ("reference_station_indicator", self.reference_station_indicator),
            ("oscillator_indicator", self.oscillator_indicator),
        ):
            if not isinstance(flag_value, bool):
                raise MessageInputError(f"{flag_name}: a boolean is required")
        for name, value in (
            ("ecef_x_m", self.ecef_x_m),
            ("ecef_y_m", self.ecef_y_m),
            ("ecef_z_m", self.ecef_z_m),
        ):
            numeric = _as_float(name, value)
            _quantize_ecef(name, numeric)
        _as_int("quarter_cycle_indicator", self.quarter_cycle_indicator, 0, 3)

    def encode(self) -> bytes:
        self.validate()
        writer = BitWriter(max_bits=152)
        writer.write_unsigned(MESSAGE_NUMBER_1005, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(self.itrf_realization_year, 6)
        writer.write_unsigned(int(self.gps_indicator), 1)
        writer.write_unsigned(int(self.glonass_indicator), 1)
        writer.write_unsigned(int(self.galileo_indicator), 1)
        writer.write_unsigned(int(self.reference_station_indicator), 1)
        writer.write_signed(_quantize_ecef("ecef_x_m", self.ecef_x_m), 38)
        writer.write_unsigned(int(self.oscillator_indicator), 1)
        writer.write_unsigned(0, 1)  # reserved
        writer.write_signed(_quantize_ecef("ecef_y_m", self.ecef_y_m), 38)
        writer.write_unsigned(self.quarter_cycle_indicator, 2)
        writer.write_signed(_quantize_ecef("ecef_z_m", self.ecef_z_m), 38)
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class Msm4Cell:
    """One MSM4 satellite/signal cell with all required observables."""

    satellite_id: int
    signal_id: int
    pseudorange_m: float
    phase_range_m: float
    lock_time_s: float
    half_cycle_ambiguity: bool
    cnr_dbhz: float

    _REQUIRED_FIELDS = frozenset(
        {
            "satellite_id",
            "signal_id",
            "pseudorange_m",
            "phase_range_m",
            "lock_time_s",
            "half_cycle_ambiguity",
            "cnr_dbhz",
        }
    )

    @classmethod
    def from_mapping(
        cls, system: MsmSystem, row: Mapping[str, object], index: int
    ) -> Self:
        name = f"observations[{index}]"
        _require_exact_keys(row, cls._REQUIRED_FIELDS, name)
        signal_table = _signal_table(system)
        satellite_max = (
            GPS_SATELLITE_ID_MAX
            if system == MsmSystem.GPS
            else GLONASS_SATELLITE_ID_MAX
            if system == MsmSystem.GLONASS
            else GALILEO_SATELLITE_ID_MAX
        )
        cell = cls(
            satellite_id=_as_int(
                f"{name}.satellite_id", row["satellite_id"], 1, satellite_max
            ),
            signal_id=_as_int(f"{name}.signal_id", row["signal_id"], 1, 32),
            pseudorange_m=_as_float(f"{name}.pseudorange_m", row["pseudorange_m"]),
            phase_range_m=_as_float(f"{name}.phase_range_m", row["phase_range_m"]),
            lock_time_s=_as_float(f"{name}.lock_time_s", row["lock_time_s"]),
            half_cycle_ambiguity=_as_bool(
                f"{name}.half_cycle_ambiguity", row["half_cycle_ambiguity"]
            ),
            cnr_dbhz=_as_float(f"{name}.cnr_dbhz", row["cnr_dbhz"]),
        )
        if cell.signal_id not in signal_table:
            raise MessageInputError(
                f"{name}.signal_id: {cell.signal_id} is not a defined "
                f"{system.value} MSM signal ID"
            )
        cell.validate(name, system=system)
        return cell

    def validate(self, name: str = "cell", *, system: MsmSystem | None = None) -> None:
        satellite_max = (
            GPS_SATELLITE_ID_MAX
            if system == MsmSystem.GPS
            else GLONASS_SATELLITE_ID_MAX
            if system == MsmSystem.GLONASS
            else GALILEO_SATELLITE_ID_MAX
            if system == MsmSystem.GALILEO
            else MSM_SATELLITE_MASK_BITS
        )
        _as_int(f"{name}.satellite_id", self.satellite_id, 1, satellite_max)
        _as_int(f"{name}.signal_id", self.signal_id, 1, MSM_SIGNAL_MASK_BITS)
        if system is not None and self.signal_id not in _signal_table(system):
            raise MessageInputError(
                f"{name}.signal_id: {self.signal_id} is not a defined "
                f"{system.value} MSM signal ID"
            )
        if not isinstance(self.half_cycle_ambiguity, bool):
            raise MessageInputError(
                f"{name}.half_cycle_ambiguity: a boolean is required"
            )
        for field_name, value in (
            ("pseudorange_m", self.pseudorange_m),
            ("phase_range_m", self.phase_range_m),
            ("lock_time_s", self.lock_time_s),
            ("cnr_dbhz", self.cnr_dbhz),
        ):
            _as_float(f"{name}.{field_name}", value)
        if self.pseudorange_m <= 0.0:
            raise MessageInputError(
                f"{name}.pseudorange_m: a positive pseudorange is required"
            )
        if self.pseudorange_m >= RANGE_MS * 255.0:
            raise MessageInputError(
                f"{name}.pseudorange_m: {self.pseudorange_m} m exceeds the "
                "8-bit rough-range domain"
            )
        if not 0.0 <= self.cnr_dbhz <= 63.0:
            raise MessageInputError(
                f"{name}.cnr_dbhz: {self.cnr_dbhz} is outside [0, 63] dB-Hz"
            )
        _to_msm_lock(self.lock_time_s)


@dataclass(frozen=True, slots=True)
class Msm4Message:
    """RTCM 1074 (GPS) or 1084 (GLONASS) MSM4 payload."""

    system: MsmSystem
    station_id: int
    epoch: int
    multiple_message: bool
    iod: int
    clock_steering: int
    external_clock: int
    smoothing: bool
    smoothing_interval: int
    cells: tuple[Msm4Cell, ...] = field(default_factory=tuple)

    @property
    def message_number(self) -> int:
        if self.system == MsmSystem.GPS:
            return MESSAGE_NUMBER_1074
        if self.system == MsmSystem.GALILEO:
            return MESSAGE_NUMBER_1094
        return MESSAGE_NUMBER_1084

    @classmethod
    def from_mapping(
        cls,
        system: MsmSystem,
        fields: Mapping[str, object],
        observations: Sequence[Mapping[str, object]],
    ) -> Self:
        if system in (MsmSystem.GPS, MsmSystem.GALILEO):
            epoch_fields = frozenset({"epoch_ms"})
        else:
            epoch_fields = frozenset({"epoch_dow", "epoch_tod_ms"})
        required = (
            frozenset(
                {
                    "station_id",
                    "multiple_message",
                    "iod",
                    "clock_steering",
                    "external_clock",
                    "smoothing",
                    "smoothing_interval",
                }
            )
            | epoch_fields
        )
        _require_exact_keys(fields, required, system.value)
        if system in (MsmSystem.GPS, MsmSystem.GALILEO):
            epoch = _as_int("epoch_ms", fields["epoch_ms"], 0, GPS_WEEK_MS - 1)
        else:
            dow = _as_int("epoch_dow", fields["epoch_dow"], 0, 6)
            tod_ms = _as_int(
                "epoch_tod_ms", fields["epoch_tod_ms"], 0, GLONASS_DAY_MS - 1
            )
            epoch = (dow << 27) | tod_ms
        if not observations:
            raise MessageInputError(
                f"{system.value}: at least one observation is required", missing=True
            )
        cells = tuple(
            Msm4Cell.from_mapping(system, row, index)
            for index, row in enumerate(observations)
        )
        message = cls(
            system=system,
            station_id=_as_int("station_id", fields["station_id"], 0, MAX_STATION_ID),
            epoch=epoch,
            multiple_message=_as_bool(
                "multiple_message", fields["multiple_message"]
            ),
            iod=_as_int("iod", fields["iod"], 0, 7),
            clock_steering=_as_int(
                "clock_steering", fields["clock_steering"], 0, 3
            ),
            external_clock=_as_int("external_clock", fields["external_clock"], 0, 3),
            smoothing=_as_bool("smoothing", fields["smoothing"]),
            smoothing_interval=_as_int(
                "smoothing_interval", fields["smoothing_interval"], 0, 7
            ),
            cells=cells,
        )
        message.validate()
        return message

    def validate(self) -> None:
        if not self.cells:
            raise MessageInputError("at least one MSM4 cell is required", missing=True)
        _as_int("station_id", self.station_id, 0, MAX_STATION_ID)
        _as_int("epoch", self.epoch, 0, (1 << 30) - 1)
        if self.system in (MsmSystem.GPS, MsmSystem.GALILEO):
            if not 0 <= self.epoch < GPS_WEEK_MS:
                raise MessageInputError(
                    f"epoch: {self.epoch} is outside TOW range [0, {GPS_WEEK_MS - 1}]"
                )
        else:
            dow = self.epoch >> 27
            tod_ms = self.epoch & 0x07FFFFFF
            if not 0 <= dow <= 6:
                raise MessageInputError(
                    f"epoch: GLONASS day-of-week {dow} is outside [0, 6]"
                )
            if not 0 <= tod_ms < GLONASS_DAY_MS:
                raise MessageInputError(
                    f"epoch: GLONASS time-of-day {tod_ms} is outside "
                    f"[0, {GLONASS_DAY_MS - 1}]"
                )
        if not isinstance(self.multiple_message, bool):
            raise MessageInputError("multiple_message: a boolean is required")
        _as_int("iod", self.iod, 0, 7)
        _as_int("clock_steering", self.clock_steering, 0, 3)
        _as_int("external_clock", self.external_clock, 0, 3)
        if not isinstance(self.smoothing, bool):
            raise MessageInputError("smoothing: a boolean is required")
        _as_int("smoothing_interval", self.smoothing_interval, 0, 7)
        seen: set[tuple[int, int]] = set()
        for index, cell in enumerate(self.cells):
            key = (cell.satellite_id, cell.signal_id)
            if key in seen:
                raise MessageInputError(
                    f"observations[{index}]: duplicate satellite/signal cell {key}"
                )
            seen.add(key)
            cell.validate(f"observations[{index}]", system=self.system)
        satellites = {cell.satellite_id for cell in self.cells}
        signals = {cell.signal_id for cell in self.cells}
        if len(satellites) * len(signals) > MAX_MSM_CELLS:
            raise MessageInputError(
                "satellite and signal masks require "
                f"{len(satellites) * len(signals)} cells; the MSM4 limit is "
                f"{MAX_MSM_CELLS}"
            )
        layout = _build_msm_layout(self.cells)
        _fine_codes(layout.ordered_cells, layout.rough_ranges)

    def encode(self) -> bytes:
        self.validate()
        layout = _build_msm_layout(self.cells)
        satellite_set = set(layout.satellites)
        signal_set = set(layout.signals)
        present = {(cell.satellite_id, cell.signal_id) for cell in layout.ordered_cells}
        cell_mask = [
            1 if (satellite_id, signal_id) in present else 0
            for satellite_id in layout.satellites
            for signal_id in layout.signals
        ]
        total_bits = (
            MSM4_HEADER_BITS
            + len(cell_mask)
            + len(layout.satellites) * MSM4_SATELLITE_BITS
            + len(layout.ordered_cells) * MSM4_SIGNAL_BITS
        )
        writer = BitWriter(max_bits=((total_bits + 7) // 8) * 8)
        writer.write_unsigned(self.message_number, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(self.epoch, 30)
        writer.write_unsigned(int(self.multiple_message), 1)
        writer.write_unsigned(self.iod, 3)
        writer.write_unsigned(0, 7)  # reserved
        writer.write_unsigned(self.clock_steering, 2)
        writer.write_unsigned(self.external_clock, 2)
        writer.write_unsigned(int(self.smoothing), 1)
        writer.write_unsigned(self.smoothing_interval, 3)
        for satellite_id in range(1, MSM_SATELLITE_MASK_BITS + 1):
            writer.write_unsigned(1 if satellite_id in satellite_set else 0, 1)
        for signal_id in range(1, MSM_SIGNAL_MASK_BITS + 1):
            writer.write_unsigned(1 if signal_id in signal_set else 0, 1)
        for bit in cell_mask:
            writer.write_unsigned(bit, 1)

        fine_pseudoranges, fine_phases = _fine_codes(
            layout.ordered_cells, layout.rough_ranges
        )
        lock_times = [
            _to_msm_lock(cell.lock_time_s) for cell in layout.ordered_cells
        ]
        half_cycles = [
            int(cell.half_cycle_ambiguity) for cell in layout.ordered_cells
        ]
        cnrs = [_round_half_up(cell.cnr_dbhz) for cell in layout.ordered_cells]
        for value in layout.rough_integers:
            writer.write_unsigned(value, 8)
        for value in layout.rough_modulos:
            writer.write_unsigned(value, 10)
        for value in fine_pseudoranges:
            writer.write_signed(value, 15)
        for value in fine_phases:
            writer.write_signed(value, 22)
        for value in lock_times:
            writer.write_unsigned(value, 4)
        for value in half_cycles:
            writer.write_unsigned(value, 1)
        for value in cnrs:
            writer.write_unsigned(value, 6)
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class _MsmLayout:
    satellites: list[int]
    signals: list[int]
    ordered_cells: list[Msm4Cell]
    rough_integers: list[int]
    rough_modulos: list[int]
    rough_ranges: dict[int, float]


def _build_msm_layout(cells: Sequence[Msm4Cell]) -> _MsmLayout:
    satellites = sorted({cell.satellite_id for cell in cells})
    signals = sorted({cell.signal_id for cell in cells})
    lookup = {(cell.satellite_id, cell.signal_id): cell for cell in cells}
    ordered_cells: list[Msm4Cell] = []
    for satellite_id in satellites:
        for signal_id in signals:
            cell = lookup.get((satellite_id, signal_id))
            if cell is not None:
                ordered_cells.append(cell)
    rough_integers: list[int] = []
    rough_modulos: list[int] = []
    rough_ranges: dict[int, float] = {}
    for satellite_id in satellites:
        reference = next(
            cell for cell in ordered_cells if cell.satellite_id == satellite_id
        )
        scaled = _round_half_up(reference.pseudorange_m * 1024.0 / RANGE_MS)
        integer_ms = scaled >> 10
        if integer_ms >= 255:
            raise MessageInputError(
                f"satellite {satellite_id}: pseudorange "
                f"{reference.pseudorange_m} m exceeds the 254 ms rough-range domain"
            )
        modulo_ms = scaled & 0x3FF
        rough_integers.append(integer_ms)
        rough_modulos.append(modulo_ms)
        rough_ranges[satellite_id] = (
            (integer_ms << 10) + modulo_ms
        ) * RANGE_MS / 1024.0
    return _MsmLayout(
        satellites=satellites,
        signals=signals,
        ordered_cells=ordered_cells,
        rough_integers=rough_integers,
        rough_modulos=rough_modulos,
        rough_ranges=rough_ranges,
    )


def _fine_codes(
    ordered_cells: Sequence[Msm4Cell], rough_ranges: Mapping[int, float]
) -> tuple[list[int], list[int]]:
    fine_pseudoranges: list[int] = []
    fine_phases: list[int] = []
    for index, cell in enumerate(ordered_cells):
        name = f"observations[{index}]"
        rough_range = rough_ranges[cell.satellite_id]
        fine_pseudorange = cell.pseudorange_m - rough_range
        if abs(fine_pseudorange) > FINE_PSEUDORANGE_LIMIT_M:
            raise MessageInputError(
                f"{name}.pseudorange_m: fine pseudorange "
                f"{fine_pseudorange:.3f} m exceeds +/-{FINE_PSEUDORANGE_LIMIT_M} m"
            )
        pseudorange_value = _round_half_up(fine_pseudorange * (1 << 24) / RANGE_MS)
        if not -(1 << 14) < pseudorange_value < (1 << 14):
            raise MessageInputError(
                f"{name}.pseudorange_m: fine pseudorange code "
                f"{pseudorange_value} is not a valid 15-bit value"
            )
        fine_phase = cell.phase_range_m - rough_range
        if abs(fine_phase) > FINE_PHASE_LIMIT_M:
            raise MessageInputError(
                f"{name}.phase_range_m: fine phase {fine_phase:.3f} m "
                f"exceeds +/-{FINE_PHASE_LIMIT_M} m"
            )
        phase_value = _round_half_up(fine_phase * (1 << 29) / RANGE_MS)
        if not -(1 << 21) < phase_value < (1 << 21):
            raise MessageInputError(
                f"{name}.phase_range_m: fine phase code {phase_value} is not "
                "a valid 22-bit value"
            )
        fine_pseudoranges.append(pseudorange_value)
        fine_phases.append(phase_value)
    return fine_pseudoranges, fine_phases


def _as_ascii_descriptor(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise MessageInputError(f"{name}: an ASCII string is required")
    if len(value) > MAX_DESCRIPTOR_LEN:
        raise MessageInputError(
            f"{name}: length {len(value)} exceeds RTCM 31-character limit"
        )
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MessageInputError(f"{name}: non-ASCII characters are not permitted") from exc
    if any(b < 0x20 or b > 0x7E for b in raw):
        raise MessageInputError(f"{name}: control characters are not permitted")
    return value


@dataclass(frozen=True, slots=True)
class ReferenceStation1006:
    """RTCM 1006 Stationary RTK Reference Station ARP with Antenna Height."""

    station_id: int
    itrf_realization_year: int
    gps_indicator: bool
    glonass_indicator: bool
    galileo_indicator: bool
    reference_station_indicator: bool
    ecef_x_m: float
    ecef_y_m: float
    ecef_z_m: float
    oscillator_indicator: bool
    quarter_cycle_indicator: int
    antenna_height_m: float

    _REQUIRED_FIELDS = ReferenceStation1005._REQUIRED_FIELDS | frozenset({"antenna_height_m"})

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1006")
        base_fields = {k: v for k, v in fields.items() if k != "antenna_height_m"}
        base = ReferenceStation1005.from_mapping(base_fields)
        msg = cls(
            station_id=base.station_id,
            itrf_realization_year=base.itrf_realization_year,
            gps_indicator=base.gps_indicator,
            glonass_indicator=base.glonass_indicator,
            galileo_indicator=base.galileo_indicator,
            reference_station_indicator=base.reference_station_indicator,
            ecef_x_m=base.ecef_x_m,
            ecef_y_m=base.ecef_y_m,
            ecef_z_m=base.ecef_z_m,
            oscillator_indicator=base.oscillator_indicator,
            quarter_cycle_indicator=base.quarter_cycle_indicator,
            antenna_height_m=_as_float("antenna_height_m", fields["antenna_height_m"]),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        ReferenceStation1005(
            station_id=self.station_id,
            itrf_realization_year=self.itrf_realization_year,
            gps_indicator=self.gps_indicator,
            glonass_indicator=self.glonass_indicator,
            galileo_indicator=self.galileo_indicator,
            reference_station_indicator=self.reference_station_indicator,
            ecef_x_m=self.ecef_x_m,
            ecef_y_m=self.ecef_y_m,
            ecef_z_m=self.ecef_z_m,
            oscillator_indicator=self.oscillator_indicator,
            quarter_cycle_indicator=self.quarter_cycle_indicator,
        ).validate()
        h = _as_float("antenna_height_m", self.antenna_height_m)
        if not 0.0 <= h <= MAX_ANTENNA_HEIGHT_M:
            raise MessageInputError(
                f"antenna_height_m: {h} m is outside [0.0, {MAX_ANTENNA_HEIGHT_M}] m"
            )

    def encode(self) -> bytes:
        self.validate()
        writer = BitWriter(max_bits=168)
        writer.write_unsigned(MESSAGE_NUMBER_1006, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(self.itrf_realization_year, 6)
        writer.write_unsigned(int(self.gps_indicator), 1)
        writer.write_unsigned(int(self.glonass_indicator), 1)
        writer.write_unsigned(int(self.galileo_indicator), 1)
        writer.write_unsigned(int(self.reference_station_indicator), 1)
        writer.write_signed(_quantize_ecef("ecef_x_m", self.ecef_x_m), 38)
        writer.write_unsigned(int(self.oscillator_indicator), 1)
        writer.write_unsigned(0, 1)
        writer.write_signed(_quantize_ecef("ecef_y_m", self.ecef_y_m), 38)
        writer.write_unsigned(self.quarter_cycle_indicator, 2)
        writer.write_signed(_quantize_ecef("ecef_z_m", self.ecef_z_m), 38)
        writer.write_unsigned(_round_half_up(self.antenna_height_m / ECEF_SCALE_M), 16)
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class AntennaDescriptor1007:
    """RTCM 1007 Antenna Descriptor."""

    station_id: int
    antenna_descriptor: str
    antenna_setup_id: int = 0

    _REQUIRED_FIELDS = frozenset({"station_id", "antenna_descriptor", "antenna_setup_id"})

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1007")
        msg = cls(
            station_id=_as_int("station_id", fields["station_id"], 0, MAX_STATION_ID),
            antenna_descriptor=_as_ascii_descriptor(
                "antenna_descriptor", fields["antenna_descriptor"]
            ),
            antenna_setup_id=_as_int("antenna_setup_id", fields["antenna_setup_id"], 0, 255),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        _as_int("station_id", self.station_id, 0, MAX_STATION_ID)
        _as_ascii_descriptor("antenna_descriptor", self.antenna_descriptor)
        _as_int("antenna_setup_id", self.antenna_setup_id, 0, 255)

    def encode(self) -> bytes:
        self.validate()
        desc = self.antenna_descriptor.encode("ascii")
        writer = BitWriter(max_bits=40 + len(desc) * 8)
        writer.write_unsigned(MESSAGE_NUMBER_1007, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(len(desc), 8)
        writer.write_bytes(desc)
        writer.write_unsigned(self.antenna_setup_id, 8)
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class AntennaDescriptorSerial1008:
    """RTCM 1008 Antenna Descriptor and Serial Number."""

    station_id: int
    antenna_descriptor: str
    antenna_setup_id: int
    antenna_serial: str

    _REQUIRED_FIELDS = frozenset(
        {"station_id", "antenna_descriptor", "antenna_setup_id", "antenna_serial"}
    )

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1008")
        msg = cls(
            station_id=_as_int("station_id", fields["station_id"], 0, MAX_STATION_ID),
            antenna_descriptor=_as_ascii_descriptor(
                "antenna_descriptor", fields["antenna_descriptor"]
            ),
            antenna_setup_id=_as_int("antenna_setup_id", fields["antenna_setup_id"], 0, 255),
            antenna_serial=_as_ascii_descriptor("antenna_serial", fields["antenna_serial"]),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        _as_int("station_id", self.station_id, 0, MAX_STATION_ID)
        _as_ascii_descriptor("antenna_descriptor", self.antenna_descriptor)
        _as_int("antenna_setup_id", self.antenna_setup_id, 0, 255)
        _as_ascii_descriptor("antenna_serial", self.antenna_serial)

    def encode(self) -> bytes:
        self.validate()
        desc = self.antenna_descriptor.encode("ascii")
        serial = self.antenna_serial.encode("ascii")
        writer = BitWriter(max_bits=48 + (len(desc) + len(serial)) * 8)
        writer.write_unsigned(MESSAGE_NUMBER_1008, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(len(desc), 8)
        writer.write_bytes(desc)
        writer.write_unsigned(self.antenna_setup_id, 8)
        writer.write_unsigned(len(serial), 8)
        writer.write_bytes(serial)
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class ReceiverAntennaDescriptor1033:
    """RTCM 1033 Receiver and Antenna Descriptors."""

    station_id: int
    antenna_descriptor: str
    antenna_setup_id: int
    antenna_serial: str
    receiver_type: str
    receiver_firmware: str
    receiver_serial: str

    _REQUIRED_FIELDS = frozenset(
        {
            "station_id",
            "antenna_descriptor",
            "antenna_setup_id",
            "antenna_serial",
            "receiver_type",
            "receiver_firmware",
            "receiver_serial",
        }
    )

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1033")
        msg = cls(
            station_id=_as_int("station_id", fields["station_id"], 0, MAX_STATION_ID),
            antenna_descriptor=_as_ascii_descriptor(
                "antenna_descriptor", fields["antenna_descriptor"]
            ),
            antenna_setup_id=_as_int("antenna_setup_id", fields["antenna_setup_id"], 0, 255),
            antenna_serial=_as_ascii_descriptor("antenna_serial", fields["antenna_serial"]),
            receiver_type=_as_ascii_descriptor("receiver_type", fields["receiver_type"]),
            receiver_firmware=_as_ascii_descriptor(
                "receiver_firmware", fields["receiver_firmware"]
            ),
            receiver_serial=_as_ascii_descriptor("receiver_serial", fields["receiver_serial"]),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        _as_int("station_id", self.station_id, 0, MAX_STATION_ID)
        _as_int("antenna_setup_id", self.antenna_setup_id, 0, 255)
        for name, val in (
            ("antenna_descriptor", self.antenna_descriptor),
            ("antenna_serial", self.antenna_serial),
            ("receiver_type", self.receiver_type),
            ("receiver_firmware", self.receiver_firmware),
            ("receiver_serial", self.receiver_serial),
        ):
            _as_ascii_descriptor(name, val)

    def encode(self) -> bytes:
        self.validate()
        b_desc = self.antenna_descriptor.encode("ascii")
        b_ant_sn = self.antenna_serial.encode("ascii")
        b_rec = self.receiver_type.encode("ascii")
        b_fw = self.receiver_firmware.encode("ascii")
        b_rec_sn = self.receiver_serial.encode("ascii")
        total_bytes = 9 + len(b_desc) + len(b_ant_sn) + len(b_rec) + len(b_fw) + len(b_rec_sn)
        writer = BitWriter(max_bits=total_bytes * 8)
        writer.write_unsigned(MESSAGE_NUMBER_1033, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(len(b_desc), 8)
        writer.write_bytes(b_desc)
        writer.write_unsigned(self.antenna_setup_id, 8)
        for blob in (b_ant_sn, b_rec, b_fw, b_rec_sn):
            writer.write_unsigned(len(blob), 8)
            writer.write_bytes(blob)
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class GlonassEphemeris1020:
    """RTCM 1020 GLONASS Broadcast Ephemeris (carries FCN resolving 1084 phase)."""

    satellite_id: int
    fcn: int
    tk_hour: int
    tk_minute: int
    tk_second_30s: int
    svh: int
    tb: int
    pos_m: tuple[float, float, float]
    vel_m_s: tuple[float, float, float]
    acc_m_s2: tuple[float, float, float]
    gamma_n: float
    tau_n: float
    dtau_n: float = 0.0
    age_days: int = 0
    nt: int = 1

    _REQUIRED_FIELDS = frozenset(
        {
            "satellite_id",
            "fcn",
            "tk_hour",
            "tk_minute",
            "tk_second_30s",
            "svh",
            "tb",
            "pos_m",
            "vel_m_s",
            "acc_m_s2",
            "gamma_n",
            "tau_n",
            "dtau_n",
            "age_days",
            "nt",
        }
    )

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1020")

        def _vec3(name: str, raw: object) -> tuple[float, float, float]:
            if not isinstance(raw, (list, tuple)) or len(raw) != 3:
                raise MessageInputError(f"{name}: 3-element numeric vector required")
            return (
                _as_float(f"{name}[0]", raw[0]),
                _as_float(f"{name}[1]", raw[1]),
                _as_float(f"{name}[2]", raw[2]),
            )

        msg = cls(
            satellite_id=_as_int(
                "satellite_id", fields["satellite_id"], 1, GLONASS_SATELLITE_ID_MAX
            ),
            fcn=_as_int("fcn", fields["fcn"], -7, 6),
            tk_hour=_as_int("tk_hour", fields["tk_hour"], 0, 23),
            tk_minute=_as_int("tk_minute", fields["tk_minute"], 0, 59),
            tk_second_30s=_as_int("tk_second_30s", fields["tk_second_30s"], 0, 1),
            svh=_as_int("svh", fields["svh"], 0, 1),
            tb=_as_int("tb", fields["tb"], 1, 96),
            pos_m=_vec3("pos_m", fields["pos_m"]),
            vel_m_s=_vec3("vel_m_s", fields["vel_m_s"]),
            acc_m_s2=_vec3("acc_m_s2", fields["acc_m_s2"]),
            gamma_n=_as_float("gamma_n", fields["gamma_n"]),
            tau_n=_as_float("tau_n", fields["tau_n"]),
            dtau_n=_as_float("dtau_n", fields["dtau_n"]),
            age_days=_as_int("age_days", fields["age_days"], 0, 31),
            nt=_as_int("nt", fields["nt"], 1, 1461),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        _as_int("satellite_id", self.satellite_id, 1, GLONASS_SATELLITE_ID_MAX)
        _as_int("fcn", self.fcn, -7, 6)
        _as_int("tk_hour", self.tk_hour, 0, 23)
        _as_int("tk_minute", self.tk_minute, 0, 59)
        _as_int("tk_second_30s", self.tk_second_30s, 0, 1)
        _as_int("svh", self.svh, 0, 1)
        _as_int("tb", self.tb, 1, 96)
        _as_int("age_days", self.age_days, 0, 31)
        _as_int("nt", self.nt, 1, 1461)
        for v in (
            *self.pos_m,
            *self.vel_m_s,
            *self.acc_m_s2,
            self.gamma_n,
            self.tau_n,
            self.dtau_n,
        ):
            _as_float("ephemeris_value", v)
        for idx, (p, v, a) in enumerate(zip(self.pos_m, self.vel_m_s, self.acc_m_s2, strict=True)):
            if abs(_round_half_up((p / 1000.0) / (2.0**-11))) > (1 << 26) - 1:
                raise MessageInputError(f"pos_m[{idx}] out of 27-bit sign-magnitude range")
            if abs(_round_half_up((v / 1000.0) / (2.0**-20))) > (1 << 23) - 1:
                raise MessageInputError(f"vel_m_s[{idx}] out of 24-bit sign-magnitude range")
            if abs(_round_half_up((a / 1000.0) / (2.0**-30))) > (1 << 4) - 1:
                raise MessageInputError(f"acc_m_s2[{idx}] out of 5-bit sign-magnitude range")
        if abs(_round_half_up(self.gamma_n / (2.0**-40))) > (1 << 10) - 1:
            raise MessageInputError("gamma_n out of 11-bit sign-magnitude range")
        if abs(_round_half_up(self.tau_n / (2.0**-30))) > (1 << 21) - 1:
            raise MessageInputError("tau_n out of 22-bit sign-magnitude range")
        if abs(_round_half_up(self.dtau_n / (2.0**-30))) > (1 << 4) - 1:
            raise MessageInputError("dtau_n out of 5-bit sign-magnitude range")

    def encode(self) -> bytes:
        self.validate()
        p2_11 = 2.0**-11
        p2_20 = 2.0**-20
        p2_30 = 2.0**-30
        p2_40 = 2.0**-40
        pos_q = [_round_half_up((v / 1000.0) / p2_11) for v in self.pos_m]
        vel_q = [_round_half_up((v / 1000.0) / p2_20) for v in self.vel_m_s]
        acc_q = [_round_half_up((v / 1000.0) / p2_30) for v in self.acc_m_s2]
        gam_q = _round_half_up(self.gamma_n / p2_40)
        tau_q = _round_half_up(self.tau_n / p2_30)
        dtau_q = _round_half_up(self.dtau_n / p2_30)

        writer = BitWriter(max_bits=360)
        writer.write_unsigned(MESSAGE_NUMBER_1020, 12)
        writer.write_unsigned(self.satellite_id, 6)
        writer.write_unsigned(self.fcn + 7, 5)
        writer.write_unsigned(0, 4)  # almanac health / P1
        writer.write_unsigned(self.tk_hour, 5)
        writer.write_unsigned(self.tk_minute, 6)
        writer.write_unsigned(self.tk_second_30s, 1)
        writer.write_unsigned(self.svh, 1)
        writer.write_unsigned(0, 1)  # P2
        writer.write_unsigned(self.tb, 7)
        for axis in range(3):
            writer.write_sign_magnitude(vel_q[axis], 24)
            writer.write_sign_magnitude(pos_q[axis], 27)
            writer.write_sign_magnitude(acc_q[axis], 5)
        writer.write_unsigned(0, 1)  # P3
        writer.write_sign_magnitude(gam_q, 11)
        writer.write_unsigned(0, 3)  # P, ln
        writer.write_sign_magnitude(tau_q, 22)
        writer.write_sign_magnitude(dtau_q, 5)
        writer.write_unsigned(self.age_days, 5)
        writer.write_unsigned(0, 1)  # P4
        writer.write_unsigned(0, 4)  # FT
        writer.write_unsigned(self.nt, 11)
        writer.write_unsigned(0, 2)  # M
        writer.write_unsigned(0, 1)  # additional data flag
        writer.write_unsigned(0, 11)  # NA
        writer.write_unsigned(0, 32)  # tau_c
        writer.write_unsigned(0, 5)  # N4
        writer.write_unsigned(0, 22)  # tau_gps
        writer.write_unsigned(0, 1)  # ln
        writer.write_unsigned(0, 7)  # reserved
        return writer.to_bytes()


@dataclass(frozen=True, slots=True)
class GlonassCodePhaseBias1230:
    """RTCM 1230 GLONASS L1 and L2 Code-Phase Biases (0.02 m resolution)."""

    station_id: int
    code_phase_bias_indicator: bool
    l1_ca_bias_m: float | None = None
    l1_p_bias_m: float | None = None
    l2_ca_bias_m: float | None = None
    l2_p_bias_m: float | None = None

    _REQUIRED_FIELDS = frozenset(
        {
            "station_id",
            "code_phase_bias_indicator",
            "l1_ca_bias_m",
            "l1_p_bias_m",
            "l2_ca_bias_m",
            "l2_p_bias_m",
        }
    )

    @classmethod
    def from_mapping(cls, fields: Mapping[str, object]) -> Self:
        _require_exact_keys(fields, cls._REQUIRED_FIELDS, "1230")

        def _opt_bias(name: str, val: object) -> float | None:
            return None if val is None else _as_float(name, val)

        msg = cls(
            station_id=_as_int("station_id", fields["station_id"], 0, MAX_STATION_ID),
            code_phase_bias_indicator=_as_bool(
                "code_phase_bias_indicator", fields["code_phase_bias_indicator"]
            ),
            l1_ca_bias_m=_opt_bias("l1_ca_bias_m", fields["l1_ca_bias_m"]),
            l1_p_bias_m=_opt_bias("l1_p_bias_m", fields["l1_p_bias_m"]),
            l2_ca_bias_m=_opt_bias("l2_ca_bias_m", fields["l2_ca_bias_m"]),
            l2_p_bias_m=_opt_bias("l2_p_bias_m", fields["l2_p_bias_m"]),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        _as_int("station_id", self.station_id, 0, MAX_STATION_ID)
        if not isinstance(self.code_phase_bias_indicator, bool):
            raise MessageInputError("code_phase_bias_indicator: a boolean is required")
        for name, val in (
            ("l1_ca_bias_m", self.l1_ca_bias_m),
            ("l1_p_bias_m", self.l1_p_bias_m),
            ("l2_ca_bias_m", self.l2_ca_bias_m),
            ("l2_p_bias_m", self.l2_p_bias_m),
        ):
            if val is not None:
                v = _as_float(name, val)
                if not -655.34 <= v <= 655.34:
                    raise MessageInputError(f"{name}: {v} m outside [-655.34, +655.34] m")

    def encode(self) -> bytes:
        self.validate()
        slots = (self.l1_ca_bias_m, self.l1_p_bias_m, self.l2_ca_bias_m, self.l2_p_bias_m)
        mask = 0
        present: list[int] = []
        for idx, val in enumerate(slots):
            if val is not None:
                mask |= 1 << (3 - idx)
                present.append(_round_half_up(val / 0.02))
        writer = BitWriter(max_bits=32 + 16 * len(present))
        writer.write_unsigned(MESSAGE_NUMBER_1230, 12)
        writer.write_unsigned(self.station_id, 12)
        writer.write_unsigned(int(self.code_phase_bias_indicator), 1)
        writer.write_unsigned(0, 3)  # reserved
        writer.write_unsigned(mask, 4)
        for q in present:
            writer.write_signed(q, 16)
        return writer.to_bytes()


def _signal_table(system: MsmSystem) -> dict[int, str]:
    if system == MsmSystem.GPS:
        return GPS_MSM_SIGNAL_IDS
    if system == MsmSystem.GALILEO:
        return GALILEO_MSM_SIGNAL_IDS
    return GLONASS_MSM_SIGNAL_IDS
