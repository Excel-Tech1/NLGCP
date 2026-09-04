"""Database repository for station metadata imports."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nlgcp_api.station_metadata.models import (
    ProviderMetadata,
    ResolvedMetadataSource,
    StationCoordinate,
    StationEquipment,
    StationImportPackage,
    StationMetadata,
)


class StationMetadataConflictError(RuntimeError):
    """Raised when an import would overwrite existing scientific metadata."""


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Summary of one transactional station metadata import."""

    provider_id: int
    station_id: int
    inserted_sources: int
    inserted_provider: bool
    inserted_station: bool
    inserted_coordinates: int
    inserted_equipment: int


class StationMetadataRepository:
    """Repository backed by a psycopg connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def import_package(
        self,
        package: StationImportPackage,
        resolved_sources: dict[str, ResolvedMetadataSource],
    ) -> ImportResult:
        """Import a validated package in one database transaction."""

        with self._connection.transaction():
            source_ids: dict[str, int] = {}
            inserted_sources = 0
            for source in package.sources:
                source_id, inserted = self._ensure_source(resolved_sources[source.key])
                source_ids[source.key] = source_id
                if inserted:
                    inserted_sources += 1

            provider_id, inserted_provider = self._ensure_provider(
                package.provider,
                source_ids[package.provider.source_key],
            )
            station_id, inserted_station = self._ensure_station(
                provider_id,
                package.station,
                source_ids[package.station.source_key],
            )
            inserted_coordinates = self._ensure_coordinates(
                station_id,
                package.coordinates,
                source_ids,
            )
            inserted_equipment = self._ensure_equipment(
                station_id,
                package.equipment,
                source_ids,
            )

        return ImportResult(
            provider_id=provider_id,
            station_id=station_id,
            inserted_sources=inserted_sources,
            inserted_provider=inserted_provider,
            inserted_station=inserted_station,
            inserted_coordinates=inserted_coordinates,
            inserted_equipment=inserted_equipment,
        )

    def _ensure_source(self, resolved: ResolvedMetadataSource) -> tuple[int, bool]:
        source = resolved.source
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT metadata_source_id, sha256
                FROM metadata_sources
                WHERE source_type = %s
                  AND source_reference = %s
                  AND source_path = %s
                """,
                (source.source_type, source.source_reference, str(source.path)),
            )
            row = cursor.fetchone()
            if row is not None:
                source_id = int(row[0])
                existing_sha = row[1]
                if existing_sha != resolved.sha256:
                    raise StationMetadataConflictError(
                        f"metadata source {source.path} has conflicting checksum"
                    )
                return source_id, False

            cursor.execute(
                """
                INSERT INTO metadata_sources (
                    source_type,
                    source_reference,
                    source_path,
                    source_date,
                    sha256,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING metadata_source_id
                """,
                (
                    source.source_type,
                    source.source_reference,
                    str(source.path),
                    source.source_date,
                    resolved.sha256,
                    source.notes,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("metadata source insert did not return an id")
            return int(inserted[0]), True

    def _ensure_provider(
        self,
        provider: ProviderMetadata,
        metadata_source_id: int,
    ) -> tuple[int, bool]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    provider_id,
                    provider_name,
                    operator_name,
                    country,
                    notes,
                    metadata_source_id
                FROM providers
                WHERE provider_code = %s
                """,
                (provider.provider_code,),
            )
            row = cursor.fetchone()
            if row is not None:
                provider_id = int(row[0])
                existing = row[1:]
                expected = (
                    provider.provider_name,
                    provider.operator_name,
                    provider.country,
                    provider.notes,
                    metadata_source_id,
                )
                if existing != expected:
                    raise StationMetadataConflictError(
                        f"provider {provider.provider_code} conflicts with registry"
                    )
                return provider_id, False

            cursor.execute(
                """
                INSERT INTO providers (
                    provider_code,
                    provider_name,
                    operator_name,
                    country,
                    notes,
                    metadata_source_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING provider_id
                """,
                (
                    provider.provider_code,
                    provider.provider_name,
                    provider.operator_name,
                    provider.country,
                    provider.notes,
                    metadata_source_id,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("provider insert did not return an id")
            return int(inserted[0]), True

    def _ensure_station(
        self,
        provider_id: int,
        station: StationMetadata,
        metadata_source_id: int,
    ) -> tuple[int, bool]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    station_id,
                    station_name,
                    network,
                    operator_name,
                    country,
                    status,
                    first_observation,
                    last_observation,
                    metadata_source_id,
                    notes
                FROM stations
                WHERE provider_id = %s AND station_code = %s
                """,
                (provider_id, station.station_code),
            )
            row = cursor.fetchone()
            if row is not None:
                station_id = int(row[0])
                existing = row[1:]
                expected = (
                    station.station_name,
                    station.network,
                    station.operator_name,
                    station.country,
                    station.status,
                    station.first_observation,
                    station.last_observation,
                    metadata_source_id,
                    station.notes,
                )
                if existing != expected:
                    raise StationMetadataConflictError(
                        f"station {station.station_code} conflicts with registry"
                    )
                return station_id, False

            cursor.execute(
                """
                INSERT INTO stations (
                    provider_id,
                    station_code,
                    station_name,
                    network,
                    operator_name,
                    country,
                    status,
                    first_observation,
                    last_observation,
                    metadata_source_id,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING station_id
                """,
                (
                    provider_id,
                    station.station_code,
                    station.station_name,
                    station.network,
                    station.operator_name,
                    station.country,
                    station.status,
                    station.first_observation,
                    station.last_observation,
                    metadata_source_id,
                    station.notes,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("station insert did not return an id")
            return int(inserted[0]), True

    def _ensure_coordinates(
        self,
        station_id: int,
        coordinates: tuple[StationCoordinate, ...],
        source_ids: dict[str, int],
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    latitude_deg,
                    longitude_deg,
                    ellipsoidal_height_m,
                    ecef_x_m,
                    ecef_y_m,
                    ecef_z_m,
                    reference_frame,
                    coordinate_epoch,
                    solution_method,
                    valid_from,
                    valid_to,
                    metadata_source_id,
                    notes
                FROM station_coordinates
                WHERE station_id = %s
                ORDER BY valid_from, valid_to NULLS LAST
                """,
                (station_id,),
            )
            existing = tuple(cursor.fetchall())
            expected = tuple(
                coordinate_record_tuple(coordinate, source_ids[coordinate.source_key])
                for coordinate in coordinates
            )
            if existing:
                if _normalise_rows(existing) != _normalise_rows(expected):
                    raise StationMetadataConflictError(
                        f"coordinates for station_id {station_id} conflict with registry"
                    )
                return 0

            for coordinate in coordinates:
                cursor.execute(
                    """
                    INSERT INTO station_coordinates (
                        station_id,
                        latitude_deg,
                        longitude_deg,
                        ellipsoidal_height_m,
                        ecef_x_m,
                        ecef_y_m,
                        ecef_z_m,
                        reference_frame,
                        coordinate_epoch,
                        solution_method,
                        valid_from,
                        valid_to,
                        metadata_source_id,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        station_id,
                        *coordinate_record_tuple(
                            coordinate,
                            source_ids[coordinate.source_key],
                        ),
                    ),
                )
            return len(coordinates)

    def _ensure_equipment(
        self,
        station_id: int,
        equipment: tuple[StationEquipment, ...],
        source_ids: dict[str, int],
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    receiver_model,
                    receiver_serial,
                    receiver_firmware,
                    antenna_model,
                    antenna_serial,
                    radome,
                    antenna_height_m,
                    antenna_height_reference,
                    valid_from,
                    valid_to,
                    metadata_source_id,
                    notes
                FROM station_equipment
                WHERE station_id = %s
                ORDER BY valid_from, valid_to NULLS LAST
                """,
                (station_id,),
            )
            existing = tuple(cursor.fetchall())
            expected = tuple(
                equipment_record_tuple(row, source_ids[row.source_key])
                for row in equipment
            )
            if existing:
                if _normalise_rows(existing) != _normalise_rows(expected):
                    raise StationMetadataConflictError(
                        f"equipment for station_id {station_id} conflicts with registry"
                    )
                return 0

            for row in equipment:
                cursor.execute(
                    """
                    INSERT INTO station_equipment (
                        station_id,
                        receiver_model,
                        receiver_serial,
                        receiver_firmware,
                        antenna_model,
                        antenna_serial,
                        radome,
                        antenna_height_m,
                        antenna_height_reference,
                        valid_from,
                        valid_to,
                        metadata_source_id,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        station_id,
                        *equipment_record_tuple(row, source_ids[row.source_key]),
                    ),
                )
            return len(equipment)


def coordinate_record_tuple(
    coordinate: StationCoordinate,
    metadata_source_id: int,
) -> tuple[object, ...]:
    """Return a comparable/persistable coordinate tuple."""

    return (
        coordinate.latitude_deg,
        coordinate.longitude_deg,
        coordinate.ellipsoidal_height_m,
        coordinate.ecef_x_m,
        coordinate.ecef_y_m,
        coordinate.ecef_z_m,
        coordinate.reference_frame,
        coordinate.coordinate_epoch,
        coordinate.solution_method,
        coordinate.valid_from,
        coordinate.valid_to,
        metadata_source_id,
        coordinate.notes,
    )


def equipment_record_tuple(
    equipment: StationEquipment,
    metadata_source_id: int,
) -> tuple[object, ...]:
    """Return a comparable/persistable equipment tuple."""

    return (
        equipment.receiver_model,
        equipment.receiver_serial,
        equipment.receiver_firmware,
        equipment.antenna_model,
        equipment.antenna_serial,
        equipment.radome,
        equipment.antenna_height_m,
        equipment.antenna_height_reference,
        equipment.valid_from,
        equipment.valid_to,
        metadata_source_id,
        equipment.notes,
    )


def _normalise_rows(rows: tuple[tuple[object, ...], ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(tuple(_normalise_value(value) for value in row) for row in rows)


def _normalise_value(value: object) -> object:
    if isinstance(value, Decimal):
        return value.normalize()
    return value
