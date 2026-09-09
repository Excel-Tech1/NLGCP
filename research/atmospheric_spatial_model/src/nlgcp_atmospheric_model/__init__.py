"""NLGCP Phase 6 atmospheric & spatial error modelling package."""

from __future__ import annotations

__version__ = "6.1.0"

MIN_REFERENCE_STATIONS = 3
"""Triangle/polygon floor: spatial modelling needs >= 3 reference stations."""

MIN_REFS_FOR_LOOCV_FOLD = 2
"""Minimum remaining references for a leave-one-out fold to be admissible."""

PIPELINE_VERSION = "phase6-geometry-v3"
"""Bump when algorithm defaults change; invalidates fingerprinted products."""
