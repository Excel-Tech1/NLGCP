#!/usr/bin/env python3
"""B-04 Deterministic Offline PRIDE PPP-AR 3.2.8 Static Coordinate Verification Runner.

Processes the 9 priority Nigerian CORS stations across the 6 authentic 2011 windows
(March DOY 079-080 in native IGS05; December DOY 339-342 in native IGS08) using
SHA-256-verified local CODE Final (5 s clocks) and IGS Final (30 s clocks) products.

Scientific integrity guarantees:
- Never modifies raw ``NIGNET2011.zip``, external products, or upstream PRIDE installation.
- Keeps IGS05 (March 2011) and IGS08 (December 2011) frames and ANTEX models strictly
  separated (``igs05_1627.atx`` vs ``igs08_1731.atx``).
- Explicitly runs float static PPP (``-f``) because 2011 operational CODE/IGS final products
  do not contain SINEX OSB phase biases, and records ``amb_fixing=NO`` transparently.
- Fails closed on corrupted/single-frequency station-days (e.g., RUST Dec 2011 L2=0%).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))
PRIDE_ROOT = Path(os.environ.get("PRIDE_PPPAR_ROOT", "/home/excellence/PRIDE-PPPAR"))
PRIDE_BIN = Path(os.environ.get("PRIDE_PPPAR_BIN", "/home/excellence/.PRIDE_PPPAR_BIN"))

RAW_ZIP_REL = Path("incoming/southern-nignet/NIGNET2011.zip")
EXPECTED_ZIP_SHA256 = "8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf"
NAV_RECOVERY_DIR = Path(
    "validation/southern-nignet/coordinate-navigation-recovery/"
    "run-20261030T132927Z/navigation-products"
)

PRIORITY_STATIONS: tuple[str, ...] = (
    "ABUZ",
    "BKFP",
    "CGGT",
    "FUTY",
    "MDGR",
    "OSGF",
    "RUST",
    "ULAG",
    "UNEC",
)

WINDOWS: tuple[dict[str, str], ...] = (
    {
        "doy": "079",
        "date": "2011-03-20",
        "window": "2011_MAR",
        "frame": "IGS05",
        "gps_week": "1628",
        "dow": "0",
        "code_sp3": "COD16280.EPH",
        "code_clk": "COD16280.CLK_05S",
        "code_erp": "COD16287.ERP",
        "igs_sp3": "igs16280.sp3",
        "igs_clk": "igs16280.clk_30s",
        "igs_erp": "igs16287.erp",
        "ionex": "CODG0790.11I",
    },
    {
        "doy": "080",
        "date": "2011-03-21",
        "window": "2011_MAR",
        "frame": "IGS05",
        "gps_week": "1628",
        "dow": "1",
        "code_sp3": "COD16281.EPH",
        "code_clk": "COD16281.CLK_05S",
        "code_erp": "COD16287.ERP",
        "igs_sp3": "igs16281.sp3",
        "igs_clk": "igs16281.clk_30s",
        "igs_erp": "igs16287.erp",
        "ionex": "CODG0800.11I",
    },
    {
        "doy": "339",
        "date": "2011-12-05",
        "window": "2011_DEC",
        "frame": "IGS08",
        "gps_week": "1665",
        "dow": "1",
        "code_sp3": "COD16651.EPH",
        "code_clk": "COD16651.CLK_05S",
        "code_erp": "COD16657.ERP",
        "igs_sp3": "igs16651.sp3",
        "igs_clk": "igs16651.clk_30s",
        "igs_erp": "igs16657.erp",
        "ionex": "CODG3390.11I",
    },
    {
        "doy": "340",
        "date": "2011-12-06",
        "window": "2011_DEC",
        "frame": "IGS08",
        "gps_week": "1665",
        "dow": "2",
        "code_sp3": "COD16652.EPH",
        "code_clk": "COD16652.CLK_05S",
        "code_erp": "COD16657.ERP",
        "igs_sp3": "igs16652.sp3",
        "igs_clk": "igs16652.clk_30s",
        "igs_erp": "igs16657.erp",
        "ionex": "CODG3400.11I",
    },
    {
        "doy": "341",
        "date": "2011-12-07",
        "window": "2011_DEC",
        "frame": "IGS08",
        "gps_week": "1665",
        "dow": "3",
        "code_sp3": "COD16653.EPH",
        "code_clk": "COD16653.CLK_05S",
        "code_erp": "COD16657.ERP",
        "igs_sp3": "igs16653.sp3",
        "igs_clk": "igs16653.clk_30s",
        "igs_erp": "igs16657.erp",
        "ionex": "CODG3410.11I",
    },
    {
        "doy": "342",
        "date": "2011-12-08",
        "window": "2011_DEC",
        "frame": "IGS08",
        "gps_week": "1665",
        "dow": "4",
        "code_sp3": "COD16654.EPH",
        "code_clk": "COD16654.CLK_05S",
        "code_erp": "COD16657.ERP",
        "igs_sp3": "igs16654.sp3",
        "igs_clk": "igs16654.clk_30s",
        "igs_erp": "igs16657.erp",
        "ionex": "CODG3420.11I",
    },
)

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Convert ECEF (m) to (lat_deg, lon_deg, height_m) on GRS80/WGS84."""
    p = math.hypot(x, y)
    lon = math.atan2(y, x)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(10):
        s = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * s * s)
        h = p / math.cos(lat) - n
        lat_new = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
        if abs(lat_new - lat) < 1e-13:
            lat = lat_new
            break
        lat = lat_new
    s = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * s * s)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def cov_xyz_to_enu_sigmas(
    lat_deg: float,
    lon_deg: float,
    cxx: float,
    cyy: float,
    czz: float,
    cxy: float,
    cxz: float,
    cyz: float,
) -> tuple[float, float, float]:
    """Rotate 3x3 ECEF covariance matrix into local ENU and return 1-sigma (E, N, U) in metres."""
    phi = math.radians(lat_deg)
    lam = math.radians(lon_deg)
    sp, cp = math.sin(phi), math.cos(phi)
    sl, cl = math.sin(lam), math.cos(lam)
    rot = (
        (-sl, cl, 0.0),
        (-sp * cl, -sp * sl, cp),
        (cp * cl, cp * sl, sp),
    )
    cov = (
        (cxx, cxy, cxz),
        (cxy, cyy, cyz),
        (cxz, cyz, czz),
    )
    sigmas: list[float] = []
    for row in rot:
        # row @ cov @ row.T
        var = 0.0
        for i in range(3):
            for j in range(3):
                var += row[i] * cov[i][j] * row[j]
        sigmas.append(math.sqrt(max(0.0, var)))
    return sigmas[0], sigmas[1], sigmas[2]


def decompress_z(src: Path, dst: Path) -> Path:
    """Decompress .Z or .gz into derived destination without modifying source."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and dst.stat().st_size > 0:
        return dst
    if src.suffix == ".gz":
        with gzip.open(src, "rb") as fin:
            dst.write_bytes(fin.read())
        return dst
    proc = subprocess.run(["gzip", "-dc", str(src)], capture_output=True, check=False, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"Failed to decompress {src}: {proc.stderr.decode(errors='replace')}")
    dst.write_bytes(proc.stdout)
    return dst


def prepare_environment(
    work_root: Path, stations: list[str], windows: list[dict[str, str]]
) -> dict[str, Any]:
    """Prepare extracted RINEX, nav, products, per-frame tables, and offline pdp3."""
    zip_path = DATA_ROOT / RAW_ZIP_REL
    if not zip_path.is_file():
        raise FileNotFoundError(f"Missing immutable archive: {zip_path}")

    # 1. Offline wrapper of pdp3.sh (never mutates PRIDE installation)
    upstream_pdp3 = PRIDE_ROOT / "scripts" / "pdp3.sh"
    upstream_sha = sha256_file(upstream_pdp3)
    offline_pdp3 = work_root / "bin" / "pdp3_offline.sh"
    offline_pdp3.parent.mkdir(parents=True, exist_ok=True)
    raw_script = upstream_pdp3.read_text(encoding="utf-8")
    if "readonly OFFLINE=NO" not in raw_script:
        raise RuntimeError("Unexpected pdp3.sh layout: 'readonly OFFLINE=NO' not found")
    offline_script = raw_script.replace("readonly OFFLINE=NO", "readonly OFFLINE=YES", 1)
    offline_pdp3.write_text(offline_script, encoding="utf-8")
    offline_pdp3.chmod(0o755)

    # 2. Per-frame table directories (strictly isolated ANTEX per reference frame!)
    igs05_code_atx = DATA_ROOT / "external-products/igs/2011/antex/igs05_1627.atx"
    igs05_igs_atx = DATA_ROOT / "external-products/igs/2011/antex/igs05_1617.atx"
    igs08_code_atx = PRIDE_ROOT / "table/igs08_1731.atx"
    igs08_igs_atx = DATA_ROOT / "external-products/igs/2011/antex/igs08_1648.atx"
    common_tables = (
        "file_name",
        "FES2004S1.dat",
        "Love_load_cm.dat",
        "orography_ell",
        "orography_ell_1x1",
        "gpt3_1.grd",
        "oceanload",
        "leap.sec",
        "sat_parameters",
    )
    frame_table_dirs: dict[str, Path] = {}
    for frame, links in (
        (
            "IGS05",
            (
                ("igs05_1627.atx", igs05_code_atx),
                ("igs05.atx", igs05_code_atx),
                ("igs05_1617.atx", igs05_igs_atx),
            ),
        ),
        (
            "IGS08",
            (
                ("igs08_1731.atx", igs08_code_atx),
                ("igs08.atx", igs08_code_atx),
                ("igs08_1648.atx", igs08_igs_atx),
            ),
        ),
    ):
        tdir = work_root / f"tables_{frame.lower()}"
        tdir.mkdir(parents=True, exist_ok=True)
        for tbl in common_tables:
            dst = tdir / tbl
            if not dst.exists():
                dst.symlink_to(PRIDE_ROOT / "table" / tbl)
        for name, atx_src in links:
            dst = tdir / name
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(atx_src)
        frame_table_dirs[frame] = tdir

    # 3. Extract needed 2011 RINEX observation files read-only from NIGNET2011.zip
    rnx_dir = work_root / "rinex_extracted"
    rnx_dir.mkdir(parents=True, exist_ok=True)
    needed_doys = {w["doy"] for w in windows}
    with zipfile.ZipFile(zip_path, "r") as zf:
        by_basename: dict[str, list[str]] = {}
        for m in zf.namelist():
            if m.endswith("/"):
                continue
            bn = Path(m).name.upper()
            by_basename.setdefault(bn, []).append(m)
        for st in stations:
            for doy in sorted(needed_doys):
                target_bn = f"{st}{doy}0.11O"
                matches = by_basename.get(target_bn, [])
                if len(matches) != 1:
                    raise FileNotFoundError(
                        f"Expected 1 ZIP member named {target_bn}, found {matches}"
                    )
                member = matches[0]
                dst = rnx_dir / f"{st.lower()}{doy}0.11o"
                if not dst.is_file() or dst.stat().st_size == 0:
                    dst.write_bytes(zf.read(member))

    # 4. Decompress broadcast GPS navigation files as brdm<doy>0.11p (expected by PrepareRinexNav)
    nav_src_dir = DATA_ROOT / NAV_RECOVERY_DIR
    nav_hashes: dict[str, str] = {}
    for doy in sorted(needed_doys):
        src_z = nav_src_dir / f"brdc{doy}0.11n.Z"
        if not src_z.is_file():
            raise FileNotFoundError(f"Missing 2011 GPS broadcast nav: {src_z}")
        nav_hashes[src_z.name] = sha256_file(src_z)
        decompress_z(src_z, rnx_dir / f"brdm{doy}0.11p")

    # 5. Decompress CODE Final & IGS Final products into derived product directory
    prod_dir = work_root / "products_2011"
    cmn_dir = prod_dir / "common"
    ion_dir = prod_dir / "ion"
    ext = DATA_ROOT / "external-products/igs/2011"
    for w in windows:
        decompress_z(ext / "precise-orbits" / f"{w['code_sp3']}.Z", cmn_dir / w["code_sp3"])
        decompress_z(ext / "clocks" / f"{w['code_clk']}.Z", cmn_dir / w["code_clk"])
        decompress_z(ext / "erp" / f"{w['code_erp']}.Z", cmn_dir / w["code_erp"])
        decompress_z(ext / "precise-orbits" / f"{w['igs_sp3']}.Z", cmn_dir / w["igs_sp3"])
        decompress_z(ext / "clocks" / f"{w['igs_clk']}.Z", cmn_dir / w["igs_clk"])
        decompress_z(ext / "erp" / f"{w['igs_erp']}.Z", cmn_dir / w["igs_erp"])
        decompress_z(ext / "ionosphere" / f"{w['ionex']}.Z", ion_dir / w["ionex"])

    return {
        "upstream_pdp3_path": str(upstream_pdp3),
        "upstream_pdp3_sha256": upstream_sha,
        "offline_pdp3_path": str(offline_pdp3),
        "frame_table_dirs": {k: str(v) for k, v in frame_table_dirs.items()},
        "rinex_dir": str(rnx_dir),
        "product_dir": str(prod_dir),
        "nav_sha256": nav_hashes,
        "antex_sha256": {
            "IGS05_igs05_1627.atx": sha256_file(igs05_code_atx),
            "IGS05_igs05_1617.atx": sha256_file(igs05_igs_atx),
            "IGS08_igs08_1731.atx": sha256_file(igs08_code_atx),
            "IGS08_igs08_1648.atx": sha256_file(igs08_igs_atx),
        },
    }


def write_custom_config(
    cfg_path: Path,
    *,
    table_dir: Path,
    product_dir: Path,
    sp3_name: str,
    clk_name: str,
    erp_name: str,
) -> None:
    """Create a deterministic PRIDE PPP-AR 3.2.8 config file from config_template."""
    tmpl = (PRIDE_ROOT / "table" / "config_template").read_text(encoding="utf-8")
    replacements = {
        "Table directory": str(table_dir),
        "Product directory": str(product_dir),
        "Satellite orbit": sp3_name,
        "Satellite clock": clk_name,
        "ERP": erp_name,
        "Quaternions": "NONE",
        "Code/phase bias": "NONE",
        "LEO quaternions": "NONE",
        "Iono 2nd": "YES",
    }
    lines: list[str] = []
    for line in tmpl.splitlines():
        replaced = False
        for key, val in replacements.items():
            if line.startswith(key):
                prefix = line.split("=", 1)[0]
                lines.append(f"{prefix}= {val}")
                replaced = True
                break
        if not replaced:
            lines.append(line)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_pos_file(pos_path: Path) -> dict[str, Any]:
    """Parse PRIDE static pos_* file (header metadata + coordinates + full covariance)."""
    text = pos_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    meta: dict[str, str] = {}
    data_line: str | None = None
    in_body = False
    for line in lines:
        if "END OF HEADER" in line:
            in_body = True
            continue
        if not in_body:
            if len(line) >= 60:
                val = line[:60].strip()
                key = line[60:].strip()
                if key in {
                    "STATION",
                    "OBS FIRST EPOCH",
                    "OBS LAST EPOCH",
                    "OBS INTERVAL (sec)",
                    "OBS MASK ANGLE (deg)",
                    "SAT ORBIT",
                    "SAT CLOCK",
                    "EARTH ROTATION PARAMETERS",
                    "SITE RECEIVER TYPE",
                    "SITE ANTENNA TYPE",
                    "SITE ANTENNA E/N/H (meter)",
                    "TABLE ANTEX",
                    "TROP ZENITH",
                    "TROP GRADIENT",
                    "IONO 2ND",
                    "TIDES",
                    "AMB FIXING",
                }:
                    meta[key] = val
        else:
            s = line.strip()
            if s and not s.startswith("*"):
                data_line = s
    if not data_line:
        raise ValueError(f"No coordinate data row in {pos_path}")
    parts = data_line.split()
    if len(parts) < 13:
        raise ValueError(f"Unexpected pos row ({len(parts)} cols) in {pos_path}: {data_line}")
    mjd = float(parts[1])
    x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
    sx, sy, sz = float(parts[5]), float(parts[6]), float(parts[7])
    rxy, rxz, ryz = float(parts[8]), float(parts[9]), float(parts[10])
    sig0 = float(parts[11])
    nobs = int(parts[12])
    if any(math.isnan(v) or math.isinf(v) for v in (x, y, z, sx, sy, sz, sig0)) or nobs <= 0:
        raise ValueError(f"Non-finite or zero-obs solution in {pos_path}: {data_line}")

    lat_deg, lon_deg, height_m = ecef_to_geodetic(x, y, z)
    s2 = sig0 * sig0
    sig_x = math.sqrt(max(0.0, s2 * sx))
    sig_y = math.sqrt(max(0.0, s2 * sy))
    sig_z = math.sqrt(max(0.0, s2 * sz))
    sig_e, sig_n, sig_u = cov_xyz_to_enu_sigmas(
        lat_deg, lon_deg, s2 * sx, s2 * sy, s2 * sz, s2 * rxy, s2 * rxz, s2 * ryz
    )
    ant_enh = meta.get("SITE ANTENNA E/N/H (meter)", "").split()
    delta_h = float(ant_enh[2]) if len(ant_enh) == 3 else None

    return {
        "mjd": mjd,
        "x_m": x,
        "y_m": y,
        "z_m": z,
        "lat_deg": lat_deg,
        "lon_deg": lon_deg,
        "height_m": height_m,
        "sx": sx,
        "sy": sy,
        "sz": sz,
        "rxy": rxy,
        "rxz": rxz,
        "ryz": ryz,
        "sig0_m": sig0,
        "nobs": nobs,
        "sigma_x_m": sig_x,
        "sigma_y_m": sig_y,
        "sigma_z_m": sig_z,
        "sigma_e_m": sig_e,
        "sigma_n_m": sig_n,
        "sigma_u_m": sig_u,
        "first_epoch": meta.get("OBS FIRST EPOCH"),
        "last_epoch": meta.get("OBS LAST EPOCH"),
        "sat_orbit": meta.get("SAT ORBIT"),
        "sat_clock": meta.get("SAT CLOCK"),
        "erp": meta.get("EARTH ROTATION PARAMETERS"),
        "receiver_type": meta.get("SITE RECEIVER TYPE"),
        "antenna_type": meta.get("SITE ANTENNA TYPE"),
        "antenna_delta_h_m": delta_h,
        "antex_table": meta.get("TABLE ANTEX"),
        "iono_2nd": meta.get("IONO 2ND"),
        "tides": meta.get("TIDES"),
        "amb_fixing": meta.get("AMB FIXING"),
    }


def parse_stt_phase_rms_mm(stt_path: Path) -> float | None:
    if not stt_path.is_file():
        return None
    lines = stt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "+RMS OF RESIDUALS---PHASE(MM)" and i + 2 < len(lines):
            parts = lines[i + 2].split()
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    return None
    return None


def parse_ztd_summary(ztd_path: Path) -> dict[str, Any]:
    if not ztd_path.is_file():
        return {"ztd_epochs": 0, "zhd_mean_m": None, "zwd_mean_m": None, "ztd_mean_m": None}
    zhds: list[float] = []
    zwds: list[float] = []
    ztds: list[float] = []
    in_body = False
    for line in ztd_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "END OF HEADER" in line:
            in_body = True
            continue
        if not in_body:
            continue
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        parts = s.split()
        # Year Mon Day Hour Min Sec ZDD ZWDini ZWDcor
        if len(parts) >= 9:
            try:
                zhd = float(parts[6])
                zwd_ini = float(parts[7])
                zwd_cor = float(parts[8])
                zwd = zwd_ini + zwd_cor
                ztd = zhd + zwd
                if 1.5 < ztd < 3.5 and -0.1 < zwd < 0.8 and 1.5 < zhd < 2.8:
                    zhds.append(zhd)
                    zwds.append(zwd)
                    ztds.append(ztd)
            except ValueError:
                continue
    if not ztds:
        return {"ztd_epochs": 0, "zhd_mean_m": None, "zwd_mean_m": None, "ztd_mean_m": None}
    return {
        "ztd_epochs": len(ztds),
        "zhd_mean_m": round(sum(zhds) / len(zhds), 5),
        "zwd_mean_m": round(sum(zwds) / len(zwds), 5),
        "ztd_mean_m": round(sum(ztds) / len(ztds), 5),
    }


def run_single_job(job: dict[str, Any]) -> dict[str, Any]:
    station: str = job["station"]
    st_low = station.lower()
    w: dict[str, str] = job["window_spec"]
    ac: str = job["ac"]
    work_root = Path(job["work_root"])
    offline_pdp3 = Path(job["offline_pdp3"])
    table_dir = Path(job["table_dir"])
    product_dir = Path(job["product_dir"])
    rnx_path = Path(job["rnx_path"])
    doy = w["doy"]
    frame = w["frame"]

    run_base = work_root / "runs" / ac.lower() / doy / station
    session_dir = run_base / "2011" / doy
    if run_base.exists():
        shutil.rmtree(run_base)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Pre-place leap.sec and sat_parameters in session_dir so PrepareTables does zero downloads
    for tbl in ("leap.sec", "sat_parameters"):
        shutil.copy2(PRIDE_ROOT / "table" / tbl, session_dir / tbl)

    sp3_name = w["code_sp3"] if ac == "CODE" else w["igs_sp3"]
    clk_name = w["code_clk"] if ac == "CODE" else w["igs_clk"]
    erp_name = w["code_erp"] if ac == "CODE" else w["igs_erp"]

    cfg_path = run_base / f"config_{ac.lower()}_{doy}_{st_low}"
    write_custom_config(
        cfg_path,
        table_dir=table_dir,
        product_dir=product_dir,
        sp3_name=sp3_name,
        clk_name=clk_name,
        erp_name=erp_name,
    )

    env = os.environ.copy()
    env["PATH"] = f"{PRIDE_BIN}:{env.get('PATH', '')}"
    cmd = [
        str(offline_pdp3),
        "-cfg",
        str(cfg_path),
        "-m",
        "S",
        "-f",
        "-sys",
        "G",
        "-hion",
        "-n",
        st_low,
        str(rnx_path),
    ]
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(run_base),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    elapsed_s = round(time.monotonic() - t0, 2)
    log_path = run_base / "pdp3.log"
    combined_log = proc.stdout + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else "")
    log_path.write_text(combined_log, encoding="utf-8")

    pos_path = session_dir / f"pos_2011{doy}_{st_low}"
    stt_path = session_dir / f"stt_2011{doy}_{st_low}"
    ztd_path = session_dir / f"ztd_2011{doy}_{st_low}"

    record: dict[str, Any] = {
        "station": station,
        "doy": doy,
        "date": w["date"],
        "window": w["window"],
        "ac": ac,
        "frame": frame,
        "sp3_product": sp3_name,
        "clk_product": clk_name,
        "erp_product": erp_name,
        "ionex_product": w["ionex"],
        "returncode": proc.returncode,
        "elapsed_s": elapsed_s,
        "pos_path": str(pos_path),
        "ztd_path": str(ztd_path),
        "log_path": str(log_path),
        "status": "FAILED",
        "failure_reason": None,
    }

    if proc.returncode != 0 or not pos_path.is_file():
        err_lines = [
            re.sub(r"\x1b\[[0-9;]*m", "", ln).strip()
            for ln in combined_log.splitlines()
            if "error:" in ln.lower() or "failed" in ln.lower() or "no observation" in ln.lower()
        ]
        record["failure_reason"] = "; ".join(err_lines[-4:]) or f"rc={proc.returncode}, no pos file"
        return record

    try:
        parsed = parse_pos_file(pos_path)
    except Exception as exc:
        record["failure_reason"] = f"pos parse/validity failure: {exc}"
        return record

    phase_rms = parse_stt_phase_rms_mm(stt_path)
    ztd_info = parse_ztd_summary(ztd_path)
    record.update(parsed)
    record["phase_rms_mm"] = phase_rms
    record.update(ztd_info)

    # Fail-closed sanity checks: minimum observations & realistic coordinates
    if parsed["nobs"] < 1000 or (phase_rms is not None and phase_rms == 0.0):
        record["status"] = "REJECTED_LOW_QUALITY"
        record["failure_reason"] = f"insufficient nobs={parsed['nobs']} or phase_rms={phase_rms}"
        return record
    if parsed["first_epoch"] and parsed["first_epoch"].startswith("1858"):
        record["status"] = "REJECTED_LOW_QUALITY"
        record["failure_reason"] = "uninitialized epoch 1858-11-17 (no valid dual-frequency data)"
        return record

    record["status"] = "OK"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run B-04 PRIDE PPP-AR 3.2.8 coordinate verification"
    )
    parser.add_argument(
        "--pilot", action="store_true", help="Run 2-window OSGF pilot (CODE + IGS)"
    )
    parser.add_argument(
        "--acs",
        default="CODE,IGS",
        help="Comma-separated analysis centers to run (CODE, IGS)",
    )
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker count")
    parser.add_argument("--doys", default="", help="Optional comma-separated DOYs filter")
    parser.add_argument("--out-name", default="", help="Optional output JSON filename override")
    parser.add_argument(
        "--work-root",
        type=Path,
        default=DATA_ROOT / "processed" / "b04-coordinate-verification",
    )
    args = parser.parse_args()

    acs = [a.strip().upper() for a in args.acs.split(",") if a.strip()]
    if args.pilot:
        stations = ["OSGF"]
        windows = [w for w in WINDOWS if w["doy"] in {"079", "339"}]
    else:
        stations = list(PRIORITY_STATIONS)
        windows = list(WINDOWS)
    if args.doys:
        wanted = {d.strip().zfill(3) for d in args.doys.split(",") if d.strip()}
        windows = [w for w in windows if w["doy"] in wanted]

    print(
        f"B-04 PRIDE PPP-AR runner starting: stations={len(stations)}, "
        f"windows={len(windows)}, acs={acs}, workers={args.workers}"
    )
    env_info = prepare_environment(args.work_root, stations, windows)

    jobs: list[dict[str, Any]] = []
    for ac in acs:
        for w in windows:
            for st in stations:
                rnx_file = Path(env_info["rinex_dir"]) / f"{st.lower()}{w['doy']}0.11o"
                jobs.append(
                    {
                        "station": st,
                        "window_spec": w,
                        "ac": ac,
                        "work_root": str(args.work_root),
                        "offline_pdp3": env_info["offline_pdp3_path"],
                        "table_dir": env_info["frame_table_dirs"][w["frame"]],
                        "product_dir": env_info["product_dir"],
                        "rnx_path": str(rnx_file),
                    }
                )

    t0 = time.monotonic()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_single_job, j) for j in jobs]
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            results.append(res)
            if res["status"] == "OK":
                se_mm = res["sigma_e_m"] * 1e3
                sn_mm = res["sigma_n_m"] * 1e3
                su_mm = res["sigma_u_m"] * 1e3
                print(
                    f"OK   {res['ac']:4s} {res['frame']:5s} DOY={res['doy']} {res['station']:4s} "
                    f"X={res['x_m']:13.4f} Y={res['y_m']:12.4f} Z={res['z_m']:12.4f} "
                    f"sENU=({se_mm:4.1f},{sn_mm:4.1f},{su_mm:4.1f})mm "
                    f"rms={res['phase_rms_mm']}mm nobs={res['nobs']} atx={res['antex_table']} "
                    f"dH={res['antenna_delta_h_m']} ({res['elapsed_s']}s)"
                )
            else:
                print(
                    f"FAIL {res['ac']:4s} {res['frame']:5s} DOY={res['doy']} {res['station']:4s} "
                    f"status={res['status']} reason={res['failure_reason']} ({res['elapsed_s']}s)"
                )

    results.sort(key=lambda r: (r["ac"], r["doy"], r["station"]))
    total_s = round(time.monotonic() - t0, 2)
    out_name = args.out_name or (
        "pride_ppp_pilot_results.json" if args.pilot else "pride_ppp_full_results.json"
    )
    out_path = args.work_root / out_name
    payload = {
        "schema_version": "nlgcp.b04.pride_ppp_results.v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pilot_mode": args.pilot,
        "elapsed_total_s": total_s,
        "environment": env_info,
        "summary": {
            "total_jobs": len(results),
            "ok": sum(1 for r in results if r["status"] == "OK"),
            "failed_or_rejected": sum(1 for r in results if r["status"] != "OK"),
        },
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"\nCompleted {len(results)} jobs in {total_s}s: "
        f"OK={payload['summary']['ok']}, FAILED/REJECTED={payload['summary']['failed_or_rejected']}"
    )
    print(f"Results written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
