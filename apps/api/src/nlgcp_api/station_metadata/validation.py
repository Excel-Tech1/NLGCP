"""Validation for provenance-controlled station metadata imports."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath

from nlgcp_api.station_metadata.models import (
    MetadataSource,
    ProviderMetadata,
    StationCoordinate,
    StationEquipment,
    StationImportPackage,
    StationMetadata,
)

SUPPORTED_SCHEMA_VERSION = "1.0"
SHA256_LENGTH = 64


class StationMetadataValidationError(ValueError):
    """Raised when an import package violates the canonical contract."""


def load_station_import_package(path: Path) -> StationImportPackage:
    """Load and validate a UTF-8 JSON station metadata package."""

    try:
        with path.open("r", encoding="utf-8") as package_file:
            payload = json.load(package_file)
    except json.JSONDecodeError as exc:
        raise StationMetadataValidationError(
            f"invalid JSON at line {exc.lineno}: {exc.msg}"
        ) from exc

    return validate_station_import_payload(payload)


def validate_station_import_payload(payload: object) -> StationImportPackage:
    """Validate a decoded JSON payload."""

    root = _object(payload, "$")
    schema_version = _required_str(root, "schema_version", "$")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise StationMetadataValidationError(
            f"unsupported schema_version {schema_version!r}"
        )

    sources = tuple(
        _parse_source(item, f"$.sources[{index}]")
        for index, item in enumerate(_required_list(root, "sources", "$"))
    )
    if not sources:
        raise StationMetadataValidationError("$.sources must not be empty")

    source_keys: set[str] = set()
    for source in sources:
        if source.key in source_keys:
            raise StationMetadataValidationError(
                f"duplicate source key {source.key!r}"
            )
        source_keys.add(source.key)

    provider = _parse_provider(_required_object(root, "provider", "$"))
    station = _parse_station(_required_object(root, "station", "$"))

    _require_source_key(provider.source_key, source_keys, "$.provider.source_key")
    _require_source_key(station.source_key, source_keys, "$.station.source_key")

    coordinates = tuple(
        _parse_coordinate(item, f"$.coordinates[{index}]", source_keys)
        for index, item in enumerate(_required_list(root, "coordinates", "$"))
    )
    equipment = tuple(
        _parse_equipment(item, f"$.equipment[{index}]", source_keys)
        for index, item in enumerate(_required_list(root, "equipment", "$"))
    )

    _reject_overlapping_intervals(
        ((row.valid_from, row.valid_to) for row in coordinates),
        "$.coordinates",
    )
    _reject_overlapping_intervals(
        ((row.valid_from, row.valid_to) for row in equipment),
        "$.equipment",
    )

    return StationImportPackage(
        schema_version=schema_version,
        sources=sources,
        provider=provider,
        station=station,
        coordinates=coordinates,
        equipment=equipment,
    )


def _parse_source(payload: object, path: str) -> MetadataSource:
    item = _object(payload, path)
    source_path = _required_str(item, "path", path)
    parsed_path = PurePosixPath(source_path)
    if parsed_path.is_absolute() or ".." in parsed_path.parts:
        raise StationMetadataValidationError(
            f"{path}.path must be relative to NLGCP_DATA_ROOT and not traverse"
        )
    return MetadataSource(
        key=_required_str(item, "key", path),
        source_type=_required_str(item, "source_type", path),
        path=parsed_path,
        source_reference=_required_str(item, "source_reference", path),
        source_date=_optional_date(item, "source_date", path),
        expected_sha256=_optional_sha256(item, "expected_sha256", path),
        notes=_optional_str(item, "notes", path),
    )


def _parse_provider(item: Mapping[str, object]) -> ProviderMetadata:
    path = "$.provider"
    return ProviderMetadata(
        provider_code=_required_str(item, "provider_code", path),
        provider_name=_required_str(item, "provider_name", path),
        operator_name=_optional_str(item, "operator_name", path),
        country=_optional_str(item, "country", path),
        source_key=_required_str(item, "source_key", path),
        notes=_optional_str(item, "notes", path),
    )


def _parse_station(item: Mapping[str, object]) -> StationMetadata:
    path = "$.station"
    first_observation = _optional_datetime(item, "first_observation", path)
    last_observation = _optional_datetime(item, "last_observation", path)
    if (
        first_observation is not None
        and last_observation is not None
        and last_observation < first_observation
    ):
        raise StationMetadataValidationError(
            "$.station.last_observation must be >= first_observation"
        )
    return StationMetadata(
        station_code=_required_str(item, "station_code", path),
        station_name=_optional_str(item, "station_name", path),
        network=_optional_str(item, "network", path),
        operator_name=_optional_str(item, "operator_name", path),
        country=_optional_str(item, "country", path),
        status=_required_str(item, "status", path),
        first_observation=first_observation,
        last_observation=last_observation,
        source_key=_required_str(item, "source_key", path),
        notes=_optional_str(item, "notes", path),
    )


def _parse_coordinate(
    payload: object,
    path: str,
    source_keys: set[str],
) -> StationCoordinate:
    item = _object(payload, path)
    source_key = _required_str(item, "source_key", path)
    _require_source_key(source_key, source_keys, f"{path}.source_key")
    latitude = _optional_decimal(item, "latitude_deg", path)
    longitude = _optional_decimal(item, "longitude_deg", path)
    ecef_x = _optional_decimal(item, "ecef_x_m", path)
    ecef_y = _optional_decimal(item, "ecef_y_m", path)
    ecef_z = _optional_decimal(item, "ecef_z_m", path)
    geodetic_values = (latitude, longitude)
    ecef_values = (ecef_x, ecef_y, ecef_z)
    if any(value is None for value in geodetic_values) and any(
        value is not None for value in geodetic_values
    ):
        raise StationMetadataValidationError(
            f"{path} must not contain a partial latitude/longitude pair"
        )
    if any(value is None for value in ecef_values) and any(
        value is not None for value in ecef_values
    ):
        raise StationMetadataValidationError(
            f"{path} must not contain a partial ECEF triplet"
        )
    if latitude is None and ecef_x is None:
        raise StationMetadataValidationError(
            f"{path} must contain a geodetic pair or ECEF triplet"
        )
    if latitude is not None and not Decimal("-90") <= latitude <= Decimal("90"):
        raise StationMetadataValidationError(f"{path}.latitude_deg is out of range")
    if longitude is not None and not Decimal("-180") <= longitude <= Decimal("180"):
        raise StationMetadataValidationError(f"{path}.longitude_deg is out of range")

    valid_from = _required_datetime(item, "valid_from", path)
    valid_to = _optional_datetime(item, "valid_to", path)
    if valid_to is not None and valid_to <= valid_from:
        raise StationMetadataValidationError(f"{path}.valid_to must be > valid_from")

    return StationCoordinate(
        latitude_deg=latitude,
        longitude_deg=longitude,
        ellipsoidal_height_m=_optional_decimal(item, "ellipsoidal_height_m", path),
        ecef_x_m=ecef_x,
        ecef_y_m=ecef_y,
        ecef_z_m=ecef_z,
        reference_frame=_required_str(item, "reference_frame", path),
        coordinate_epoch=_required_decimal(item, "coordinate_epoch", path),
        solution_method=_optional_str(item, "solution_method", path),
        valid_from=valid_from,
        valid_to=valid_to,
        source_key=source_key,
        notes=_optional_str(item, "notes", path),
    )


def _parse_equipment(
    payload: object,
    path: str,
    source_keys: set[str],
) -> StationEquipment:
    item = _object(payload, path)
    source_key = _required_str(item, "source_key", path)
    _require_source_key(source_key, source_keys, f"{path}.source_key")
    meaningful_fields = (
        "receiver_model",
        "receiver_serial",
        "receiver_firmware",
        "antenna_model",
        "antenna_serial",
        "radome",
        "antenna_height_m",
        "antenna_height_reference",
    )
    if not any(item.get(field_name) is not None for field_name in meaningful_fields):
        raise StationMetadataValidationError(
            f"{path} must contain at least one receiver or antenna field"
        )
    antenna_height = _optional_decimal(item, "antenna_height_m", path)
    if antenna_height is not None and antenna_height < Decimal("0"):
        raise StationMetadataValidationError(
            f"{path}.antenna_height_m must be non-negative"
        )
    valid_from = _required_datetime(item, "valid_from", path)
    valid_to = _optional_datetime(item, "valid_to", path)
    if valid_to is not None and valid_to <= valid_from:
        raise StationMetadataValidationError(f"{path}.valid_to must be > valid_from")

    return StationEquipment(
        receiver_model=_optional_str(item, "receiver_model", path),
        receiver_serial=_optional_str(item, "receiver_serial", path),
        receiver_firmware=_optional_str(item, "receiver_firmware", path),
        antenna_model=_optional_str(item, "antenna_model", path),
        antenna_serial=_optional_str(item, "antenna_serial", path),
        radome=_optional_str(item, "radome", path),
        antenna_height_m=antenna_height,
        antenna_height_reference=_optional_str(
            item,
            "antenna_height_reference",
            path,
        ),
        valid_from=valid_from,
        valid_to=valid_to,
        source_key=source_key,
        notes=_optional_str(item, "notes", path),
    )


def _reject_overlapping_intervals(
    intervals: Iterable[tuple[datetime, datetime | None]],
    path: str,
) -> None:
    ordered = sorted(intervals, key=lambda interval: interval[0])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        previous_end = previous[1]
        if previous_end is None or current[0] < previous_end:
            raise StationMetadataValidationError(
                f"{path} contains overlapping validity intervals"
            )


def _require_source_key(source_key: str, source_keys: set[str], path: str) -> None:
    if source_key not in source_keys:
        raise StationMetadataValidationError(
            f"{path} references unknown source key {source_key!r}"
        )


def _object(payload: object, path: str) -> Mapping[str, object]:
    if not isinstance(payload, dict):
        raise StationMetadataValidationError(f"{path} must be an object")
    return payload


def _required_object(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> Mapping[str, object]:
    return _object(_required(item, key, path), f"{path}.{key}")


def _required_list(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> list[object]:
    value = _required(item, key, path)
    if not isinstance(value, list):
        raise StationMetadataValidationError(f"{path}.{key} must be an array")
    return value


def _required(item: Mapping[str, object], key: str, path: str) -> object:
    if key not in item:
        raise StationMetadataValidationError(f"{path}.{key} is required")
    return item[key]


def _required_str(item: Mapping[str, object], key: str, path: str) -> str:
    value = _required(item, key, path)
    if not isinstance(value, str) or value.strip() == "":
        raise StationMetadataValidationError(f"{path}.{key} must be a non-empty string")
    return value


def _optional_str(item: Mapping[str, object], key: str, path: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise StationMetadataValidationError(f"{path}.{key} must be a string or null")
    return value


def _required_decimal(item: Mapping[str, object], key: str, path: str) -> Decimal:
    value = _required(item, key, path)
    parsed = _parse_decimal(value)
    if parsed is None:
        raise StationMetadataValidationError(f"{path}.{key} must not be null")
    return parsed


def _optional_decimal(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> Decimal | None:
    try:
        return _parse_decimal(item.get(key))
    except StationMetadataValidationError as exc:
        raise StationMetadataValidationError(f"{path}.{key} must be numeric") from exc


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise StationMetadataValidationError("boolean is not numeric")
    if isinstance(value, int | float | str):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise StationMetadataValidationError("invalid decimal") from exc
    raise StationMetadataValidationError("invalid decimal")


def _required_datetime(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> datetime:
    value = _optional_datetime(item, key, path)
    if value is None:
        raise StationMetadataValidationError(f"{path}.{key} is required")
    return value


def _optional_datetime(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> datetime | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise StationMetadataValidationError(f"{path}.{key} must be an ISO timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StationMetadataValidationError(
            f"{path}.{key} must be an ISO timestamp"
        ) from exc


def _optional_date(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> date | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise StationMetadataValidationError(f"{path}.{key} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise StationMetadataValidationError(f"{path}.{key} must be an ISO date") from exc


def _optional_sha256(
    item: Mapping[str, object],
    key: str,
    path: str,
) -> str | None:
    value = _optional_str(item, key, path)
    if value is None:
        return None
    if len(value) != SHA256_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise StationMetadataValidationError(
            f"{path}.{key} must be a lowercase 64-character SHA256"
        )
    return value
