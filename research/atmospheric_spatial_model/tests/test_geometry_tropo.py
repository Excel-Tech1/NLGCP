"""Tests for satellite geometry and tropospheric a priori models (synthetic)."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model.satellite_geometry import (  # noqa: E402
    BroadcastEphemeris,
    broadcast_position,
    elevation_azimuth_deg,
    geometry_table,
    gps_datetime_to_tow,
    parse_rinex3_gps_nav,
    select_ephemeris,
)
from nlgcp_atmospheric_model.troposphere import (  # noqa: E402
    STANDARD_ATMOSPHERE_LABEL,
    a_priori_slant,
    differential_apriori_m,
    ecef_to_geodetic,
    niell_hydrostatic_mapping,
    niell_wet_mapping,
    saastamoinen_zhd_m,
    standard_pressure_hpa,
    standard_zwd_m,
)
from phase6_fixtures import synthetic_nav_text  # noqa: E402

EARTH_R = 6_378_137.0


def circular_equatorial_eph() -> BroadcastEphemeris:
    a = 26_560_000.0
    return BroadcastEphemeris(
        satellite_id="G01",
        toc_week=2298,
        toc_tow_s=432000.0,
        af0_s=0.0,
        af1_s_s=0.0,
        af2_s_s2=0.0,
        iode=1.0,
        crs_m=0.0,
        delta_n_rad_s=0.0,
        m0_rad=0.0,
        cuc_rad=0.0,
        e=0.0,
        cus_rad=0.0,
        sqrt_a_m_sqrt=math.sqrt(a),
        toe_tow_s=432000.0,
        toe_week=2298,
        cic_rad=0.0,
        omega0_rad=0.0,
        cis_rad=0.0,
        i0_rad=0.0,
        crc_m=0.0,
        omega_rad=0.0,
        omega_dot_rad_s=0.0,
        idot_rad_s=0.0,
    )


def test_broadcast_circular_equatorial_radius() -> None:
    eph = circular_equatorial_eph()
    pos = broadcast_position(eph, 2298, 432000.0)
    assert math.dist(pos, (0.0, 0.0, 0.0)) == pytest.approx(26_560_000.0, rel=1e-9)
    assert pos[2] == pytest.approx(0.0, abs=1e-9)


def test_overhead_satellite_elevation_90() -> None:
    station = (EARTH_R, 0.0, 0.0)
    satellite = (EARTH_R + 20_200_000.0, 0.0, 0.0)
    elev, _ = elevation_azimuth_deg(station, satellite)
    assert elev == pytest.approx(90.0)


def test_east_horizon_satellite() -> None:
    station = (EARTH_R, 0.0, 0.0)
    satellite = (EARTH_R, 26_560_000.0, 0.0)
    elev, azim = elevation_azimuth_deg(station, satellite)
    assert elev == pytest.approx(0.0, abs=0.5)
    assert azim == pytest.approx(90.0, abs=0.5)


def test_gps_week_conversion() -> None:
    # RINEX labels in this archive are GPS time: no UTC leap-second offset.
    # 2024-01-26T00:00:00 GPST = week 2298, tow 432000 s exactly. A previous
    # revision added 18 s (432018), biasing broadcast propagation ~70 km.
    week, tow = gps_datetime_to_tow(datetime(2024, 1, 26, 0, 0, tzinfo=UTC))
    assert week == 2298
    assert tow == pytest.approx(432000.0)


def test_synthetic_nav_parses_and_selects(tmp_path: Path) -> None:
    nav = tmp_path / "BRDC.nav"
    nav.write_text(synthetic_nav_text(), encoding="utf-8")
    records = parse_rinex3_gps_nav(nav)
    assert set(records) == {"G01"}
    week, tow = gps_datetime_to_tow(datetime(2024, 1, 26, 0, 0, tzinfo=UTC))
    eph = select_ephemeris(records["G01"], week, tow)
    assert eph is not None
    pos = broadcast_position(eph, week, tow)
    assert math.dist(pos, (0.0, 0.0, 0.0)) == pytest.approx(26_560_000.0, rel=1e-6)


def test_geometry_table_excludes_non_gps() -> None:
    rows, exclusions = geometry_table(
        epochs=["2024-01-26T00:00:00.000000+00:00"],
        satellites=["G01", "R07"],
        station_coords={"STA": (EARTH_R, 0.0, 0.0)},
        nav_records={"G01": [circular_equatorial_eph()]},
        nav_hash="abc",
    )
    assert len(rows) == 1
    assert any(e.get("satellite") == "R07" for e in exclusions)


def test_geometry_table_missing_nav_excluded() -> None:
    rows, exclusions = geometry_table(
        epochs=["2024-01-26T00:00:00.000000+00:00"],
        satellites=["G02"],
        station_coords={"STA": (EARTH_R, 0.0, 0.0)},
        nav_records={},
        nav_hash="abc",
    )
    assert rows == []
    assert exclusions[0]["reason"] == "no GPS broadcast record available"


def test_saastamoinen_reference() -> None:
    # P=1013.25 hPa, lat 45 deg, h=0: ZHD = 0.0022768*P (documented reference).
    assert saastamoinen_zhd_m(1013.25, math.radians(45.0), 0.0) == pytest.approx(
        2.3069676, rel=1e-9
    )


def test_niell_zenith_is_unity() -> None:
    assert niell_hydrostatic_mapping(90.0, math.radians(9.0), 400.0, 26) == pytest.approx(
        1.0, rel=1e-6
    )
    assert niell_wet_mapping(90.0) == pytest.approx(1.0, rel=1e-6)


def test_niell_below_horizon_rejected() -> None:
    with pytest.raises(ValueError):
        niell_wet_mapping(2.0)


def test_standard_atmosphere_labelled_not_measured() -> None:
    assert "not measured" in STANDARD_ATMOSPHERE_LABEL
    assert standard_pressure_hpa(0.0) == pytest.approx(1013.25)
    assert standard_zwd_m(0.0) == pytest.approx(0.12)


def test_apriori_slant_reasonable_and_differential() -> None:
    station = (6_246_471.0, 820_849.0, 994_268.0)
    term = a_priori_slant(
        station_id="S",
        satellite_id="G01",
        epoch_iso="e",
        elevation_deg=45.0,
        station_ecef_m=station,
        doy=26,
    )
    assert term.slant_total_m == pytest.approx(3.2, abs=0.6)
    assert "not measured" in term.meteorology_source
    term2 = a_priori_slant(
        station_id="T",
        satellite_id="G01",
        epoch_iso="e",
        elevation_deg=45.0,
        station_ecef_m=(station[0] + 1e5, station[1], station[2]),
        doy=26,
    )
    assert differential_apriori_m(term2, term) != 0.0


def test_ecef_to_geodetic_equator() -> None:
    lat, lon, h = ecef_to_geodetic((EARTH_R, 0.0, 0.0))
    assert math.degrees(lat) == pytest.approx(0.0, abs=1e-6)
    assert lon == pytest.approx(0.0, abs=1e-9)
    assert h == pytest.approx(0.0, abs=1.0)
