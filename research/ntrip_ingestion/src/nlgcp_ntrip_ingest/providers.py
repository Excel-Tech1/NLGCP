"""Source-independent Nigerian CORS provider registry and Stage B gate (Milestone B-09).

Implements ADR-001 (source-independent GNSS ingestion) and ADR-011 (fail-closed
integrity). Catalogues known Nigerian CORS networks honestly without fabricating
IP addresses, mountpoints, or credentials.

Stage A (credential-free recorded RTCM and local loopback ingestion) is executable
offline. Stage B (live external CORS ingestion) remains strictly
``BLOCKED_EXTERNAL_ACCESS`` unless explicit operator authorization and runtime
credentials are supplied via environment variables (never committed to Git).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ProviderAccessTier(StrEnum):
    LOCAL_LAB_STAGE_A = "LOCAL_LAB_STAGE_A"
    PUBLIC_INSTITUTIONAL = "PUBLIC_INSTITUTIONAL"
    COMMERCIAL_SUBSCRIPTION = "COMMERCIAL_SUBSCRIPTION"
    COMMERCIAL_MARKETPLACE = "COMMERCIAL_MARKETPLACE"


class StageBStatus(StrEnum):
    STAGE_A_AVAILABLE_OFFLINE = "STAGE_A_AVAILABLE_OFFLINE"
    BLOCKED_EXTERNAL_ACCESS = "BLOCKED_EXTERNAL_ACCESS"
    AUTHORIZED_READY_FOR_PROBE = "AUTHORIZED_READY_FOR_PROBE"


@dataclass(frozen=True, slots=True)
class CorsProviderProfile:
    """Metadata and access-policy record for one CORS provider."""

    provider_code: str
    provider_name: str
    operator_name: str
    country: str
    website_url: str | None
    access_tier: ProviderAccessTier
    requires_account_credentials: bool
    default_tls_required: bool
    known_coverage_notes: str
    expected_protocol: str
    stage_b_default_status: StageBStatus
    contact_or_onboarding_path: str
    env_prefix: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["access_tier"] = str(self.access_tier)
        payload["stage_b_default_status"] = str(self.stage_b_default_status)
        return payload


NIGERIAN_CORS_PROVIDERS: tuple[CorsProviderProfile, ...] = (
    CorsProviderProfile(
        provider_code="NLGCP_LOCAL_STAGE_A",
        provider_name="NLGCP Local Recorded / Loopback Lab Source",
        operator_name="NLGCP Engineering Team",
        country="NG",
        website_url=None,
        access_tier=ProviderAccessTier.LOCAL_LAB_STAGE_A,
        requires_account_credentials=False,
        default_tls_required=False,
        known_coverage_notes=(
            "Offline recorded RTCM 3.x streams and 127.0.0.1 loopback NTRIP lab caster "
            "for Stage A ingestion testing; never substitutes for live CORS validation."
        ),
        expected_protocol="Recorded RTCM 3.x / NTRIP v2.0 & v1.0 (127.0.0.1)",
        stage_b_default_status=StageBStatus.STAGE_A_AVAILABLE_OFFLINE,
        contact_or_onboarding_path="Local workspace / ${NLGCP_DATA_ROOT}",
        env_prefix=None,
    ),
    CorsProviderProfile(
        provider_code="SOGPOS_SACREDION",
        provider_name="SOGPOS (Sacredion Online GNSS Positioning Service)",
        operator_name="Sacredion Nigeria Limited (with Tersus GNSS)",
        country="NG",
        website_url="https://www.sacredioncors.com/",
        access_tier=ProviderAccessTier.COMMERCIAL_SUBSCRIPTION,
        requires_account_credentials=True,
        default_tls_required=True,
        known_coverage_notes=(
            "Commercial multi-state Nigerian CORS network reported across Lagos, "
            "Benin City, Port Harcourt, Warri, Jos, Osun, and Minna. Specific caster "
            "host/port/mountpoints and credentials are issued only to subscribed users."
        ),
        expected_protocol="NTRIP v1/v2 over TCP (standard port 2101; TLS preferred if supported)",
        stage_b_default_status=StageBStatus.BLOCKED_EXTERNAL_ACCESS,
        contact_or_onboarding_path=(
            "Commercial subscription via https://www.sacredioncors.com/ "
            "(info@sacredioncors.com / admin@sacredioncors.com)"
        ),
        env_prefix="NLGCP_SOGPOS",
    ),
    CorsProviderProfile(
        provider_code="NIGNET_OSGOF",
        provider_name="NIGNET (Nigerian Permanent GNSS Reference Network)",
        operator_name="Office of the Surveyor General of the Federation (OSGoF)",
        country="NG",
        website_url="https://osgof.gov.ng/",
        access_tier=ProviderAccessTier.PUBLIC_INSTITUTIONAL,
        requires_account_credentials=True,
        default_tls_required=True,
        known_coverage_notes=(
            "National geodetic reference backbone (historical 2011/2024 RINEX archived "
            "and coordinate-verified in B-04). Public unauthenticated real-time NTRIP "
            "caster endpoint is not exposed; formal OSGoF authorization is required."
        ),
        expected_protocol="NTRIP v1/v2 (institutional authorization required)",
        stage_b_default_status=StageBStatus.BLOCKED_EXTERNAL_ACCESS,
        contact_or_onboarding_path="Formal institutional request to OSGoF Geodesy Department",
        env_prefix="NLGCP_NIGNET",
    ),
    CorsProviderProfile(
        provider_code="CORSLOCATE_NG",
        provider_name="CORSLocate Nigeria CORS Marketplace",
        operator_name="Pink Project NG Ltd",
        country="NG",
        website_url="https://corslocate.ng/",
        access_tier=ProviderAccessTier.COMMERCIAL_MARKETPLACE,
        requires_account_credentials=True,
        default_tls_required=True,
        known_coverage_notes=(
            "Commercial Nigerian CORS aggregator/marketplace focused on Lagos and "
            "multi-operator access; NTRIP credentials provisioned per paid subscription."
        ),
        expected_protocol="NTRIP v1/v2 (commercial subscription credentials required)",
        stage_b_default_status=StageBStatus.BLOCKED_EXTERNAL_ACCESS,
        contact_or_onboarding_path="Commercial subscription via https://corslocate.ng/",
        env_prefix="NLGCP_CORSLOCATE",
    ),
)


def get_provider_profile(provider_code: str) -> CorsProviderProfile:
    key = provider_code.strip().upper()
    for profile in NIGERIAN_CORS_PROVIDERS:
        if profile.provider_code == key:
            return profile
    raise KeyError(f"unknown CORS provider code: {provider_code!r}")


@dataclass(frozen=True, slots=True)
class StageBGateAssessment:
    """Fail-closed authorization and credential preflight result for Stage B live access."""

    provider_code: str
    status: StageBStatus
    external_connection_permitted: bool
    missing_prerequisites: tuple[str, ...]
    checked_env_vars: tuple[str, ...]
    notes: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = str(self.status)
        payload["missing_prerequisites"] = list(self.missing_prerequisites)
        payload["checked_env_vars"] = list(self.checked_env_vars)
        return payload


def evaluate_stage_b_provider_gate(
    provider_code: str,
    *,
    env: Mapping[str, str] | None = None,
) -> StageBGateAssessment:
    """Check whether Stage B live access is authorized without ever logging secrets."""
    profile = get_provider_profile(provider_code)
    if profile.access_tier == ProviderAccessTier.LOCAL_LAB_STAGE_A:
        return StageBGateAssessment(
            provider_code=profile.provider_code,
            status=StageBStatus.STAGE_A_AVAILABLE_OFFLINE,
            external_connection_permitted=False,
            missing_prerequisites=(),
            checked_env_vars=(),
            notes="Stage A local recorded/loopback mode only; no external internet host dialed.",
        )

    source = os.environ if env is None else env
    prefix = profile.env_prefix or "NLGCP_NTRIP"
    required_vars = (
        f"{prefix}_HOST",
        f"{prefix}_PORT",
        f"{prefix}_MOUNTPOINT",
        f"{prefix}_USERNAME",
        f"{prefix}_PASSWORD",
        f"{prefix}_AUTHORIZATION_BASIS",
    )
    missing = tuple(var for var in required_vars if not source.get(var, "").strip())
    if missing:
        return StageBGateAssessment(
            provider_code=profile.provider_code,
            status=StageBStatus.BLOCKED_EXTERNAL_ACCESS,
            external_connection_permitted=False,
            missing_prerequisites=missing,
            checked_env_vars=required_vars,
            notes=(
                f"Stage B live ingestion for {profile.provider_name} is BLOCKED_EXTERNAL_ACCESS: "
                "authorized host/mountpoint/credentials and written authorization basis are not "
                "configured. Never fabricate credentials or probe unauthorized endpoints."
            ),
        )
    return StageBGateAssessment(
        provider_code=profile.provider_code,
        status=StageBStatus.AUTHORIZED_READY_FOR_PROBE,
        external_connection_permitted=True,
        missing_prerequisites=(),
        checked_env_vars=required_vars,
        notes=(
            f"All required non-empty environment variables present for {profile.provider_code}; "
            "explicit operator probe authorization required before connecting."
        ),
    )
