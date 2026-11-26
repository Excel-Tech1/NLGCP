"""Phase 12 — Local loopback-only NTRIP correction distribution service.

This package implements a laboratory-only, loopback-bound (127.0.0.1) NTRIP
caster and client connecting the Phase 11 synthetic RTCM 1005/1074/1084
generation pipeline to authenticated local NTRIP clients.

SCIENTIFIC AND OPERATIONAL BOUNDARY:
All mountpoints and streams in this phase distribute synthetic laboratory
fixtures labelled:
  SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.
Transport success does not establish GNSS accuracy, RTK FIX, VRS approval,
commercial receiver interoperability, or operational readiness.
"""

from __future__ import annotations

SERVICE_VERSION = "0.1.0"
DEFAULT_MOUNTPOINT = "NLGCP_TEST"
EXPERIMENTAL_VRS_MOUNTPOINT = "NLGCP_VRS_EXP"
LOOPBACK_HOST = "127.0.0.1"
SYNTHETIC_MOUNTPOINT_LABEL = (
    "SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS."
)
EXPERIMENTAL_VRS_MOUNTPOINT_LABEL = (
    "EXPERIMENTAL VRS RESEARCH STREAM — NOT OPERATIONAL — "
    "NOT VALID FOR NAVIGATION OR OPERATIONAL POSITIONING."
)
SCIENTIFIC_READINESS_STATUS = (
    "NOT_VALID_SYNTHETIC_TEST_ONLY — "
    "NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS"
)
