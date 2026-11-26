#!/usr/bin/env python3
"""Standalone CLI runner for NLGCP Research Archive (B-00)."""

from __future__ import annotations

import sys
from pathlib import Path

_ARCHIVE_SRC = Path(__file__).resolve().parents[1] / "research" / "research_archive" / "src"
if str(_ARCHIVE_SRC) not in sys.path:
    sys.path.insert(0, str(_ARCHIVE_SRC))

from nlgcp_research_archive.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
