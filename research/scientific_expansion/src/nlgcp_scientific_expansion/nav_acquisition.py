"""Broadcast-navigation acquisition: planning, download, verification.

The three stages are separated so tests exercise planning and verification on
fixtures without network access. Only ``fetch_products`` touches the network.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import os
import re
import tempfile
import time
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from nlgcp_scientific_expansion.models import NavProductRecord

BKG_BRDC_TEMPLATE = (
    "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2024/{doy:03d}/"
    "BRDC00IGS_R_2024{doy:03d}0000_01D_MN.rnx.gz"
)
BKG_PROVIDER = "BKG/IGS"

_RINEX_NAV_EPOCH_RE = re.compile(
    r"(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+\d{1,2}\s+\d{1,2}\s+[\d.]+"
)


@dataclass(frozen=True)
class FetchConfig:
    """Bounded network behaviour for product downloads."""

    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_backoff_seconds: float = 5.0
    user_agent: str = "NLGCP-scientific-expansion/1.0 (research navigation fetch)"


def plan_products(
    doys: list[int],
    year: int,
    provider: str = BKG_PROVIDER,
    template: str = BKG_BRDC_TEMPLATE,
) -> list[NavProductRecord]:
    """Build a deterministic acquisition plan for candidate days."""
    plans: list[NavProductRecord] = []
    for doy in sorted(set(doys)):
        filename = f"BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"
        plans.append(
            NavProductRecord(
                year=year,
                doy=doy,
                provider=provider,
                source_url=template.format(doy=doy),
                product_type="BRDC_MERGED",
                expected_filename=filename,
                download_status="PLANNED",
            )
        )
    return plans


def filename_for_doy(year: int, doy: int) -> str:
    """Return the canonical merged-BRDC filename for a day."""
    return f"BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"


def fetch_products(
    plans: list[NavProductRecord],
    dest_dir: str,
    config: FetchConfig | None = None,
) -> list[NavProductRecord]:
    """Download planned products with retry, atomic rename, and SHA-256."""
    cfg = config or FetchConfig()
    os.makedirs(dest_dir, exist_ok=True)
    results: list[NavProductRecord] = []
    for plan in plans:
        results.append(_fetch_one(plan, dest_dir, cfg))
    return results


def _fetch_one(
    plan: NavProductRecord, dest_dir: str, config: FetchConfig
) -> NavProductRecord:
    dest_path = os.path.join(dest_dir, plan.expected_filename)
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        existing = _hash_file(dest_path)
        cached = replace(
            plan,
            stored_path=dest_path,
            sha256=existing,
            size_bytes=os.path.getsize(dest_path),
            download_status="CACHED",
            retrieval_utc=_utc_now(),
        )
        if verify_product(cached, plan.year, plan.doy).validation_status == "ACCEPTED":
            return cached
        # Keep the existing bytes until a replacement has been completely
        # downloaded and atomically renamed. A corrupt cache must not be
        # mistaken for a successful acquisition.
    last_error = ""
    http_status = 0
    for attempt in range(config.max_retries):
        try:
            request = urllib.request.Request(
                plan.source_url, headers={"User-Agent": config.user_agent}
            )
            with urllib.request.urlopen(
                request, timeout=config.timeout_seconds
            ) as response:
                http_status = int(response.getcode() or 0)
                with tempfile.NamedTemporaryFile(
                    delete=False, dir=dest_dir, prefix=".tmp-brdc-"
                ) as tmp:
                    tmp_path = tmp.name
                    digest = hashlib.sha256()
                    total = 0
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        digest.update(chunk)
                        total += len(chunk)
                        tmp.write(chunk)
            if total == 0:
                _safe_unlink(tmp_path)
                return replace(
                    plan,
                    download_status="REJECTED_ZERO_BYTES",
                    http_status=http_status,
                    retrieval_utc=_utc_now(),
                    validation_status="REJECTED",
                    validation_detail="zero-byte payload",
                )
            with open(tmp_path, "rb") as handle:
                prefix = handle.read(256)
            if _looks_like_error_page(prefix):
                _safe_unlink(tmp_path)
                return replace(
                    plan,
                    download_status="REJECTED_ERROR_PAGE",
                    http_status=http_status,
                    retrieval_utc=_utc_now(),
                    validation_status="REJECTED",
                    validation_detail="HTML/error payload instead of gzip",
                )
            os.replace(tmp_path, dest_path)
            return replace(
                plan,
                stored_path=dest_path,
                sha256=digest.hexdigest(),
                size_bytes=total,
                download_status="DOWNLOADED",
                http_status=http_status,
                retrieval_utc=_utc_now(),
            )
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            last_error = f"{type(exc).__name__}: {exc}"
            http_status = _extract_http_status(exc, http_status)
            if attempt + 1 < config.max_retries:
                time.sleep(config.retry_backoff_seconds * (attempt + 1))
    return replace(
        plan,
        download_status="BLOCKED",
        http_status=http_status,
        retrieval_utc=_utc_now(),
        validation_status="BLOCKED",
        validation_detail=last_error[:300],
    )


def verify_product(record: NavProductRecord, year: int, doy: int) -> NavProductRecord:
    """Validate a stored product: gzip, RINEX header, day match, ephemerides."""
    if not record.stored_path or not os.path.exists(record.stored_path):
        return replace(
            record,
            validation_status="REJECTED",
            validation_detail="stored file missing",
        )
    record = replace(
        record,
        sha256=_hash_file(record.stored_path),
        size_bytes=os.path.getsize(record.stored_path),
    )
    try:
        with gzip.open(record.stored_path, "rt", encoding="utf-8", errors="replace") as handle:
            header_lines: list[str] = []
            header_done = False
            for _ in range(100):
                line = handle.readline()
                if not line:
                    break
                header_lines.append(line)
                if "END OF HEADER" in line:
                    header_done = True
                    break
            epoch_count = 0
            mismatched_days = 0
            total_lines = len(header_lines)
            body = handle if header_done else iter(header_lines)
            for line in body:
                total_lines += 1
                match = _RINEX_NAV_EPOCH_RE.search(line)
                if match:
                    epoch_count += 1
                    file_year = int(match.group(1))
                    file_doy = _ymd_to_doy(
                        file_year, int(match.group(2)), int(match.group(3))
                    )
                    if file_year != year or file_doy != doy:
                        mismatched_days += 1
                if total_lines > 400000:
                    break
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        return replace(
            record,
            validation_status="REJECTED",
            validation_detail=f"archive integrity failure: {type(exc).__name__}",
        )
    header_text = "".join(header_lines)
    if "RINEX VERSION" not in header_text and "RINEX" not in header_text[:400]:
        return replace(
            record,
            validation_status="REJECTED",
            validation_detail="missing RINEX header",
        )
    if epoch_count == 0:
        return replace(
            record,
            validation_status="REJECTED",
            validation_detail="zero ephemeris records",
        )
    if mismatched_days > epoch_count // 2:
        return replace(
            record,
            validation_status="REJECTED",
            validation_detail=(
                f"date mismatch: {mismatched_days}/{epoch_count} "
                f"epochs outside {year}/{doy:03d}"
            ),
        )
    detail = f"epochs={epoch_count} mismatched_days={mismatched_days}"
    return replace(
        record,
        validation_status="ACCEPTED",
        validation_detail=detail,
        ephemeris_records=epoch_count,
    )


def _looks_like_error_page(prefix: bytes) -> bool:
    lowered = prefix[:200].lower()
    return lowered.startswith(b"<html") or lowered.startswith(b"<!doctype html")


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_unlink(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_http_status(exc: BaseException, default: int) -> int:
    code = getattr(exc, "code", None)
    try:
        return int(code) if code is not None else default
    except (TypeError, ValueError):
        return default


def _ymd_to_doy(year: int, month: int, day: int) -> int:
    from datetime import date

    return (date(year, month, day) - date(year, 1, 1)).days + 1
