"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Independent analytic circular orbit checks against the actual pinned RTKLIB
adapter. Set RTKLIB_SOURCE to run; dependency absence is an explicit skip.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import pytest
from nlgcp_vrs.geometry import build_adapter, geometry_batch


@pytest.fixture(scope="module")
def native() -> tuple[Path, dict[str, Any]]:
    path = os.environ.get("RTKLIB_SOURCE")
    if not path:
        pytest.skip("external pinned RTKLIB_SOURCE is required for native integration checks")
    return build_adapter(Path(__file__).resolve().parents[3], Path(path))


def navigation(path: Path, health: int = 0) -> None:
    def header(body: str, label: str) -> str:
        return f"{body:<60}{label}\n"

    # Circular equatorial orbit: choose OMEGA0 so longitude at toe is 0.4 rad.
    omega = 7.2921151467e-5
    vals = [
        1,
        0,
        0,
        0.2,
        0,
        0,
        0,
        math.sqrt(26560000),
        432000,
        0,
        (omega * 432000 + 0.2) % (2 * math.pi),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        2298,
        0,
        2,
        health,
        0,
        1,
        432000,
        4,
        0,
        0,
    ]
    text = header("     3.04           NAVIGATION DATA     G", "RINEX VERSION / TYPE")
    text += header("SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS", "COMMENT")
    text += header("", "END OF HEADER")
    text += "G01 2024 01 26 00 00 00" + "".join(f"{x:19.12E}" for x in (0.0, 0.0, 0.0)) + "\n"
    for i in range(0, 28, 4):
        text += "    " + "".join(f"{x:19.12E}" for x in vals[i : i + 4]) + "\n"
    path.write_text(text)


def test_native_radians_gpst_lighttime_sagnac(
    native: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    nav = tmp_path / "synthetic.rnx"
    navigation(nav)
    a, v = (6378137.0, 0.0, 0.0), (6378000.0, 10000.0, 0.0)
    p = 22000000.0
    rows = geometry_batch(
        native[0],
        nav,
        a,
        v,
        [("2024-01-26T00:00:00", "G01", p), ("2024-01-26T00:01:00", "G01", p)],
        tmp_path,
    )
    row = rows[0]
    assert "reason" not in row
    # Analytic circular orbit, nonzero radians, no UTC->GPST 18-second shift.
    earth_rate = 7.2921151467e-5
    rate = math.sqrt(3.986005e14 / 26560000.0**3) - earth_rate
    angle = 0.4 + rate * (-p / 299792458.0)
    satellite = (26560000 * math.cos(angle), 26560000 * math.sin(angle), 0.0)
    for k, value in zip(("x", "y", "z"), satellite, strict=True):
        assert row[f"satellite_anchor_{k}_m"] == pytest.approx(value, abs=0.0001)
    expected = math.dist(satellite, a) + earth_rate / 299792458.0 * (
        satellite[0] * a[1] - satellite[1] * a[0]
    )
    assert row["range_anchor_m"] == pytest.approx(expected, abs=0.0001)
    assert rows[0]["satellite_anchor_x_m"] != rows[1]["satellite_anchor_x_m"]
    assert row["satellite_anchor_x_m"] != row["satellite_target_x_m"]
    assert row["geometric_transformation_m"] == row["range_target_m"] - row["range_anchor_m"]
    assert native[1]["executable_sha256"]


def test_native_zero_displacement(native: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    nav = tmp_path / "synthetic.rnx"
    navigation(nav)
    point = (6378137.0, 0.0, 0.0)
    row = geometry_batch(
        native[0], nav, point, point, [("2024-01-26T00:00:00", "G01", 22000000)], tmp_path
    )[0]
    assert row["geometric_transformation_m"] == 0
    assert row["satellite_clock_translation_m"] == 0


@pytest.mark.parametrize("case", ["missing", "stale", "unhealthy", "horizon"])
def test_native_exclusions(native: tuple[Path, dict[str, Any]], tmp_path: Path, case: str) -> None:
    nav = tmp_path / "synthetic.rnx"
    navigation(nav, health=1 if case == "unhealthy" else 0)
    epoch = "2024-01-26T10:00:00" if case == "stale" else "2024-01-26T00:00:00"
    sat = "G02" if case == "missing" else "G01"
    point = (-6378137.0 if case == "horizon" else 6378137.0, 0.0, 0.0)
    row = geometry_batch(native[0], nav, point, point, [(epoch, sat, 22000000)], tmp_path)[0]
    assert "reason" in row
