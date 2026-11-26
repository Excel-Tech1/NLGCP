"""Mountpoint registry and NTRIP source-table formatting for Phase 12.

Every Phase 12 lab mountpoint is strictly synthetic-only and explicitly
labelled so it can never be mistaken for an operational GNSS correction stream.
"""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_rtcm_generation.models import OutputClassification

from nlgcp_correction_service import (
    DEFAULT_MOUNTPOINT,
    EXPERIMENTAL_VRS_MOUNTPOINT,
    EXPERIMENTAL_VRS_MOUNTPOINT_LABEL,
    LOOPBACK_HOST,
    SYNTHETIC_MOUNTPOINT_LABEL,
)


class MountpointError(ValueError):
    """Raised when a mountpoint definition or registration violates policy."""


@dataclass(frozen=True, slots=True)
class MountpointDefinition:
    """Declarative metadata for one local NTRIP mountpoint."""

    name: str = DEFAULT_MOUNTPOINT
    identifier: str = "NLGCP_SYNTHETIC_LAB"
    format_name: str = "RTCM 3.2"
    format_details: str = "1005(1),1074(1),1084(1)"
    carrier: int = 2
    nav_system: str = "GPS+GLO"
    network: str = "NLGCP-LAB"
    country: str = "NGA"
    latitude: float = 0.0
    longitude: float = 0.0
    nmea_required: bool = False
    solution_type: int = 0
    generator: str = "NLGCP-Phase11-Synthetic"
    compression: str = "none"
    authentication: str = "B"
    fee_required: bool = False
    bitrate: int = 9600
    synthetic_only: bool = True
    experimental_vrs_only: bool = False
    label: str = SYNTHETIC_MOUNTPOINT_LABEL

    def validate(self) -> None:
        if not self.name or "/" in self.name or ";" in self.name or " " in self.name:
            raise MountpointError(f"invalid mountpoint name: {self.name!r}")
        if self.synthetic_only and self.experimental_vrs_only:
            raise MountpointError(
                "mountpoint cannot be both synthetic_only and experimental_vrs_only"
            )
        if not self.synthetic_only and not self.experimental_vrs_only:
            raise MountpointError(
                "non-synthetic / operational mountpoints are forbidden in Phase 12 lab mode"
            )
        if self.synthetic_only and "SYNTHETIC" not in self.label.upper():
            raise MountpointError("synthetic mountpoint label must explicitly state SYNTHETIC")
        if self.experimental_vrs_only:
            upper = self.label.upper()
            if "EXPERIMENTAL" not in upper or "NOT OPERATIONAL" not in upper:
                raise MountpointError(
                    "experimental VRS mountpoint label must explicitly state "
                    "EXPERIMENTAL and NOT OPERATIONAL"
                )

    def accepts_classification(self, classification: OutputClassification | str) -> bool:
        value = str(classification)
        if value == str(OutputClassification.OPERATIONAL_APPROVED):
            return False
        if self.synthetic_only:
            return value == str(OutputClassification.SYNTHETIC_TEST_ONLY)
        if self.experimental_vrs_only:
            return value == str(OutputClassification.RESEARCH_VALIDATION)
        return False

    def sourcetable_str_line(self) -> str:
        """Render one NTRIP STR record explicitly carrying the synthetic label."""
        nmea = 1 if self.nmea_required else 0
        fee = "Y" if self.fee_required else "N"
        misc = self.label.replace(";", ",")
        return (
            f"STR;{self.name};{self.identifier};{self.format_name};"
            f"{self.format_details};{self.carrier};{self.nav_system};"
            f"{self.network};{self.country};{self.latitude:.2f};{self.longitude:.2f};"
            f"{nmea};{self.solution_type};{self.generator};{self.compression};"
            f"{self.authentication};{fee};{self.bitrate};{misc}"
        )


class MountpointRegistry:
    """Fail-closed registry of local synthetic mountpoints."""

    def __init__(self, mountpoints: tuple[MountpointDefinition, ...] | None = None) -> None:
        items = mountpoints if mountpoints is not None else (MountpointDefinition(),)
        self._mountpoints: dict[str, MountpointDefinition] = {}
        for item in items:
            item.validate()
            key = item.name
            if key in self._mountpoints:
                raise MountpointError(f"duplicate mountpoint: {key}")
            self._mountpoints[key] = item

    def get(self, name: str) -> MountpointDefinition | None:
        cleaned = name.lstrip("/")
        return self._mountpoints.get(cleaned)

    def names(self) -> tuple[str, ...]:
        return tuple(self._mountpoints.keys())

    def render_sourcetable(self, *, port: int) -> str:
        """Render a complete NTRIP source table with explicit synthetic warnings."""
        lines = [
            f"CAS;{LOOPBACK_HOST};{port};NLGCP-LAB-CASTER;NLGCP-Research;0;NGA;"
            f"0.00;0.00;LOCALHOST_ONLY_SYNTHETIC_LAB",
            "NET;NLGCP-LAB;NLGCP-Research;B;N;none;none;;SYNTHETIC_TEST_ONLY",
        ]
        for mp in self._mountpoints.values():
            lines.append(mp.sourcetable_str_line())
        lines.append("ENDSOURCETABLE")
        return "\r\n".join(lines) + "\r\n"


def experimental_vrs_mountpoint(
    name: str = EXPERIMENTAL_VRS_MOUNTPOINT,
    *,
    latitude: float = 0.0,
    longitude: float = 0.0,
    format_details: str = "1005(1),1074(1)",
    label: str = EXPERIMENTAL_VRS_MOUNTPOINT_LABEL,
) -> MountpointDefinition:
    """Create an isolated research-only mountpoint for experimental VRS streams."""
    mp = MountpointDefinition(
        name=name,
        identifier="NLGCP_VRS_RESEARCH",
        format_details=format_details,
        nav_system="GPS",
        network="NLGCP-RESEARCH",
        latitude=latitude,
        longitude=longitude,
        generator="NLGCP-Phase7-Experimental-VRS",
        synthetic_only=False,
        experimental_vrs_only=True,
        label=label,
    )
    mp.validate()
    return mp
