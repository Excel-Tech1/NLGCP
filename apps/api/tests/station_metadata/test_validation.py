from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest
from nlgcp_api.station_metadata.validation import (
    StationMetadataValidationError,
    validate_station_import_payload,
)


def valid_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "sources": [
            {
                "key": "site-log",
                "source_type": "site_log",
                "path": "metadata/source-documents/synthetic-site.log",
                "source_reference": "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS",
                "source_date": None,
                "expected_sha256": None,
                "notes": None,
            }
        ],
        "provider": {
            "provider_code": "SYN",
            "provider_name": "Synthetic Provider",
            "operator_name": None,
            "country": "NG",
            "source_key": "site-log",
            "notes": None,
        },
        "station": {
            "station_code": "SY01",
            "station_name": "Synthetic Station",
            "network": "SYNTHETIC",
            "operator_name": None,
            "country": "NG",
            "status": "unknown",
            "first_observation": None,
            "last_observation": None,
            "source_key": "site-log",
            "notes": None,
        },
        "coordinates": [
            {
                "latitude_deg": "9.000000000",
                "longitude_deg": "7.000000000",
                "ellipsoidal_height_m": None,
                "ecef_x_m": None,
                "ecef_y_m": None,
                "ecef_z_m": None,
                "reference_frame": "SYNTHETIC-FRAME",
                "coordinate_epoch": "2026.0000",
                "solution_method": None,
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": None,
                "source_key": "site-log",
                "notes": "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS",
            }
        ],
        "equipment": [
            {
                "receiver_model": "SYNTHETIC RECEIVER",
                "receiver_serial": None,
                "receiver_firmware": None,
                "antenna_model": None,
                "antenna_serial": None,
                "radome": None,
                "antenna_height_m": None,
                "antenna_height_reference": None,
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": None,
                "source_key": "site-log",
                "notes": "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS",
            }
        ],
    }


def test_validates_minimal_canonical_package() -> None:
    package = validate_station_import_payload(valid_payload())

    assert package.provider.provider_code == "SYN"
    assert package.station.station_code == "SY01"
    assert package.coordinates[0].latitude_deg == Decimal("9.000000000")
    assert package.equipment[0].receiver_model == "SYNTHETIC RECEIVER"


def test_rejects_unknown_source_key() -> None:
    payload = valid_payload()
    station = payload["station"]
    assert isinstance(station, dict)
    station["source_key"] = "missing"

    with pytest.raises(StationMetadataValidationError, match="unknown source key"):
        validate_station_import_payload(payload)


def test_rejects_path_traversal_source() -> None:
    payload = valid_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    source = sources[0]
    assert isinstance(source, dict)
    source["path"] = "../source.log"

    with pytest.raises(StationMetadataValidationError, match="not traverse"):
        validate_station_import_payload(payload)


def test_rejects_partial_coordinate_pair() -> None:
    payload = valid_payload()
    coordinates = payload["coordinates"]
    assert isinstance(coordinates, list)
    coordinate = coordinates[0]
    assert isinstance(coordinate, dict)
    coordinate["longitude_deg"] = None

    with pytest.raises(StationMetadataValidationError, match="partial latitude"):
        validate_station_import_payload(payload)


def test_rejects_coordinate_interval_overlap() -> None:
    payload = valid_payload()
    coordinates = payload["coordinates"]
    assert isinstance(coordinates, list)
    second = deepcopy(coordinates[0])
    assert isinstance(second, dict)
    second["valid_from"] = "2026-06-01T00:00:00Z"
    coordinates.append(second)

    with pytest.raises(StationMetadataValidationError, match="overlapping"):
        validate_station_import_payload(payload)


def test_rejects_equipment_without_meaningful_fields() -> None:
    payload = valid_payload()
    equipment = payload["equipment"]
    assert isinstance(equipment, list)
    row = equipment[0]
    assert isinstance(row, dict)
    for key in (
        "receiver_model",
        "receiver_serial",
        "receiver_firmware",
        "antenna_model",
        "antenna_serial",
        "radome",
        "antenna_height_m",
        "antenna_height_reference",
    ):
        row[key] = None

    with pytest.raises(StationMetadataValidationError, match="at least one"):
        validate_station_import_payload(payload)
