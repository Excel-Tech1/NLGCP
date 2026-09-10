"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

import gzip
import os

from nlgcp_scientific_expansion import nav_acquisition
from nlgcp_scientific_expansion.models import NavProductRecord

_SYNTHETIC_NAV = """     3.04           N: GPS NAV DATA                         RINEX VERSION / TYPE
SYNTHETIC TEST DATA                                       PGM / RUN BY / DATE
2024     1     7     0     0     0.0000000                 LEAP SECONDS
END OF HEADER
G01 2024  1  7  0  0  0.0 1.0 2.0 3.0
      4.0      5.0      6.0      7.0
G02 2024  1  7  1  0  0.0 1.0 2.0 3.0
      4.0      5.0      6.0      7.0
"""


def _write_nav(tmp_path: object, name: str, text: str) -> str:
    path = os.path.join(str(tmp_path), name)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_plan_is_deterministic() -> None:
    first = nav_acquisition.plan_products([7, 26, 7], 2024)
    second = nav_acquisition.plan_products([26, 7], 2024)
    assert [plan.doy for plan in first] == [7, 26]
    assert [plan.source_url for plan in first] == [plan.source_url for plan in second]
    assert first[0].expected_filename == "BRDC00IGS_R_20240070000_01D_MN.rnx.gz"
    assert first[0].download_status == "PLANNED"


def test_filename_for_doy() -> None:
    assert (
        nav_acquisition.filename_for_doy(2024, 26)
        == "BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    )


def test_verify_accepts_good_product(tmp_path: object) -> None:
    path = _write_nav(tmp_path, "nav.gz", _SYNTHETIC_NAV)
    record = NavProductRecord(year=2024, doy=7, stored_path=path)
    verified = nav_acquisition.verify_product(record, 2024, 7)
    assert verified.validation_status == "ACCEPTED"
    assert verified.ephemeris_records == 2
    assert verified.sha256
    assert verified.size_bytes == os.path.getsize(path)


def test_verify_rejects_corrupt_gzip(tmp_path: object) -> None:
    path = os.path.join(str(tmp_path), "bad.gz")
    with open(path, "wb") as handle:
        handle.write(b"not a gzip file at all")
    record = NavProductRecord(year=2024, doy=7, stored_path=path)
    verified = nav_acquisition.verify_product(record, 2024, 7)
    assert verified.validation_status == "REJECTED"


def test_verify_rejects_missing_header(tmp_path: object) -> None:
    path = _write_nav(tmp_path, "nohead.gz", "just some text without epochs\n")
    record = NavProductRecord(year=2024, doy=7, stored_path=path)
    verified = nav_acquisition.verify_product(record, 2024, 7)
    assert verified.validation_status == "REJECTED"


def test_verify_rejects_date_mismatch(tmp_path: object) -> None:
    wrong = _SYNTHETIC_NAV.replace("2024  1  7", "2024  6  7")
    path = _write_nav(tmp_path, "wrong.gz", wrong)
    record = NavProductRecord(year=2024, doy=7, stored_path=path)
    verified = nav_acquisition.verify_product(record, 2024, 7)
    assert verified.validation_status == "REJECTED"
    assert "mismatch" in verified.validation_detail


def test_verify_rejects_missing_file() -> None:
    record = NavProductRecord(year=2024, doy=7, stored_path="/nonexistent/nav.gz")
    verified = nav_acquisition.verify_product(record, 2024, 7)
    assert verified.validation_status == "REJECTED"


def test_error_page_detection() -> None:
    assert nav_acquisition._looks_like_error_page(b"<html><body>404</body>")
    assert nav_acquisition._looks_like_error_page(b"<!DOCTYPE html><html>")
    assert not nav_acquisition._looks_like_error_page(b"\x1f\x8b\x08 binary gzip")


def test_validation_inventory_rejects_unvalidated_or_hash_mismatch(tmp_path: object) -> None:
    from pathlib import Path

    product_dir = Path(str(tmp_path))
    good = product_dir / "BRDC00IGS_R_20240070000_01D_MN.rnx.gz"
    good.write_bytes(b"good")
    bad = product_dir / "BRDC00IGS_R_20240080000_01D_MN.rnx.gz"
    bad.write_bytes(b"bad")
    inventory = product_dir / "navigation-products.csv"
    inventory.write_text(
        "doy,stored_path,sha256,validation_status\n"
        f"7,{good},,ACCEPTED\n"
        f"8,{bad},not-the-file,ACCEPTED\n"
        f"9,{product_dir / 'missing.gz'},,ACCEPTED\n"
        f"10,{good},,UNVALIDATED\n",
        encoding="utf-8",
    )
    from nlgcp_scientific_expansion import loaders

    assert loaders.nav_inventory_by_day(str(product_dir), str(inventory)) == {
        7: good.name
    }
