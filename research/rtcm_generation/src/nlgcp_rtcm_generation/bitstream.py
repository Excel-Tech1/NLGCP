"""Small deterministic bit writer used by the reference test encoder."""

from __future__ import annotations


class BitWriter:
    def __init__(self, *, max_bits: int = 8192) -> None:
        if max_bits < 1:
            raise ValueError("max_bits must be positive")
        self._max_bits = max_bits
        self._bits: list[int] = []

    @property
    def bit_length(self) -> int:
        return len(self._bits)

    def write_unsigned(self, value: int, bits: int) -> None:
        if bits < 1 or value < 0 or value >= (1 << bits):
            raise ValueError(f"unsigned value {value} does not fit {bits} bits")
        self._append([(value >> index) & 1 for index in range(bits - 1, -1, -1)])

    def write_signed(self, value: int, bits: int) -> None:
        minimum = -(1 << (bits - 1))
        maximum = (1 << (bits - 1)) - 1
        if bits < 1 or value < minimum or value > maximum:
            raise ValueError(f"signed value {value} does not fit {bits} bits")
        self.write_unsigned(value if value >= 0 else (1 << bits) + value, bits)

    def write_bytes(self, value: bytes) -> None:
        for byte in value:
            self.write_unsigned(byte, 8)

    def to_bytes(self) -> bytes:
        if self.bit_length % 8:
            self._append([0] * (8 - self.bit_length % 8))
        output = bytearray()
        for offset in range(0, len(self._bits), 8):
            byte = 0
            for bit in self._bits[offset : offset + 8]:
                byte = (byte << 1) | bit
            output.append(byte)
        return bytes(output)

    def _append(self, bits: list[int]) -> None:
        if len(self._bits) + len(bits) > self._max_bits:
            raise ValueError("bitstream exceeds configured maximum")
        self._bits.extend(bits)


class BitReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._position = 0

    def read_unsigned(self, bits: int) -> int:
        if bits < 1 or self._position + bits > len(self._data) * 8:
            raise ValueError("bitstream underflow")
        value = 0
        for _ in range(bits):
            byte = self._data[self._position // 8]
            value = (value << 1) | ((byte >> (7 - self._position % 8)) & 1)
            self._position += 1
        return value

    def read_signed(self, bits: int) -> int:
        value = self.read_unsigned(bits)
        return value - (1 << bits) if value & (1 << (bits - 1)) else value
