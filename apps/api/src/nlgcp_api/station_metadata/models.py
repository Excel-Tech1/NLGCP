"""Typed station metadata import records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class MetadataSource:
    """A provenance document referenced by an import package."""

    key: str
    source_type: str
    path: PurePosixPath
    source_reference: str
    source_date: date | None
    expected_sha256: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class ResolvedMetadataSource:
    """A source file resolved under NLGCP_DATA_ROOT."""

    source: MetadataSource
    sha256: str


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Provider metadata from a canonical import package."""

    provider_code: str
    provider_name: str
    operator_name: str | None
    country: str | None
    source_key: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class StationMetadata:
    """Station identity and observation span metadata."""

    station_code: str
    station_name: str | None
    network: str | None
    operator_name: str | None
    country: str | None
    status: str
    first_observation: datetime | None
    last_observation: datetime | None
    source_key: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class StationCoordinate:
    """Effective-dated station coordinates."""

    latitude_deg: Decimal | None
    longitude_deg: Decimal | None
    ellipsoidal_height_m: Decimal | None
    ecef_x_m: Decimal | None
    ecef_y_m: Decimal | None
    ecef_z_m: Decimal | None
    reference_frame: str
    coordinate_epoch: Decimal
    solution_method: str | None
    valid_from: datetime
    valid_to: datetime | None
    source_key: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class StationEquipment:
    """Effective-dated station equipment metadata."""

    receiver_model: str | None
    receiver_serial: str | None
    receiver_firmware: str | None
    antenna_model: str | None
    antenna_serial: str | None
    radome: str | None
    antenna_height_m: Decimal | None
    antenna_height_reference: str | None
    valid_from: datetime
    valid_to: datetime | None
    source_key: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class StationImportPackage:
    """A validated station metadata import package."""

    schema_version: str
    sources: tuple[MetadataSource, ...]
    provider: ProviderMetadata
    station: StationMetadata
    coordinates: tuple[StationCoordinate, ...]
    equipment: tuple[StationEquipment, ...]

    @property
    def source_by_key(self) -> dict[str, MetadataSource]:
        """Return sources keyed by package-local source key."""

        return {source.key: source for source in self.sources}
