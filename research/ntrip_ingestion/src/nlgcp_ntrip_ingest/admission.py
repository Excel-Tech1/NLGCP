"""Mountpoint admission and station-identity mapping (fail-closed).

A mountpoint is not a station identity.  Ingestion requires an
explicit mapping from the provider mountpoint to a registry station;
unmapped sources stay ``STATION_IDENTITY_UNVERIFIED`` and are refused
for Phase 8 correction-source use (a labelled diagnostic raw capture
may still be permitted when authorization is clear).
"""

from __future__ import annotations

from nlgcp_ntrip_ingest.models import (
    AdmissionStatus,
    MountpointAdmission,
    NtripConfig,
    StationMapping,
)

try:
    from nlgcp_rtcm_replay.models import KNOWN_STATIONS as _KNOWN
except ImportError:  # pragma: no cover - package always present in repo
    _KNOWN = ()

KNOWN_STATIONS: tuple[str, ...] = tuple(_KNOWN)

STATION_IDENTITY_UNVERIFIED = "STATION_IDENTITY_UNVERIFIED"


def map_station(mountpoint: str, registry: dict[str, str]) -> StationMapping:
    """Map a provider mountpoint to a registry station identity."""
    key = mountpoint.lstrip("/").upper()
    for raw_mount, station in registry.items():
        if raw_mount.lstrip("/").upper() == key:
            verified = station in KNOWN_STATIONS
            reason = (
                "registry mapping to verified station"
                if verified
                else f"registry station not in verified set: {station}"
            )
            return StationMapping(
                mountpoint=mountpoint, station_id=station, verified=verified, reason=reason
            )
    return StationMapping(
        mountpoint=mountpoint,
        station_id=STATION_IDENTITY_UNVERIFIED,
        verified=False,
        reason="no registry mapping for mountpoint",
    )


def admit_mountpoint(
    *,
    provider: str,
    config: NtripConfig,
    source_table_format: str,
    gnss_systems: tuple[str, ...],
    requires_nmea: bool,
    needs_auth: bool,
    mapping: StationMapping,
) -> MountpointAdmission:
    """Create a mountpoint admission record before any ingestion."""
    reasons: list[str] = []
    if not config.host:
        reasons.append("CONFIG_INVALID: empty caster host")
    if not config.mountpoint:
        reasons.append("CONFIG_INVALID: empty mountpoint")
    if needs_auth and not config.username:
        reasons.append("AUTH_REQUIRED: stream requires authentication, no username configured")
    if requires_nmea and not config.gga_sentence:
        reasons.append("NMEA_POSITION_REQUIRED: stream requires GGA, none configured")
    if not mapping.verified:
        reasons.append(f"STATION_IDENTITY_UNVERIFIED: {mapping.reason}")
    if requires_nmea:
        reasons.append("WARN: stream requires periodic rover GGA")
    if config.allow_insecure_tls:
        reasons.append("WARN: insecure TLS explicitly enabled (diagnostic only, unsafe)")

    blocking = [r for r in reasons if not r.startswith("WARN")]
    if blocking:
        config_blocked = any(
            r.startswith("CONFIG_INVALID")
            or r.startswith("AUTH_REQUIRED")
            or "NMEA_POSITION_REQUIRED" in r
            for r in blocking
        )
        if config_blocked:
            status = AdmissionStatus.BLOCKED
        elif any("STATION_IDENTITY_UNVERIFIED" in r for r in blocking):
            status = AdmissionStatus.WARN
        else:
            status = AdmissionStatus.REJECT
    else:
        status = AdmissionStatus.ACCEPT if not reasons else AdmissionStatus.WARN

    auth_mode = "basic" if config.username else "none"
    configured = "configured" if config.username else "anonymous"
    return MountpointAdmission(
        provider=provider,
        caster_host=config.host,
        caster_port=config.port,
        mountpoint=config.mountpoint,
        station_mapping=mapping.station_id,
        source_table_format=source_table_format,
        gnss_systems=gnss_systems,
        requires_nmea=requires_nmea,
        authentication_mode=auth_mode,
        configured_authorization=configured,
        admission_status=status,
        reason_codes=tuple(reasons),
    )
