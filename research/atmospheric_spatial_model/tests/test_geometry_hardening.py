"""Geometry-hardening regression tests (Phase 6/7 scientific validation).

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Each test pins a corrected behaviour found in the validation sprint:
Earth-rotation rate, RINEX radian units, GPST handling, geodetic ENU,
point-in-triangle containment, IDW/planar rules, and datum-anchored LOOCV.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model import constants  # noqa: E402
from nlgcp_atmospheric_model.interpolation import (  # noqa: E402
    barycentric_coordinates,
    interpolate,
    reference_triangle_area_m2,
)
from nlgcp_atmospheric_model.satellite_geometry import (  # noqa: E402
    BroadcastEphemeris,
    broadcast_position,
    elevation_azimuth_deg,
    gps_datetime_to_tow,
    parse_rinex3_gps_nav,
)
from nlgcp_atmospheric_model.spatial import ecef_to_local_enu  # noqa: E402
from nlgcp_atmospheric_model.troposphere import ecef_to_geodetic  # noqa: E402
from nlgcp_atmospheric_model.validation import run_loocv  # noqa: E402
from phase6_fixtures import synthetic_nav_text  # noqa: E402

EARTH_A = 6378137.0
EARTH_F = 1.0 / 298.257223563


def geodetic_to_ecef(lat_deg: float, lon_deg: float, h: float) -> tuple[float, float, float]:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    e2 = EARTH_F * (2.0 - EARTH_F)
    n = EARTH_A / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return (
        (n + h) * math.cos(lat) * math.cos(lon),
        (n + h) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - e2) + h) * math.sin(lat),
    )


def test_earth_rotation_rate_matches_is_gps_200() -> None:
    assert math.isclose(constants.EARTH_ROT_RATE_RAD_S, 7.2921151467e-05, rel_tol=1e-12)


def test_rinex_angles_stored_in_radians(tmp_path: Path) -> None:
    nav = tmp_path / "BRDC.nav"
    nav.write_text(synthetic_nav_text(), encoding="utf-8")
    eph = parse_rinex3_gps_nav(nav)["G01"][0]
    # Fixture records i0 = 0.9599 rad (~55 deg); a pi-scaled parse gives ~3.01.
    assert eph.i0_rad == pytest.approx(0.9599310886, rel=1e-9)
    assert eph.i0_rad < math.pi / 2.0


def test_real_brdc_inclination_is_physical() -> None:
    product = Path(
        "/home/excellence/nlgcp-data/external-products/brdc/2024"
        "/BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    )
    if not product.is_file():
        pytest.skip("real navigation product unavailable")
    records = parse_rinex3_gps_nav(product)
    assert records
    for block in records.values():
        for eph in block:
            # GPS inclination ~55 deg; pi-scaled garbage would sit near 150-180.
            assert 0.9 < eph.i0_rad < 1.1
            break
        break


def test_gpst_conversion_has_no_leap_offset() -> None:
    week, tow = gps_datetime_to_tow(datetime(2024, 1, 26, 0, 0, tzinfo=UTC))
    assert week == 2298
    assert tow == pytest.approx(432000.0)


def test_inclined_circular_orbit_leaves_equatorial_plane() -> None:
    a = 26_560_000.0
    inc = math.radians(55.0)
    eph = BroadcastEphemeris(
        satellite_id="G01",
        toc_week=2298,
        toc_tow_s=432000.0,
        af0_s=0.0,
        af1_s_s=0.0,
        af2_s_s2=0.0,
        iode=1.0,
        crs_m=0.0,
        delta_n_rad_s=0.0,
        m0_rad=math.pi / 2.0,
        cuc_rad=0.0,
        e=0.0,
        cus_rad=0.0,
        sqrt_a_m_sqrt=math.sqrt(a),
        toe_tow_s=432000.0,
        toe_week=2298,
        cic_rad=0.0,
        omega0_rad=0.0,
        cis_rad=0.0,
        i0_rad=inc,
        crc_m=0.0,
        omega_rad=0.0,
        omega_dot_rad_s=0.0,
        idot_rad_s=0.0,
    )
    pos = broadcast_position(eph, 2298, 432000.0)
    assert math.dist(pos, (0.0, 0.0, 0.0)) == pytest.approx(a, rel=1e-9)
    assert pos[2] == pytest.approx(a * math.sin(inc), rel=1e-6)


def test_enu_origin_latitude_is_geodetic() -> None:
    abfc = (6246471.17131, 820849.02064, 994268.16646)
    lat, _ = ecef_to_geodetic(abfc), None
    # Shared frame: spatial ENU must use the same geodetic latitude as the
    # tropospheric chain, not geocentric atan2(z, hypot(x, y)).
    geocentric = math.atan2(abfc[2], math.hypot(abfc[0], abfc[1]))
    assert lat[0] != pytest.approx(geocentric)
    assert math.degrees(lat[0]) == pytest.approx(9.027668, abs=1e-4)


def test_enu_cardinal_signs_and_antisymmetry() -> None:
    origin = geodetic_to_ecef(9.0, 7.5, 500.0)
    east_pt: tuple[float, float, float] = (origin[0] - 100.0, origin[1] + 100.0, origin[2])
    # A point displaced along +ECEF-y at lon ~7.5E must read East-positive.
    assert ecef_to_local_enu(east_pt, origin)[0] > 0.0
    up_scale = 1.0 + 100.0 / math.dist(origin, (0, 0, 0))
    up_pt: tuple[float, float, float] = (
        origin[0] * up_scale,
        origin[1] * up_scale,
        origin[2] * up_scale,
    )
    assert ecef_to_local_enu(up_pt, origin)[2] == pytest.approx(100.0, abs=2.0)
    a = geodetic_to_ecef(4.6, 7.9, 40.0)
    b = geodetic_to_ecef(4.8, 7.0, 50.0)
    fwd = ecef_to_local_enu(b, a)
    back = ecef_to_local_enu(a, b)
    # Antisymmetric to first order: |A->B| == |B->A|.
    assert math.dist(fwd, (0, 0, 0)) == pytest.approx(math.dist(back, (0, 0, 0)), rel=1e-3)
    assert ecef_to_local_enu(a, a) == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


def test_geodetic_zenith_satellite_is_overhead() -> None:
    station = geodetic_to_ecef(45.0, 0.0, 0.0)
    lat, lon = math.radians(45.0), 0.0
    up = (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))
    satellite: tuple[float, float, float] = (
        station[0] + up[0] * 20_200_000.0,
        station[1] + up[1] * 20_200_000.0,
        station[2] + up[2] * 20_200_000.0,
    )
    elev, _ = elevation_azimuth_deg(station, satellite)
    # Geocentric latitude would tilt this by ~0.19 deg at 45 deg latitude.
    assert elev == pytest.approx(90.0, abs=0.01)


def test_barycentric_containment() -> None:
    a, b, c = (0.0, 0.0), (1000.0, 0.0), (0.0, 1000.0)
    w1, w2, w3, inside = barycentric_coordinates(a, b, c, (100.0, 100.0))
    assert inside is True
    assert w1 + w2 + w3 == pytest.approx(1.0)
    assert barycentric_coordinates(a, b, c, (900.0, 900.0))[3] is False
    # Boundary counts as interpolation, not extrapolation.
    assert barycentric_coordinates(a, b, c, (500.0, 0.0))[3] is True
    # Degenerate triangle never contains.
    assert barycentric_coordinates((0, 0), (1, 1), (2, 2), (1, 1))[3] is False


def test_reference_triangle_area_units() -> None:
    o = geodetic_to_ecef(9.0, 7.5, 0.0)
    # Displace along the true ECEF East/North unit vectors: a 1 km East step
    # must read back as (E,N) = (1000, 0) and a 1 km North step as (0, 1000).
    lat, lon = math.radians(9.0), math.radians(7.5)
    east_unit = (-math.sin(lon), math.cos(lon), 0.0)
    north_unit = (
        -math.sin(lat) * math.cos(lon),
        -math.sin(lat) * math.sin(lon),
        math.cos(lat),
    )
    e_step: tuple[float, float, float] = (
        o[0] + east_unit[0] * 1000.0,
        o[1] + east_unit[1] * 1000.0,
        o[2] + east_unit[2] * 1000.0,
    )
    n_step: tuple[float, float, float] = (
        o[0] + north_unit[0] * 1000.0,
        o[1] + north_unit[1] * 1000.0,
        o[2] + north_unit[2] * 1000.0,
    )
    e1 = ecef_to_local_enu(e_step, o)
    n1 = ecef_to_local_enu(n_step, o)
    assert e1[0] == pytest.approx(1000.0, rel=1e-6)
    assert e1[1] == pytest.approx(0.0, abs=1e-6)
    assert n1[0] == pytest.approx(0.0, abs=1e-6)
    assert n1[1] == pytest.approx(1000.0, rel=1e-6)
    with pytest.raises(ValueError):
        reference_triangle_area_m2([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], (0.0, 0.0, 0.0))


def test_interpolation_extrapolation_uses_triangle() -> None:
    o = geodetic_to_ecef(9.0, 7.5, 0.0)
    r1 = (o[0], o[1] + 10_000.0, o[2])
    r2 = (o[0], o[1] - 10_000.0, o[2])
    r3 = (o[0], o[1], o[2] + 10_000.0)
    refs = [("R1", r1, 1.0), ("R2", r2, 1.0), ("R3", r3, 1.0)]
    inside = interpolate(
        model_name="zero",
        epoch_iso="e",
        satellite_id="G01",
        target_station="T",
        target_xyz=o,
        references=refs,
    )
    assert inside.extrapolated is False
    far = (o[0], o[1] + 100_000.0, o[2] + 100_000.0)
    outside = interpolate(
        model_name="zero",
        epoch_iso="e",
        satellite_id="G01",
        target_station="T",
        target_xyz=far,
        references=refs,
    )
    assert outside.extrapolated is True


def test_idw_rules() -> None:
    refs = [
        ("A", (0.0, 0.0, 0.0), 2.0),
        ("B", (1000.0, 0.0, 0.0), 4.0),
    ]
    with pytest.raises(ValueError):
        interpolate(
            model_name="idw",
            epoch_iso="e",
            satellite_id="G01",
            target_station="T",
            target_xyz=(500.0, 0.0, 0.0),
            references=refs,
            power=0.0,
        )
    exact = interpolate(
        model_name="idw",
        epoch_iso="e",
        satellite_id="G01",
        target_station="T",
        target_xyz=(0.0, 0.0, 0.0),
        references=refs,
    )
    assert exact.predicted_m == pytest.approx(2.0)
    mid = interpolate(
        model_name="idw",
        epoch_iso="e",
        satellite_id="G01",
        target_station="T",
        target_xyz=(500.0, 0.0, 0.0),
        references=refs,
    )
    assert mid.predicted_m == pytest.approx(3.0)


def test_planar_recovers_exact_plane_and_rejects_singular() -> None:
    o = geodetic_to_ecef(9.0, 7.5, 0.0)
    r1 = (o[0], o[1] + 10_000.0, o[2])
    r2 = (o[0], o[1] - 10_000.0, o[2])
    r3 = (o[0], o[1], o[2] + 10_000.0)
    pred = interpolate(
        model_name="planar",
        epoch_iso="e",
        satellite_id="G01",
        target_station="T",
        target_xyz=o,
        references=[("R1", r1, 1.0), ("R2", r2, 1.0), ("R3", r3, 1.0)],
        observed_m=1.0,
    )
    assert pred.predicted_m == pytest.approx(1.0, abs=1e-9)
    assert pred.residual_m == pytest.approx(0.0, abs=1e-9)
    line = [(float(i) * 1000.0, 0.0, 0.0) for i in range(3)]
    singular = interpolate(
        model_name="planar",
        epoch_iso="e",
        satellite_id="G01",
        target_station="T",
        target_xyz=(500.0, 0.0, 0.0),
        references=[(f"R{i}", xyz, 1.0) for i, xyz in enumerate(line)],
    )
    assert singular.predicted_m is None
    assert singular.reason is not None and "singular" in singular.reason


def test_loocv_datum_defaults_reference_only() -> None:
    coords = {
        "A": (6378137.0, 0.0, 0.0),
        "B": (6378137.0 + 50_000.0, 20_000.0, 15_000.0),
        "C": (6378137.0 + 10_000.0, 60_000.0, -12_000.0),
        "T": (6378137.0 + 40_000.0, 40_000.0, 8_000.0),
    }
    epochs, sats = ["e1", "e2"], ["G01"]
    observed = {(e, "G01", s): v for e in epochs for s, v in (("B", 0.5), ("C", -0.25), ("T", 0.1))}
    result = run_loocv(
        epochs=epochs,
        satellites=sats,
        coords=coords,
        observed=observed,
        datum_defaults={"A": 0.0},
    )
    folds = {f["target"]: f for f in result["folds"]}
    # Datum fold has no measurement: unevaluable, never a free zero win.
    assert folds["A"]["evaluated"] == 0
    assert all(folds[t]["evaluated"] > 0 for t in ("B", "C", "T"))
    assert result["comparison_keys"] > 0
    # Without datum defaults the datum-as-reference folds lose planar.
    bare = run_loocv(epochs=epochs, satellites=sats, coords=coords, observed=observed)
    assert bare["comparison_keys"] == 0
