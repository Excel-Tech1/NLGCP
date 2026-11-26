#!/usr/bin/env python3
"""B-04 / B-05 Reproducible Public Geodetic Product Acquisition & Provenance Recorder.

Acquires legitimate, publicly accessible IGS/CODE/CAS geodetic products (no auth bypass,
no credentials) into ``${NLGCP_DATA_ROOT}/external-products/igs/{2011,2024}/`` and writes
a SHA-256 provenance manifest recording every download attempt, frame header, and failure.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))

TARGET_PRODUCTS: list[dict[str, str]] = [
    # --- 2011 March window (GPS Week 1628: DOY 079=16280, DOY 080=16281) ---
    # IGS Final (BKG HTTPS)
    {
        "year": "2011",
        "subdir": "precise-orbits",
        "date": "2011-03-20",
        "doy": "079",
        "product_type": "PRECISE_ORBIT_SP3",
        "provider": "IGS Final (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16280.sp3.Z",
    },
    {
        "year": "2011",
        "subdir": "clocks",
        "date": "2011-03-20",
        "doy": "079",
        "product_type": "PRECISE_CLOCK_30S",
        "provider": "IGS Final (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16280.clk_30s.Z",
    },
    {
        "year": "2011",
        "subdir": "precise-orbits",
        "date": "2011-03-21",
        "doy": "080",
        "product_type": "PRECISE_ORBIT_SP3",
        "provider": "IGS Final (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16281.sp3.Z",
    },
    {
        "year": "2011",
        "subdir": "clocks",
        "date": "2011-03-21",
        "doy": "080",
        "product_type": "PRECISE_CLOCK_30S",
        "provider": "IGS Final (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16281.clk_30s.Z",
    },
    {
        "year": "2011",
        "subdir": "erp",
        "date": "2011-03-20..2011-03-26",
        "doy": "079-085",
        "product_type": "ERP_WEEKLY",
        "provider": "IGS Final (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16287.erp.Z",
    },
    # CODE Final 2011 March (AIUB HTTPS: orbits, 5s clocks, ERP, IONEX, DCBs)
    {
        "year": "2011",
        "subdir": "precise-orbits",
        "date": "2011-03-20",
        "doy": "079",
        "product_type": "PRECISE_ORBIT_SP3_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/COD16280.EPH.Z",
    },
    {
        "year": "2011",
        "subdir": "clocks",
        "date": "2011-03-20",
        "doy": "079",
        "product_type": "PRECISE_CLOCK_05S_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/COD16280.CLK_05S.Z",
    },
    {
        "year": "2011",
        "subdir": "precise-orbits",
        "date": "2011-03-21",
        "doy": "080",
        "product_type": "PRECISE_ORBIT_SP3_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/COD16281.EPH.Z",
    },
    {
        "year": "2011",
        "subdir": "clocks",
        "date": "2011-03-21",
        "doy": "080",
        "product_type": "PRECISE_CLOCK_05S_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/COD16281.CLK_05S.Z",
    },
    {
        "year": "2011",
        "subdir": "erp",
        "date": "2011-03-20..2011-03-26",
        "doy": "079-085",
        "product_type": "ERP_WEEKLY_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/COD16287.ERP.Z",
    },
    {
        "year": "2011",
        "subdir": "ionosphere",
        "date": "2011-03-20",
        "doy": "079",
        "product_type": "IONEX_GIM_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/CODG0790.11I.Z",
    },
    {
        "year": "2011",
        "subdir": "ionosphere",
        "date": "2011-03-21",
        "doy": "080",
        "product_type": "IONEX_GIM_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/CODG0800.11I.Z",
    },
    {
        "year": "2011",
        "subdir": "biases",
        "date": "2011-03",
        "doy": "060-090",
        "product_type": "DCB_P1C1_CODE",
        "provider": "CODE Monthly (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/P1C11103.DCB.Z",
    },
    {
        "year": "2011",
        "subdir": "biases",
        "date": "2011-03",
        "doy": "060-090",
        "product_type": "DCB_P1P2_CODE",
        "provider": "CODE Monthly (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/P1P21103.DCB.Z",
    },
    # --- 2011 December window (GPS Week 1665: DOY 339..342 = 16651..16654) ---
    *[
        item
        for doy, dow, dt in [
            ("339", "1", "2011-12-05"),
            ("340", "2", "2011-12-06"),
            ("341", "3", "2011-12-07"),
            ("342", "4", "2011-12-08"),
        ]
        for item in (
            {
                "year": "2011",
                "subdir": "precise-orbits",
                "date": dt,
                "doy": doy,
                "product_type": "PRECISE_ORBIT_SP3",
                "provider": "IGS Final (via BKG)",
                "url": f"https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs1665{dow}.sp3.Z",
            },
            {
                "year": "2011",
                "subdir": "clocks",
                "date": dt,
                "doy": doy,
                "product_type": "PRECISE_CLOCK_30S",
                "provider": "IGS Final (via BKG)",
                "url": f"https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs1665{dow}.clk_30s.Z",
            },
            {
                "year": "2011",
                "subdir": "precise-orbits",
                "date": dt,
                "doy": doy,
                "product_type": "PRECISE_ORBIT_SP3_CODE",
                "provider": "CODE Final (AIUB)",
                "url": f"https://www.aiub.unibe.ch/download/CODE/2011/COD1665{dow}.EPH.Z",
            },
            {
                "year": "2011",
                "subdir": "clocks",
                "date": dt,
                "doy": doy,
                "product_type": "PRECISE_CLOCK_05S_CODE",
                "provider": "CODE Final (AIUB)",
                "url": f"https://www.aiub.unibe.ch/download/CODE/2011/COD1665{dow}.CLK_05S.Z",
            },
            {
                "year": "2011",
                "subdir": "ionosphere",
                "date": dt,
                "doy": doy,
                "product_type": "IONEX_GIM_CODE",
                "provider": "CODE Final (AIUB)",
                "url": f"https://www.aiub.unibe.ch/download/CODE/2011/CODG{doy}0.11I.Z",
            },
        )
    ],
    {
        "year": "2011",
        "subdir": "erp",
        "date": "2011-12-04..2011-12-10",
        "doy": "338-344",
        "product_type": "ERP_WEEKLY",
        "provider": "IGS Final (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16657.erp.Z",
    },
    {
        "year": "2011",
        "subdir": "erp",
        "date": "2011-12-04..2011-12-10",
        "doy": "338-344",
        "product_type": "ERP_WEEKLY_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/COD16657.ERP.Z",
    },
    {
        "year": "2011",
        "subdir": "biases",
        "date": "2011-12",
        "doy": "335-365",
        "product_type": "DCB_P1C1_CODE",
        "provider": "CODE Monthly (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/P1C11112.DCB.Z",
    },
    {
        "year": "2011",
        "subdir": "biases",
        "date": "2011-12",
        "doy": "335-365",
        "product_type": "DCB_P1P2_CODE",
        "provider": "CODE Monthly (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2011/P1P21112.DCB.Z",
    },
    {
        "year": "2011",
        "subdir": "antex",
        "date": "2011-03",
        "doy": "079-080",
        "product_type": "ANTEX_IGS05",
        "provider": "IGS Central Bureau (files.igs.org)",
        "url": "https://files.igs.org/pub/station/general/pcv_archive/igs05_1627.atx",
    },
    {
        "year": "2011",
        "subdir": "antex",
        "date": "2011-03",
        "doy": "079-080",
        "product_type": "ANTEX_IGS05_IGS_COMBINED",
        "provider": "IGS Central Bureau (files.igs.org)",
        "url": "https://files.igs.org/pub/station/general/pcv_archive/igs05_1617.atx",
    },
    {
        "year": "2011",
        "subdir": "antex",
        "date": "2011-12",
        "doy": "339-342",
        "product_type": "ANTEX_IGS08_IGS_COMBINED",
        "provider": "IGS Central Bureau (files.igs.org)",
        "url": "https://files.igs.org/pub/station/general/pcv_archive/igs08_1648.atx",
    },
    # --- 2024 DOY 026 (GPS Week 2298) CODE IONEX + OSB + CAS DCB (for B-05) ---
    {
        "year": "2024",
        "subdir": "ionosphere",
        "date": "2024-01-26",
        "doy": "026",
        "product_type": "IONEX_GIM_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2024/COD0OPSFIN_20240260000_01D_01H_GIM.INX.gz",
    },
    {
        "year": "2024",
        "subdir": "biases",
        "date": "2024-01-26",
        "doy": "026",
        "product_type": "OSB_BIA_CODE",
        "provider": "CODE Final (AIUB)",
        "url": "https://www.aiub.unibe.ch/download/CODE/2024/COD0OPSFIN_20240260000_01D_01D_OSB.BIA.gz",
    },
    {
        "year": "2024",
        "subdir": "biases",
        "date": "2024-01-26",
        "doy": "026",
        "product_type": "DCB_BIA_CAS",
        "provider": "CAS MGEX (via BKG)",
        "url": "https://igs.bkg.bund.de/root_ftp/IGS/products/2298/CAS0OPSRAP_20240260000_01D_01D_DCB.BIA.gz",
    },
]


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _inspect_header_lines(path: Path) -> list[str]:
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="latin1", errors="replace") as f:
                return [f.readline().rstrip("\r\n") for _ in range(12)]
        if path.suffix == ".Z":
            proc = subprocess.run(
                ["gzip", "-dc", str(path)],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if proc.returncode == 0:
                return proc.stdout.decode("latin1", errors="replace").splitlines()[:12]
        if path.suffix.lower() in {".atx", ".txt", ".erp", ".sp3"}:
            with path.open("rt", encoding="latin1", errors="replace") as f:
                return [f.readline().rstrip("\r\n") for _ in range(12)]
    except Exception:
        return []
    return []


def _extract_frame_hint(header_lines: list[str], product_type: str) -> str:
    joined = "\n".join(header_lines)
    if "ANTEX" in product_type:
        for line in header_lines:
            if "PCV TYPE / REFANT" in line or "ANTEX VERSION" in line:
                return line.strip()
        return "ANTEX"
    if "SP3" in product_type and header_lines:
        # SP3 line 1 cols 46-51 carry coordinate system (e.g., IGS05, IGS08, IGb08, IGS20)
        line1 = header_lines[0]
        if len(line1) >= 51:
            return line1[46:51].strip() or "UNKNOWN"
    for line in header_lines:
        if "SYS / PCVS APPLIED" in line or "ANALYSIS CENTER" in line or "FRAME" in line.upper():
            return line.strip()
    if "IONEX" in joined:
        return "IONEX_GIM"
    if "DCB" in product_type or "OSB" in product_type:
        return "CODE_OR_CAS_BIAS"
    return "NOT_STATED_IN_HEADER"


def main() -> int:
    records: list[dict[str, Any]] = []
    ok_count = 0
    fail_count = 0

    for spec in TARGET_PRODUCTS:
        filename = spec["url"].rsplit("/", 1)[-1]
        dest = DATA_ROOT / "external-products" / "igs" / spec["year"] / spec["subdir"] / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        retrieved_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        rec: dict[str, Any] = {
            **spec,
            "filename": filename,
            "local_path": str(dest),
            "retrieved_utc": retrieved_utc,
            "status": "FAILED",
            "http_status": None,
            "file_size_bytes": None,
            "sha256": None,
            "detected_frame_or_pcv": "UNKNOWN",
            "header_sample": [],
            "error": None,
        }
        try:
            if not dest.is_file() or dest.stat().st_size == 0:
                req = urllib.request.Request(
                    spec["url"], headers={"User-Agent": "NLGCP-B04-Acquire/1.0"}
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    rec["http_status"] = resp.status
                    data = resp.read()
                dest.write_bytes(data)
            else:
                rec["http_status"] = "CACHED_LOCAL"
            sha, size = _sha256_file(dest)
            hdr = _inspect_header_lines(dest)
            rec["sha256"] = sha
            rec["file_size_bytes"] = size
            rec["header_sample"] = hdr[:6]
            rec["detected_frame_or_pcv"] = _extract_frame_hint(hdr, spec["product_type"])
            rec["status"] = "VERIFIED"
            ok_count += 1
            print(
                f"OK   {spec['year']}/{spec['doy']:7s} {filename:44s} "
                f"{size:9d} B  {sha[:12]}  frame={rec['detected_frame_or_pcv']}"
            )
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            fail_count += 1
            print(f"FAIL {spec['year']}/{spec['doy']:7s} {filename:44s} {rec['error']}")
        records.append(rec)

    out_dir = DATA_ROOT / "processed" / "b04-coordinate-verification"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "nlgcp.b04.precise_products.v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_requested": len(TARGET_PRODUCTS),
        "acquired_verified": ok_count,
        "failed": fail_count,
        "records": records,
    }
    manifest_path = out_dir / "precise_products_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nSummary: {ok_count}/{len(TARGET_PRODUCTS)} verified, {fail_count} failed.")
    print(f"Manifest: {manifest_path}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
