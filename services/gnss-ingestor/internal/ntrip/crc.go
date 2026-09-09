package ntrip

// CRC-24Q as used by RTCM 3.x transport framing: polynomial 0x1864CFB,
// initial value 0, no final XOR. The CRC covers preamble + 2 header
// bytes + payload (the RTKLIB-compatible convention shared with the
// Phase 9 Python replay package).
const (
	crc24QPoly = 0x1864CFB
	crc24QMask = 0xFFFFFF
)

// CRC24Q computes CRC-24Q over data.
func CRC24Q(data []byte) CRC {
	var crc uint32
	for _, b := range data {
		crc ^= uint32(b) << 16
		for range 8 {
			crc <<= 1
			if crc&0x1000000 != 0 {
				crc ^= crc24QPoly
			}
		}
	}
	return CRC(crc & crc24QMask)
}

// CRC is a 24-bit CRC-24Q value.
type CRC uint32

// VerifyFrameCRC checks the 3 trailing CRC bytes of a full transport
// frame (body = preamble + header + payload, crc = trailing 3 bytes).
func VerifyFrameCRC(body, crcBytes []byte) bool {
	if len(crcBytes) != 3 {
		return false
	}
	expected := uint32(crcBytes[0])<<16 | uint32(crcBytes[1])<<8 | uint32(crcBytes[2])
	return uint32(CRC24Q(body)) == expected
}
