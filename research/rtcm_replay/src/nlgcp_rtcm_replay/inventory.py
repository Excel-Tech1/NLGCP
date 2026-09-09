"""Frame inventory (§8): observed message types only, never claimed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from nlgcp_rtcm_replay.framing import ParseResult
from nlgcp_rtcm_replay.models import CRCStatus


@dataclass(slots=True)
class Inventory:
    frames_valid: int
    frames_invalid: int
    crc_failures: int
    message_type_counts: dict[str, int] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    inventory_fingerprint: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "frames_valid": self.frames_valid,
            "frames_invalid": self.frames_invalid,
            "crc_failures": self.crc_failures,
            "message_type_counts": dict(self.message_type_counts),
            "findings": list(self.findings),
            "inventory_fingerprint": self.inventory_fingerprint,
        }


def build_inventory(result: ParseResult, *, parser_version: str) -> Inventory:
    """Summarise actually observed frames; unobserved types stay absent."""
    counts: dict[str, int] = {}
    valid = 0
    invalid = 0
    crc_failures = 0
    for parsed in result.frames:
        record = parsed.record
        if record.crc_status == CRCStatus.PASS:
            valid += 1
            key = str(record.message_number) if record.message_number is not None else "UNKNOWN"
            counts[key] = counts.get(key, 0) + 1
        else:
            invalid += 1
            crc_failures += 1
    fingerprint = hashlib.sha256(
        "|".join(
            [parser_version]
            + sorted(f"{p.record.offset}:{p.record.raw_hash}" for p in result.frames)
        ).encode()
    ).hexdigest()
    return Inventory(
        frames_valid=valid,
        frames_invalid=invalid,
        crc_failures=crc_failures,
        message_type_counts=counts,
        findings=list(result.findings),
        inventory_fingerprint=fingerprint,
    )
