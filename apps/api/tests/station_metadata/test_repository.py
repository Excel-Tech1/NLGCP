from __future__ import annotations

from decimal import Decimal

from nlgcp_api.station_metadata.repository import (
    _normalise_rows,
    coordinate_record_tuple,
    equipment_record_tuple,
)
from nlgcp_api.station_metadata.validation import validate_station_import_payload

from .test_validation import valid_payload


def test_coordinate_record_tuple_preserves_verified_fields() -> None:
    package = validate_station_import_payload(valid_payload())

    record = coordinate_record_tuple(package.coordinates[0], 42)

    assert record[0] == Decimal("9.000000000")
    assert record[1] == Decimal("7.000000000")
    assert record[6] == "SYNTHETIC-FRAME"
    assert record[7] == Decimal("2026.0000")
    assert record[11] == 42


def test_equipment_record_tuple_preserves_verified_fields() -> None:
    package = validate_station_import_payload(valid_payload())

    record = equipment_record_tuple(package.equipment[0], 84)

    assert record[0] == "SYNTHETIC RECEIVER"
    assert record[10] == 84


def test_normalise_rows_allows_decimal_scale_differences() -> None:
    assert _normalise_rows(((Decimal("9.000000000"),),)) == _normalise_rows(
        ((Decimal("9.0"),),)
    )
