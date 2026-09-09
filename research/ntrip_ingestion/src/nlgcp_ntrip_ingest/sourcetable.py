"""NTRIP source-table retrieval and parsing (safe, bounded).

Only ``STR``/``CAS``/``NET``/``ENDSOURCETABLE`` records are parsed.
Coordinates are provider metadata, never scientifically verified
station coordinates.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class StrEntry:
    mountpoint: str
    identifier: str
    format: str
    format_details: str
    carrier: str
    nav_systems: str
    network: str
    country: str
    latitude: str
    longitude: str
    nmea_required: str
    solution: str
    generator: str
    compr_encryp: str
    authentication: str
    fee: str
    bitrate: str
    misc: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CasEntry:
    host: str
    port: str
    identifier: str
    operator: str = ""
    nmea: str = ""
    country: str = ""
    latitude: str = ""
    longitude: str = ""
    misc: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NetEntry:
    identifier: str
    operator: str = ""
    authentication: str = ""
    fee: str = ""
    web_net: str = ""
    web_str: str = ""
    web_reg: str = ""
    misc: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SourceTable:
    streams: list[StrEntry]
    casters: list[CasEntry]
    networks: list[NetEntry]
    terminated: bool
    findings: list[str]
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "streams": [s.as_dict() for s in self.streams],
            "casters": [c.as_dict() for c in self.casters],
            "networks": [n.as_dict() for n in self.networks],
            "terminated": self.terminated,
            "findings": list(self.findings),
            "sha256": self.sha256,
        }


def _split_fields(line: str) -> list[str]:
    return line.split(";")[1:]


def parse_sourcetable(
    text: str, *, max_bytes: int = 65536, max_entries: int = 10000
) -> SourceTable:
    """Parse a source-table body with explicit size/entry bounds."""
    findings: list[str] = []
    raw = text.encode("utf-8", errors="replace")
    if len(raw) > max_bytes:
        findings.append(
            f"SOURCETABLE_TOO_LARGE bytes={len(raw)} max={max_bytes}"
        )
        raw = raw[:max_bytes]
        text = raw.decode("utf-8", errors="replace")
    table = SourceTable(
        streams=[],
        casters=[],
        networks=[],
        terminated=False,
        findings=findings,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    total = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "ENDSOURCETABLE":
            table.terminated = True
            continue
        total += 1
        if total > max_entries:
            table.findings.append(f"ENTRY_LIMIT reached={max_entries}")
            break
        if line.startswith("STR;"):
            fields = _split_fields(line) + [""] * 18
            table.streams.append(
                StrEntry(
                    mountpoint=fields[0],
                    identifier=fields[1],
                    format=fields[2],
                    format_details=fields[3],
                    carrier=fields[4],
                    nav_systems=fields[5],
                    network=fields[6],
                    country=fields[7],
                    latitude=fields[8],
                    longitude=fields[9],
                    nmea_required=fields[10],
                    solution=fields[11],
                    generator=fields[12],
                    compr_encryp=fields[13],
                    authentication=fields[14],
                    fee=fields[15],
                    bitrate=fields[16],
                    misc=fields[17],
                )
            )
        elif line.startswith("CAS;"):
            fields = _split_fields(line) + [""] * 8
            table.casters.append(
                CasEntry(
                    host=fields[0],
                    port=fields[1],
                    identifier=fields[2],
                    operator=fields[3],
                    nmea=fields[4],
                    country=fields[5],
                    latitude=fields[6],
                    longitude=fields[7],
                    misc=fields[8],
                )
            )
        elif line.startswith("NET;"):
            fields = _split_fields(line) + [""] * 7
            table.networks.append(
                NetEntry(
                    identifier=fields[0],
                    operator=fields[1],
                    authentication=fields[2],
                    fee=fields[3],
                    web_net=fields[4],
                    web_str=fields[5],
                    web_reg=fields[6],
                    misc=fields[7],
                )
            )
        else:
            table.findings.append(f"UNKNOWN_RECORD prefix={line[:8]!r}")
    if not table.terminated:
        table.findings.append("MISSING_ENDSOURCETABLE")
    return table


def find_stream(table: SourceTable, mountpoint: str) -> StrEntry | None:
    want = mountpoint.lstrip("/").upper()
    for entry in table.streams:
        if entry.mountpoint.lstrip("/").upper() == want:
            return entry
    return None


def stream_requires_nmea(entry: StrEntry) -> bool:
    return entry.nmea_required.strip() == "1"


def stream_needs_auth(entry: StrEntry) -> bool:
    return entry.authentication.strip().upper() in ("B", "D", "Y", "1")
