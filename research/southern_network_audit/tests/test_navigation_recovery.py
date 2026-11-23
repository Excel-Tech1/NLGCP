"""Synthetic, offline tests for Southern Nigeria navigation recovery."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from nlgcp_southern_audit.archive_access import (
    ArchiveDownloader,
    Credentials,
    DownloadConfig,
    DownloadRequest,
    FetchResponse,
    TransportError,
)
from nlgcp_southern_audit.navigation_recovery import (
    STATUS_AUTHENTICATION_REQUIRED,
    STATUS_MISSING,
    STATUS_PARTIAL,
    STATUS_REJECTED,
    STATUS_SOURCE_UNAVAILABLE,
    STATUS_VALIDATED,
    ArchiveCandidate,
    RecoveryTarget,
    authentication_report,
    build_archive_candidates,
    date_for_doy,
    doy_for_date,
    load_recovery_targets,
    parse_navigation_filename,
    run_recovery,
    validate_navigation_bytes,
)

SYNTHETIC_NOTE = "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS"


def _header_line(body: str, label: str) -> str:
    return body.ljust(60)[:60] + label.ljust(20)


def _rinex2_payload(
    system: str,
    year: int,
    month: int,
    day: int,
    prns: Sequence[int],
    *,
    health: int = 0,
) -> bytes:
    version = "2.11" if system == "GPS" else "2.10"
    kind = "GPS NAV DATA" if system == "GPS" else "GLONASS NAV DATA"
    code = "N" if system == "GPS" else "G"
    lines = [
        _header_line(f"{version:>9}           {code}: {kind}", "RINEX VERSION / TYPE"),
        _header_line("", "END OF HEADER"),
    ]
    for prn in prns:
        lines.append(f"{prn:2d} {year % 100:2d} {month:2d} {day:2d}  0  0  0.0  0  4")
        if system == "GPS":
            lines.extend([" 0.0 0.0 0.0 0.0"] * 6)
            lines.append(f" 0.0 {health}.0 0.0 0.0")
        else:
            lines.append(f" 0.0 0.0 0.0 {health}.0")
            lines.extend([" 0.0 0.0 0.0 0.0"] * 2)
    return ("\n".join(lines) + "\n").encode("ascii")


def _rinex3_payload(
    year: int,
    month: int,
    day: int,
    satellites: Sequence[tuple[str, int]],
    *,
    health_ignored: int = 0,
) -> bytes:
    del health_ignored
    lines = [
        _header_line(
            "     3.03           N: GNSS NAV DATA    M: MIXED",
            "RINEX VERSION / TYPE",
        ),
        _header_line("", "END OF HEADER"),
    ]
    for system, prn in satellites:
        lines.append(f"{system}{prn:02d} {year} {month:02d} {day:02d} 00 00 00")
        record_length = 7 if system in {"G", "E", "C", "J"} else 3
        lines.extend([" 0.0 0.0 0.0 0.0"] * record_length)
    return ("\n".join(lines) + "\n").encode("ascii")


def _unix_compress(payload: bytes) -> bytes:
    executable = shutil.which("compress")
    if executable is None:
        pytest.skip("system compress utility is unavailable")
    result = subprocess.run(
        [executable, "-c"],
        input=payload,
        capture_output=True,
        check=True,
    )
    return result.stdout


def _target(
    *,
    date: str = "2011-03-20",
    required_systems: Sequence[str] = ("GPS", "GLONASS"),
    required_satellites: Sequence[str] = (),
) -> RecoveryTarget:
    return RecoveryTarget(
        date=date,
        year=int(date[:4]),
        doy=doy_for_date(date),
        network_id="CLBR+RUST+ULAG+UNEC",
        stations=("CLBR", "RUST", "ULAG", "UNEC"),
        target_stations=("CLBR", "RUST", "ULAG", "UNEC"),
        windows=(),
        required_systems=tuple(required_systems),
        required_satellites=tuple(required_satellites),
        source_files=(),
    )


def _candidate(
    *,
    filename: str,
    system: str = "GPS",
    rinex_version: str = "2",
    compression: str = "unix_compress",
    url: str = "https://example.test/nav",
) -> ArchiveCandidate:
    return ArchiveCandidate(
        target_date="2011-03-20",
        product_system=system,
        rinex_version=rinex_version,
        provider="BKG",
        candidate_source="synthetic",
        filename=filename,
        url=url,
        compression=compression,
        priority=0,
    )


def _write_audit(
    root: Path,
    *,
    stations: Sequence[str] = ("CLBR", "RUST", "ULAG", "UNEC"),
    dates: Sequence[str] = ("2011-03-20", "2011-03-21"),
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source_files = [
        f"NIGNET2011/{date}/{station}{doy_for_date(date):03d}0.11O"
        for date in dates
        for station in stations
    ]
    network_path = root / "network_temporal_coverage.csv"
    with network_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "network_id",
                "reference_stations",
                "target_station",
                "date",
                "start",
                "end",
                "time_system",
                "duration_s",
                "source_files",
                "overlap_status",
            ]
        )
        for date in dates:
            for target in stations:
                references = "+".join(
                    station for station in stations if station != target
                )
                date_sources = [
                    f"NIGNET2011/{date}/{station}{doy_for_date(date):03d}0.11O"
                    for station in stations
                ]
                writer.writerow(
                    [
                        "+".join(stations),
                        references,
                        target,
                        date,
                        f"{date}T00:00:00",
                        f"{date}T23:59:30",
                        "GPS",
                        "86370.0",
                        json.dumps(date_sources),
                        "COMMON_WINDOW_NOT_EPOCH_COUNT",
                    ]
                )
        writer.writerow(["DATASET_SUMMARY", "", "", "", "", "", "", "", "[]", ""])
    observation_path = root / "observation_coverage.csv"
    with observation_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["relative_path", "systems", "time_system"])
        for source in source_files:
            writer.writerow([source, '["MIXED"]', "GPS"])
    (root / "audit_summary.json").write_text(
        json.dumps(
            {
                "archive_path": "/synthetic/archive.zip",
                "station_count": 4,
                "data_label": SYNTHETIC_NOTE,
            }
        ),
        encoding="utf-8",
    )
    return root


def _constellation_evidence(root: Path, dates: Sequence[str]) -> Path:
    path = root / "candidate_observation_constellations.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "network_id",
                "date",
                "station",
                "file",
                "parse_status",
                "declared_time_system",
                "epoch_count",
                "satellite_ids_observed",
                "constellations_observed",
            ]
        )
        for date in dates:
            for station in ("CLBR", "RUST", "ULAG", "UNEC"):
                writer.writerow(
                    [
                        "CLBR+RUST+ULAG+UNEC",
                        date,
                        station,
                        "synthetic",
                        "PARSED",
                        "GPS",
                        "10",
                        "G01;G02;R01;R02",
                        "G;R",
                    ]
                )
    return path


@dataclass
class FakeTransport:
    responses: dict[str, list[FetchResponse | Exception]]
    calls: list[str] = field(default_factory=list)

    def fetch(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
        range_start: int | None = None,
    ) -> FetchResponse:
        del headers, timeout, range_start
        self.calls.append(url)
        values = self.responses.get(url)
        if not values:
            return FetchResponse(404, {"content-length": "9"}, b"not found", url)
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _response(
    status: int,
    body: bytes,
    *,
    headers: Mapping[str, str] | None = None,
    final_url: str = "https://example.test/nav",
) -> FetchResponse:
    response_headers = dict(headers or {})
    response_headers.setdefault("content-length", str(len(body)))
    return FetchResponse(status, response_headers, body, final_url)


def _fixed_clock() -> datetime:
    return datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)


def test_date_and_doy_conversion() -> None:
    assert doy_for_date("2011-01-01") == 1
    assert doy_for_date("2011-03-20") == 79
    assert doy_for_date("2011-12-31") == 365
    assert doy_for_date("2012-12-31") == 366
    assert date_for_doy(2011, 79) == "2011-03-20"
    assert date_for_doy(2012, 366) == "2012-12-31"
    with pytest.raises(ValueError):
        date_for_doy(2011, 366)
    with pytest.raises(ValueError):
        date_for_doy(2011, 0)
    with pytest.raises(ValueError):
        doy_for_date("2011-03-20T00:00:00")


def test_target_manifest_reads_audit_evidence(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path / "audit")
    inventory = load_recovery_targets(audit)
    assert len(inventory.targets) == 2
    assert inventory.selection["selected_network"] == "CLBR+RUST+ULAG+UNEC"
    first = inventory.targets[0]
    assert first.date == "2011-03-20"
    assert first.doy == 79
    assert first.stations == ("CLBR", "RUST", "ULAG", "UNEC")
    assert first.required_systems == ("GPS", "GLONASS")
    assert len(first.windows) == 1
    assert first.windows[0].duration_s == 86370.0
    evidence = _constellation_evidence(audit, ("2011-03-20", "2011-03-21"))
    with_evidence = load_recovery_targets(audit, constellation_evidence=evidence)
    assert "G01" in with_evidence.targets[0].required_satellites
    assert "R02" in with_evidence.targets[0].required_satellites
    secondary = load_recovery_targets(
        _write_audit(
            tmp_path / "audit-secondary",
            stations=("GEMB", "RUST", "ULAG", "UNEC"),
            dates=("2011-09-09",),
        ),
        include_secondary=True,
    )
    assert len(secondary.targets) == 1


def test_archive_candidates_are_documented_and_deterministic() -> None:
    target = _target()
    first = build_archive_candidates(target)
    second = build_archive_candidates(target)
    assert [candidate.to_json() for candidate in first] == [
        candidate.to_json() for candidate in second
    ]
    gps = [candidate for candidate in first if candidate.product_system == "GPS"]
    glonass = [
        candidate for candidate in first if candidate.product_system == "GLONASS"
    ]
    assert gps[0].url == (
        "https://cddis.nasa.gov/archive/gnss/data/daily/2011/079/11n/brdc0790.11n.Z"
    )
    assert gps[1].url == (
        "https://cddis.nasa.gov/archive/gnss/data/daily/2011/brdc/brdc0790.11n.Z"
    )
    assert any(
        candidate.url
        == "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2011/079/brdc0790.11n.Z"
        for candidate in gps
    )
    assert glonass[0].filename == "brdc0790.11g.Z"
    assert any(candidate.provider == "IGN" for candidate in gps)
    assert any(candidate.provider == "GSSC" for candidate in gps)
    sio = next(candidate for candidate in gps if candidate.provider == "SIO")
    assert sio.filename == "auto0790.11n.Z"
    rinex3 = [candidate for candidate in first if candidate.rinex_version == "3"]
    assert rinex3
    assert all(not candidate.applicable for candidate in rinex3)
    future_target = _target(date="2024-01-01")
    future = build_archive_candidates(future_target)
    assert any(
        candidate.rinex_version == "3" and candidate.applicable
        for candidate in future
    )


def test_filename_parsing_and_wrong_date_rejection() -> None:
    info = parse_navigation_filename("brdc0790.11n.Z")
    assert info is not None
    assert (info.year, info.doy, info.system, info.rinex_version) == (
        2011,
        79,
        "GPS",
        "2",
    )
    assert parse_navigation_filename("auto0790.11g.Z") is not None
    rinex3 = parse_navigation_filename("BRDC00IGS_R_20240790000_01D_MN.rnx.gz")
    assert rinex3 is not None
    assert (rinex3.year, rinex3.doy, rinex3.system) == (2024, 79, "MIXED")
    assert parse_navigation_filename("unrelated.txt") is None
    payload = _rinex2_payload("GPS", 2011, 3, 20, (1,))
    result = validate_navigation_bytes(
        _unix_compress(payload),
        _candidate(filename="brdc0800.11n.Z"),
        _target(),
    )
    assert result.status == STATUS_REJECTED
    assert "filename date" in result.reason
    wrong_day = _rinex2_payload("GPS", 2011, 3, 21, (1,))
    result = validate_navigation_bytes(
        _unix_compress(wrong_day),
        _candidate(filename="brdc0790.11n.Z"),
        _target(),
    )
    assert result.status == STATUS_REJECTED
    assert "NO_EXPECTED_DATE_EPHEMERIS" in result.rinex_validation_status


def test_rinex2_gps_glonass_health_and_satellite_coverage() -> None:
    gps_payload = _rinex2_payload("GPS", 2011, 3, 20, (1, 2), health=1)
    result = validate_navigation_bytes(
        _unix_compress(gps_payload),
        _candidate(filename="brdc0790.11n.Z"),
        _target(required_satellites=("G01", "G02")),
    )
    assert result.status == STATUS_VALIDATED
    assert result.satellites == ("G01", "G02")
    assert result.constellations == ("GPS",)
    assert result.health_nonzero_record_count == 2
    assert "NONZERO_HEALTH_FLAGS_PRESENT" in result.warnings
    partial = validate_navigation_bytes(
        _unix_compress(gps_payload),
        _candidate(filename="brdc0790.11n.Z"),
        _target(required_satellites=("G01", "G02", "G03")),
    )
    assert partial.status == STATUS_PARTIAL
    assert "MISSING_OBSERVED_SATELLITES" in partial.warnings[0]
    glonass_payload = _rinex2_payload("GLONASS", 2011, 3, 20, (1, 2))
    glonass = validate_navigation_bytes(
        _unix_compress(glonass_payload),
        _candidate(filename="brdc0790.11g.Z", system="GLONASS"),
        _target(required_satellites=("R01",)),
    )
    assert glonass.status == STATUS_VALIDATED
    assert glonass.constellations == ("GLONASS",)


def test_rinex3_merged_validation() -> None:
    payload = _rinex3_payload(2011, 3, 20, (("G", 1), ("R", 1)))
    target = _target(required_satellites=("G01", "R01"))
    candidate = _candidate(
        filename="BRDC00IGS_R_20110790000_01D_MN.rnx.gz",
        system="MIXED",
        rinex_version="3",
        compression="gzip",
    )
    result = validate_navigation_bytes(gzip.compress(payload), candidate, target)
    assert result.status == STATUS_VALIDATED
    assert result.satellites == ("G01", "R01")
    assert result.constellations == ("GLONASS", "GPS")
    assert "RINEX3_HEALTH_FIELDS_NOT_PARSED" in result.warnings
    wrong_date = validate_navigation_bytes(
        gzip.compress(payload),
        candidate,
        _target(date="2011-03-21", required_satellites=("G01", "R01")),
    )
    assert wrong_date.status == STATUS_REJECTED


def test_corrupt_compression_and_magic_mismatch() -> None:
    target = _target()
    gps_candidate = _candidate(filename="brdc0790.11n.Z")
    mismatch = validate_navigation_bytes(
        b"not compressed",
        gps_candidate,
        target,
    )
    assert mismatch.status == STATUS_REJECTED
    assert mismatch.compression_status == "MAGIC_MISMATCH"
    corrupt = validate_navigation_bytes(
        b"\x1f\x9d\x00\x00not-valid",
        gps_candidate,
        target,
    )
    assert corrupt.status == STATUS_REJECTED
    assert corrupt.compression_status == "CORRUPT"
    rinex3_candidate = _candidate(
        filename="BRDC00IGS_R_20110790000_01D_MN.rnx.gz",
        system="MIXED",
        rinex_version="3",
        compression="gzip",
    )
    bad_gzip = validate_navigation_bytes(
        b"\x1f\x8bnot-valid-gzip",
        rinex3_candidate,
        target,
    )
    assert bad_gzip.status == STATUS_REJECTED
    assert bad_gzip.compression_status == "CORRUPT"


def test_downloader_retries_resume_and_size_checks(tmp_path: Path) -> None:
    payload = _unix_compress(_rinex2_payload("GPS", 2011, 3, 20, (1,)))
    url = "https://example.test/brdc0790.11n.Z"
    request = DownloadRequest(
        url=url,
        filename="brdc0790.11n.Z",
        provider="BKG",
        requires_auth=False,
        expected_magic=(b"\x1f\x9d",),
    )
    transport = FakeTransport(
        {
            url: [
                _response(500, b"server error"),
                _response(200, payload),
            ]
        }
    )
    downloader = ArchiveDownloader(
        transport,
        DownloadConfig(max_retries=2, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    )
    outcome = downloader.download(request, tmp_path)
    assert outcome.status == "ACQUIRED"
    assert outcome.size_bytes == len(payload)
    assert outcome.sha256 == hashlib.sha256(payload).hexdigest()
    assert Path(outcome.stored_path).read_bytes() == payload
    assert len(transport.calls) == 2
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    partial_path = resume_dir / "brdc0791.11n.Z.part"
    partial_path.write_bytes(payload[:10])
    resume_request = DownloadRequest(
        url="https://example.test/brdc0791.11n.Z",
        filename="brdc0791.11n.Z",
        provider="BKG",
        requires_auth=False,
        expected_magic=(b"\x1f\x9d",),
    )
    resume_transport = FakeTransport(
        {
            resume_request.url: [
                _response(
                    206,
                    payload[10:],
                    headers={
                        "content-length": str(len(payload) - 10),
                        "content-range": f"bytes 10-{len(payload) - 1}/{len(payload)}",
                    },
                )
            ]
        }
    )
    resume_downloader = ArchiveDownloader(
        resume_transport,
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    )
    resumed = resume_downloader.download(resume_request, resume_dir)
    assert resumed.status == "ACQUIRED"
    assert Path(resumed.stored_path).read_bytes() == payload
    bad_length = FakeTransport(
        {
            "https://example.test/bad-length": [
                _response(200, payload, headers={"content-length": "9999"})
            ]
        }
    )
    bad_request = DownloadRequest(
        url="https://example.test/bad-length",
        filename="brdc0790.11n.Z",
        provider="BKG",
        requires_auth=False,
        expected_magic=(b"\x1f\x9d",),
    )
    bad_outcome = ArchiveDownloader(
        bad_length,
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    ).download(bad_request, tmp_path / "bad")
    assert bad_outcome.status == STATUS_REJECTED
    assert "content-length" in bad_outcome.error


def test_downloader_http_and_login_failures(tmp_path: Path) -> None:
    url = "https://cddis.nasa.gov/archive/gnss/data/daily/2011/079/11n/brdc0790.11n.Z"
    request = DownloadRequest(
        url=url,
        filename="brdc0790.11n.Z",
        provider="CDDIS",
        requires_auth=True,
        expected_magic=(b"\x1f\x9d",),
    )
    no_credentials = ArchiveDownloader(
        FakeTransport({}),
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    )
    outcome = no_credentials.download(request, tmp_path)
    assert outcome.status == STATUS_AUTHENTICATION_REQUIRED
    html = b"<!DOCTYPE html><html><body>Earthdata Login</body></html>"
    login_transport = FakeTransport(
        {url: [_response(200, html, headers={"content-type": "text/html"})]}
    )
    login = ArchiveDownloader(
        login_transport,
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(token="synthetic-token"),
        now=_fixed_clock,
    ).download(request, tmp_path / "login")
    assert login.status == STATUS_AUTHENTICATION_REQUIRED
    assert "HTML" in login.error
    public_request = DownloadRequest(
        url="https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2011/079/brdc0790.11n.Z",
        filename="brdc0790.11n.Z",
        provider="BKG",
        requires_auth=False,
        expected_magic=(b"\x1f\x9d",),
    )
    public_login = ArchiveDownloader(
        FakeTransport(
            {public_request.url: [_response(200, html, headers={"content-type": "text/html"})]}
        ),
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    ).download(public_request, tmp_path / "public-login")
    assert public_login.status == STATUS_REJECTED
    not_found = ArchiveDownloader(
        FakeTransport({}),
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    ).download(public_request, tmp_path / "not-found")
    assert not_found.status == STATUS_MISSING
    unauthorized = ArchiveDownloader(
        FakeTransport({public_request.url: [_response(401, b"denied")]}),
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    ).download(public_request, tmp_path / "unauthorized")
    assert unauthorized.status == STATUS_AUTHENTICATION_REQUIRED
    failing = ArchiveDownloader(
        FakeTransport(
            {
                public_request.url: [
                    TransportError("connection reset"),
                    TransportError("connection reset"),
                ]
            }
        ),
        DownloadConfig(max_retries=2, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    ).download(public_request, tmp_path / "failing")
    assert failing.status == STATUS_SOURCE_UNAVAILABLE
    zero = ArchiveDownloader(
        FakeTransport({public_request.url: [_response(200, b"")]}),
        DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        Credentials(),
        now=_fixed_clock,
    ).download(public_request, tmp_path / "zero")
    assert zero.status == STATUS_REJECTED


def test_credentials_and_authentication_report_are_secret_safe() -> None:
    credentials = Credentials(token="synthetic-secret-token")
    assert credentials.ready
    assert credentials.headers() == {
        "Authorization": "Bearer synthetic-secret-token"
    }
    assert "synthetic-secret-token" not in repr(credentials)
    report = authentication_report(credentials)
    assert report["cddis_credentials_configured"] is True
    assert "synthetic-secret-token" not in json.dumps(report)
    basic = Credentials(username="user", password="pass")
    assert basic.headers()["Authorization"].startswith("Basic ")
    assert not Credentials(username="user").ready


def test_source_fallback_manifest_and_checksums(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path / "audit", dates=("2011-03-20",))
    gps = _unix_compress(_rinex2_payload("GPS", 2011, 3, 20, (1, 2)))
    glonass = _unix_compress(_rinex2_payload("GLONASS", 2011, 3, 20, (1, 2)))
    transport = FakeTransport(
        {
            "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2011/079/brdc0790.11n.Z": [
                _response(200, gps)
            ],
            "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2011/079/brdc0790.11g.Z": [
                _response(200, glonass)
            ],
        }
    )
    summary = run_recovery(
        audit,
        tmp_path / "output",
        run_id="run-test",
        dry_run=False,
        workers=1,
        transport=transport,
        credentials=Credentials(),
        download_config=DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        now=_fixed_clock,
    )
    assert summary["overall_status"] == STATUS_VALIDATED
    run_dir = Path(str(summary["run_dir"]))
    manifest = json.loads((run_dir / "navigation_recovery_manifest.json").read_text())
    assert manifest["overall_status"] == STATUS_VALIDATED
    assert manifest["authentication"]["cddis_credentials_configured"] is False
    records = manifest["records"]
    assert len(records) == 2
    for record in records:
        assert record["recovery_status"] == STATUS_VALIDATED
        statuses = [attempt["recovery_status"] for attempt in record["attempts"]]
        assert STATUS_AUTHENTICATION_REQUIRED in statuses
        assert STATUS_VALIDATED in statuses
        best = record["best_attempt"]
        assert best["sha256"]
        stored = run_dir / best["stored_path"]
        assert hashlib.sha256(stored.read_bytes()).hexdigest() == best["sha256"]
    assert "synthetic-token" not in json.dumps(manifest)
    checksums = (run_dir / "sha256_manifest.txt").read_text()
    assert "navigation-products/validated/brdc0790.11n.Z" in checksums
    assert "navigation-products/validated/brdc0790.11g.Z" in checksums
    with (run_dir / "navigation_recovery_records.csv").open() as stream:
        assert "VALIDATED" in stream.read()


def test_partial_when_one_required_system_is_missing(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path / "audit", dates=("2011-03-20",))
    gps = _unix_compress(_rinex2_payload("GPS", 2011, 3, 20, (1,)))
    transport = FakeTransport(
        {
            "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2011/079/brdc0790.11n.Z": [
                _response(200, gps)
            ]
        }
    )
    summary = run_recovery(
        audit,
        tmp_path / "output",
        run_id="run-partial",
        dry_run=False,
        workers=1,
        transport=transport,
        credentials=Credentials(),
        download_config=DownloadConfig(max_retries=1, retry_backoff_seconds=0.0),
        now=_fixed_clock,
    )
    assert summary["overall_status"] == STATUS_PARTIAL
    run_dir = Path(str(summary["run_dir"]))
    manifest = json.loads((run_dir / "navigation_recovery_manifest.json").read_text())
    statuses = {
        record["product_system"]: record["recovery_status"]
        for record in manifest["records"]
    }
    assert statuses["GPS"] == STATUS_VALIDATED
    assert statuses["GLONASS"] == STATUS_MISSING


def test_dry_run_plan_writes_no_products(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path / "audit", dates=("2011-03-20",))
    transport = FakeTransport({})
    summary = run_recovery(
        audit,
        tmp_path / "output",
        run_id="run-dry",
        dry_run=True,
        transport=transport,
        now=_fixed_clock,
    )
    assert summary["dry_run"] is True
    run_dir = Path(str(summary["run_dir"]))
    assert (run_dir / "dry_run_plan.json").exists()
    assert (run_dir / "archive_candidates.csv").exists()
    assert not (run_dir / "navigation-products").exists()
    assert transport.calls == []
    plan = json.loads((run_dir / "dry_run_plan.json").read_text())
    assert plan["target_count"] == 1
    assert plan["candidate_count"] == len(plan["candidates"])


def test_reporting_is_deterministic_for_same_evidence(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path / "audit", dates=("2011-03-20",))
    first = run_recovery(
        audit,
        tmp_path / "output-a",
        run_id="run-deterministic",
        dry_run=True,
        now=_fixed_clock,
    )
    second = run_recovery(
        audit,
        tmp_path / "output-b",
        run_id="run-deterministic",
        dry_run=True,
        now=_fixed_clock,
    )
    first_dir = Path(str(first["run_dir"]))
    second_dir = Path(str(second["run_dir"]))
    assert (first_dir / "recovery_targets.json").read_bytes() == (
        second_dir / "recovery_targets.json"
    ).read_bytes()
    assert (first_dir / "archive_candidates.json").read_bytes() == (
        second_dir / "archive_candidates.json"
    ).read_bytes()


def test_target_selection_uses_maximum_date_network(tmp_path: Path) -> None:
    audit = _write_audit(
        tmp_path / "audit",
        dates=("2011-03-20", "2011-03-21", "2011-03-22"),
    )
    with (audit / "network_temporal_coverage.csv").open("a", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "GEMB+RUST+ULAG+UNEC",
                "GEMB+RUST+ULAG",
                "UNEC",
                "2011-09-09",
                "2011-09-09T00:00:00",
                "2011-09-09T23:59:30",
                "GPS",
                "86370.0",
                json.dumps(["NIGNET2011/2011-09-09/GEMB2520.11O"]),
                "COMMON_WINDOW_NOT_EPOCH_COUNT",
            ]
        )
    with (audit / "observation_coverage.csv").open("a", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "NIGNET2011/2011-09-09/GEMB2520.11O",
                '["MIXED"]',
                "GPS",
            ]
        )
    primary = load_recovery_targets(audit)
    assert len(primary.targets) == 3
    assert primary.selection["selected_network"] == "CLBR+RUST+ULAG+UNEC"
    all_candidates = load_recovery_targets(audit, include_secondary=True)
    assert len(all_candidates.targets) == 4
    assert {target.date for target in all_candidates.targets} == {
        "2011-03-20",
        "2011-03-21",
        "2011-03-22",
        "2011-09-09",
    }
