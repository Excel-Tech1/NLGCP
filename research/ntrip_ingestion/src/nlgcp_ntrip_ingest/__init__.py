"""NLGCP Phase 10 — live CORS / NTRIP ingestion (fail-closed transport).

Transport/acquisition phase only.  This package connects to an
*authorized* NTRIP caster, validates the HTTP/NTRIP handshake, frames
streaming RTCM 3.x with CRC-24Q integrity, preserves arrival timing,
and delivers the same ``CorrectionFrame`` downstream contract as
Phase 9 replay so consumers cannot tell live apart from replay.

Never invents RTCM messages, station coordinates, mountpoints,
credentials, frequencies, latency, accuracy, ambiguity fixes, or
positioning improvement.  Without an authorized reachable source,
``REAL LIVE INGESTION = BLOCKED`` is the accepted outcome.
"""

from __future__ import annotations

ENGINE_VERSION = "0.1.0"
LIVE_SCHEMA_VERSION = "1.0"
NTRIP_SCOPE = "NTRIP v2 primary, v1-compatible tolerance"

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"

BLOCKED_NO_SOURCE = "REAL LIVE INGESTION = BLOCKED"
