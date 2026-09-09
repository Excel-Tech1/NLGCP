"""CRC-24Q as used by RTCM 3.x transport framing.

Polynomial 0x1864CFB, initial value 0, no final XOR — the same
parameters RTKLIB's ``crc24q`` uses.  Convention (documented here so
real-caster interop can be audited later): the CRC is computed over the
full transport frame excluding the trailing 3 CRC bytes, i.e. preamble
+ 2 header bytes + payload.  Fixture encoder and stream validator share
this routine, so synthetic round-trips are self-consistent by
construction; compatibility with live caster captures must be
re-validated when authentic RTCM is acquired (currently BLOCKED).
"""

from __future__ import annotations

CRC24Q_POLY = 0x1864CFB
CRC24Q_MASK = 0xFFFFFF


def crc24q(data: bytes) -> int:
    """Compute CRC-24Q over ``data``."""
    crc = 0
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= CRC24Q_POLY
    return crc & CRC24Q_MASK


def crc24q_verify(frame_without_crc: bytes, crc_bytes: bytes) -> bool:
    """Check 3 trailing CRC bytes against the computed CRC-24Q."""
    if len(crc_bytes) != 3:
        return False
    expected = (crc_bytes[0] << 16) | (crc_bytes[1] << 8) | crc_bytes[2]
    return crc24q(frame_without_crc) == expected
