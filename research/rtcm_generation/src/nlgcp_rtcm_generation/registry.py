"""Message-family registry with honest support statuses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MessageFamilyStatus(StrEnum):
    DECLARED = "DECLARED"
    SCAFFOLDED = "SCAFFOLDED"
    SYNTHETICALLY_VALIDATED = "SYNTHETICALLY_VALIDATED"
    REAL_INPUT_VALIDATED = "REAL_INPUT_VALIDATED"
    OPERATIONALLY_APPROVED = "OPERATIONALLY_APPROVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class MessageFamily:
    family_id: str
    message_numbers: tuple[int, ...]
    description: str
    status: MessageFamilyStatus
    definition_provenance: str
    encoder_key: str | None = None


class MessageFamilyRegistry:
    """Registry is not a claim of support; status must be checked."""

    def __init__(self, families: tuple[MessageFamily, ...] | None = None) -> None:
        self._families = {
            family.family_id: family
            for family in (families or DEFAULT_MESSAGE_FAMILIES)
        }

    def get(self, family_id: str) -> MessageFamily | None:
        return self._families.get(family_id)

    def require(self, family_id: str) -> MessageFamily:
        family = self.get(family_id)
        if family is None:
            raise KeyError(f"unsupported message family: {family_id}")
        return family

    def as_dict(self) -> list[dict[str, object]]:
        return [
            {
                "family_id": family.family_id,
                "message_numbers": list(family.message_numbers),
                "description": family.description,
                "status": str(family.status),
                "definition_provenance": family.definition_provenance,
                "encoder_key": family.encoder_key,
            }
            for family in self._families.values()
        ]


DEFAULT_MESSAGE_FAMILIES = (
    MessageFamily(
        "REFERENCE_STATION_1005",
        (1005,),
        "Reference-station ECEF metadata scaffold; semantic layout not implemented.",
        MessageFamilyStatus.SCAFFOLDED,
        "RTKLIB/IGS references recorded in the technical baseline; licensed RTCM text not copied.",
    ),
    MessageFamily(
        "MSM4_GPS_1074",
        (1074,),
        "GPS MSM4 observation-generation boundary; authentic observation semantics required.",
        MessageFamilyStatus.SCAFFOLDED,
        "RTCM/RTKLIB compatibility boundary only; no production encoder in this sprint.",
    ),
    MessageFamily(
        "MSM4_GLONASS_1084",
        (1084,),
        "GLONASS MSM4 observation-generation boundary; authentic observation semantics required.",
        MessageFamilyStatus.SCAFFOLDED,
        "RTCM/RTKLIB compatibility boundary only; no production encoder in this sprint.",
    ),
    MessageFamily(
        "SYNTHETIC_TEST_FRAME",
        (4095,),
        "NLGCP lab-only deterministic test payload; not a navigable RTCM message.",
        MessageFamilyStatus.SYNTHETICALLY_VALIDATED,
        "NLGCP reference implementation; SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.",
        encoder_key="synthetic-test",
    ),
)
