"""Core records for the interim scientific-expansion sprint.

All records are plain data carriers. Scientific admission decisions live in
``catalog.py``; these models never fabricate availability.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StationDayCoverage:
    """One station-day cell of the observation/nav/QC coverage matrix."""

    station_id: str
    year: int
    doy: int
    observation_available: bool = False
    observation_path: str = ""
    observation_sha256: str = ""
    qc_classification: str = "UNKNOWN"
    qc_findings: tuple[str, ...] = ()
    availability_percent: float = 0.0
    epochs_observed: int = 0
    navigation_available: bool = False
    navigation_product: str = ""
    coordinate_eligible: bool = False
    processable_single_base: bool = False
    block_reason: str = ""


@dataclass(frozen=True)
class OverlapDay:
    """One calendar day's multi-station overlap summary."""

    year: int
    doy: int
    stations: tuple[str, ...]
    station_count: int = 0
    candidate_experiment_type: str = "NONE"
    full_session_stations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "station_count", len(self.stations))


@dataclass(frozen=True)
class NavProductRecord:
    """Provenance record for one broadcast-navigation product file."""

    year: int
    doy: int
    provider: str = ""
    source_url: str = ""
    product_type: str = "BRDC_MERGED"
    expected_filename: str = ""
    stored_path: str = ""
    sha256: str = ""
    size_bytes: int = 0
    download_status: str = "NOT_REQUESTED"
    http_status: int = 0
    retrieval_utc: str = ""
    validation_status: str = "UNVALIDATED"
    validation_detail: str = ""
    ephemeris_records: int = 0


@dataclass(frozen=True)
class ProcessableDay:
    """Admission verdict for one calendar day."""

    year: int
    doy: int
    stations: tuple[str, ...] = ()
    station_count: int = 0
    nav_product: str = ""
    single_base_possible: bool = False
    single_base_pairs: tuple[tuple[str, str], ...] = ()
    network_possible: bool = False
    network_references: tuple[str, ...] = ()
    phase6_loocv_possible: bool = False
    reason_if_blocked: str = ""
    priority_score: float = 0.0
    selection_reason: str = ""


@dataclass(frozen=True)
class BatchManifest:
    """Reproducibility envelope for one batch run."""

    batch_id: str
    batch_type: str = ""
    input_manifest_fingerprint: str = ""
    config_fingerprint: str = ""
    software_commit: str = ""
    software_dirty: bool = True
    rtklib_version: str = ""
    rtklib_sha256: str = ""
    data_root: str = ""
    utc_execution_time: str = ""
    worker_count: int = 1
    experiment_ids: tuple[str, ...] = ()
    extra: dict[str, str] = field(default_factory=dict)
