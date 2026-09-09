package ntrip

// RTCM 3.x transport constants: 0xD3 preamble, 2 header bytes carrying
// 6 reserved bits + 10-bit payload length, 3-byte CRC-24Q trailer.
const (
	Preamble     = 0xD3
	HeaderLength = 3
	CRCLength    = 3
	MaxRTCMLen   = 1023
)

// Frame is one validated transport frame with its global byte offset.
type Frame struct {
	ByteOffset    int64
	Raw           []byte
	MessageNumber *int
	CRCOK         bool
	SHA256        [32]byte
}

// Framer incrementally parses RTCM 3.x over arbitrary TCP chunk
// boundaries: split frames are buffered, multiple frames per read are
// all emitted, and no whole live stream is ever held in memory.
type Framer struct {
	maxFrameLength int
	buffer         []byte
	byteOffset     int64
	pendingStray   int
	Findings       []string
	StrayBytes     int
}

// NewFramer returns a streaming framer bounded by maxFrameLength (1..1023).
func NewFramer(maxFrameLength int) (*Framer, error) {
	if maxFrameLength < 1 || maxFrameLength > MaxRTCMLen {
		return nil, &ConfigError{Field: "max_frame_length"}
	}
	return &Framer{maxFrameLength: maxFrameLength}, nil
}

// PendingBytes reports bytes buffered awaiting a complete frame.
func (f *Framer) PendingBytes() int { return len(f.buffer) }

// Feed consumes one TCP read and returns zero or more complete frames.
func (f *Framer) Feed(chunk []byte) []Frame {
	f.buffer = append(f.buffer, chunk...)
	var frames []Frame
	skipped := f.pendingStray
	f.pendingStray = 0
	for {
		if len(f.buffer) == 0 {
			break
		}
		if f.buffer[0] != Preamble {
			skipped++
			f.buffer = f.buffer[1:]
			f.byteOffset++
			continue
		}
		if len(f.buffer) < HeaderLength {
			break
		}
		length := int(f.buffer[1]&0x03)<<8 | int(f.buffer[2])
		if length > f.maxFrameLength {
			f.Findings = append(f.Findings, itoa("OVERSIZED_LENGTH offset=", f.byteOffset, length))
			skipped++
			f.buffer = f.buffer[1:]
			f.byteOffset++
			continue
		}
		need := HeaderLength + length + CRCLength
		if len(f.buffer) < need {
			f.pendingStray = skipped
			break
		}
		raw := append([]byte(nil), f.buffer[:need]...)
		body, crcBytes := raw[:need-CRCLength], raw[need-CRCLength:]
		crcOK := VerifyFrameCRC(body, crcBytes)
		var payload []byte
		if length > 0 {
			payload = raw[HeaderLength : need-CRCLength]
		}
		msg := ExtractMessageNumber(payload)
		if skipped > 0 {
			f.StrayBytes += skipped
			f.Findings = append(f.Findings, itoa("STRAY_BYTES skipped=", int64(skipped), 0)+itoa(" next_offset=", f.byteOffset, 0))
			skipped = 0
		}
		frames = append(frames, Frame{
			ByteOffset:    f.byteOffset,
			Raw:           raw,
			MessageNumber: msg,
			CRCOK:         crcOK,
			SHA256:        SHA256Sum(raw),
		})
		if !crcOK {
			f.Findings = append(f.Findings, itoa("CRC_FAIL offset=", f.byteOffset, length))
		}
		f.buffer = f.buffer[need:]
		f.byteOffset += int64(need)
	}
	if skipped > 0 {
		f.StrayBytes += skipped
		f.Findings = append(f.Findings, itoa("STRAY_BYTES skipped=", int64(skipped), 0))
	}
	return frames
}

// ExtractMessageNumber returns the 12-bit RTCM message number where
// technically valid (payload of at least 2 bytes), else nil.
func ExtractMessageNumber(payload []byte) *int {
	if len(payload) < 2 {
		return nil
	}
	msg := (int(payload[0]) << 4) | ((int(payload[1]) >> 4) & 0xFFF)
	return &msg
}
