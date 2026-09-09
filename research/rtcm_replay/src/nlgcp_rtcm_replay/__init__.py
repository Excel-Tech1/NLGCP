"""NLGCP Phase 9 — recorded RTCM replay (offline deterministic transport).

Transport/replay phase only.  This package parses RTCM 3.x framing,
builds deterministic replay timelines, and replays correction frames to
a stable consumer contract.  It never recalculates Phase 8 scientific
decisions, never claims positioning accuracy, and never manufactures
real-data success: sources without authentic capture provenance are
BLOCKED for real pilots and only clearly labelled synthetic fixtures
may be used for framework tests.
"""

from __future__ import annotations

ENGINE_VERSION = "0.1.0"
REPLAY_SCHEMA_VERSION = "1.0"
PARSER_VERSION = "1.0"

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"
