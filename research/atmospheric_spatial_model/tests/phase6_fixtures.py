"""Synthetic-only fixtures for Phase 6 tests.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

HEADER_TEMPLATE = """     2.11           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE
synthetic test fixture - not scientific data                PGM / RUN BY / DATE
PHXX                                                        MARKER NAME
{approx_line}
{types_padded}
{interval_line}
{first_obs_line}
                                                            END OF HEADER
"""


def _labelled(content: str, label: str) -> str:
    return content.ljust(60) + label


def types_line(codes: list[str]) -> str:
    body = f"{len(codes):6d}" + "".join(f"{c:>6s}" for c in codes)
    return body


def epoch_line(
    *,
    minute: int,
    second: float = 0.0,
    flag: int = 0,
    sats: list[str],
) -> str:
    head = f"{24:3d}{1:3d}{26:3d}{0:3d}{minute:3d}{second:11.7f}{flag:3d}{len(sats):3d}"
    first = sats[:12]
    rest = sats[12:]
    lines = [head + "".join(f"{s:>3s}" for s in first)]
    for k in range(0, len(rest), 12):
        lines.append(" " * 32 + "".join(f"{s:>3s}" for s in rest[k : k + 12]))
    return "\n".join(lines)


def obs_line(values: list[float | None], *, lli: int = 0) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            parts.append(" " * 16)
        else:
            parts.append(f"{value:14.3f}{lli:1d} ")
    text = "".join(parts)
    lines: list[str] = []
    for k in range(0, len(text), 80):
        lines.append(text[k : k + 80])
    return "\n".join(lines)


def write_rinex2(
    path: Path,
    *,
    codes: list[str] | None = None,
    epochs: int = 4,
    sats: list[str] | None = None,
    l1_base: float = 1_000_000.0,
    l2_base: float = 800_000.0,
    gap_at: int | None = None,
    lli_at: int | None = None,
    approx: str = "  6308877.8699   772267.5163   530082.6335",
) -> Path:
    """Write a deterministic synthetic RINEX 2 observation file."""
    codes = codes or ["L1", "L2", "C1", "P1"]
    sats = sats or ["G01", "G02"]
    approx_line = _labelled(approx, "APPROX POSITION XYZ")
    types_padded = _labelled(types_line(codes), "# / TYPES OF OBSERV")
    interval_line = _labelled("    30.0000", "INTERVAL")
    first_obs_line = _labelled(
        f"{24:6d}{1:6d}{26:6d}{0:6d}{0:6d}{0.0:13.7f}", "TIME OF FIRST OBS"
    )
    lines = [HEADER_TEMPLATE.format(
        approx_line=approx_line,
        types_padded=types_padded,
        interval_line=interval_line,
        first_obs_line=first_obs_line,
    )]
    for index in range(epochs):
        if gap_at is not None and index == gap_at:
            continue
        total_seconds = index * 30
        lines.append(epoch_line(
            minute=(total_seconds // 60) % 60,
            second=float(total_seconds % 60),
            sats=sats,
        ))
        for sat in sats:
            drift = float(index) * 10.0
            plain: list[float] = [
                l1_base + drift,
                l2_base + drift * 0.8,
                20_000_000.0 + drift,
                20_000_001.0 + drift,
            ]
            drifted: list[float | None] = [v for v in plain[: len(codes)]]
            flag = 1 if (lli_at == index and sat == sats[0]) else 0
            lines.append(obs_line(drifted, lli=flag))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def synthetic_nav_text() -> str:
    """Minimal synthetic RINEX 3 GPS nav block (layout matches the parser)."""

    def fmt(values: list[float]) -> str:
        return "".join(f"{v:19.12E}".replace("E", "D") for v in values)

    header = (
        "     3.04           N: GNSS NAV DATA    M: MIXED            RINEX VERSION / TYPE\n"
        "synthetic - not scientific data                            PGM / RUN BY / DATE\n"
        "                                                            END OF HEADER\n"
    )
    a = 26_560_000.0
    sqrt_a = a**0.5
    body = (
        "G01 2024 01 26 00 00 00  0.000000000000D+00  0.000000000000D+00  0.000000000000D+00\n"
        + "   " + fmt([1.0, 0.0, 0.0, 0.0]) + "\n"  # IODE Crs dN M0
        + "   " + fmt([0.0, 0.0, 0.0, sqrt_a]) + "\n"  # Cuc e Cus sqrtA
        + "   " + fmt([0.0, 0.0, 0.0, 0.0]) + "\n"  # Toe Cic OMEGA CIS
        + "   " + fmt([0.9599310886, 0.0, 0.0, 0.0]) + "\n"  # i0 Crc omega OMEGADOT
        + "   " + fmt([0.0, 1.0, 2298.0, 0.0]) + "\n"  # IDOT codes week L2P
        + "   " + fmt([0.0, 0.0, 0.0, 0.0]) + "\n"
        + "   " + fmt([432000.0, 4.0, 0.0, 0.0]) + "\n"
    )
    return header + body
