package ntrip

import (
	"bytes"
	"encoding/base64"
	"strings"
	"testing"
)

func TestCRC24QReferenceVector(t *testing.T) {
	// Standard CRC-24Q check value for ASCII "123456789".
	if got := CRC24Q([]byte("123456789")); uint32(got) != 0xCDE703 {
		t.Fatalf("crc24q = %06x, want cde703", uint32(got))
	}
}

func TestVerifyFrameCRC(t *testing.T) {
	body := []byte{0xD3, 0x00, 0x02, 0x3E, 0x80, 0x00}
	crc := CRC24Q(body)
	good := []byte{byte(crc >> 16), byte(crc >> 8), byte(crc)}
	if !VerifyFrameCRC(body, good) {
		t.Fatal("valid CRC rejected")
	}
	bad := []byte{good[0] ^ 0x01, good[1], good[2]}
	if VerifyFrameCRC(body, bad) {
		t.Fatal("corrupt CRC accepted")
	}
	if VerifyFrameCRC(body, []byte{0x00, 0x01}) {
		t.Fatal("short CRC accepted")
	}
}

func encodeTestFrame(t *testing.T, message int, suffix []byte) []byte {
	t.Helper()
	head := []byte{byte(message >> 4), byte(message&0x0F) << 4}
	payload := append(head, suffix...)
	if len(payload) > MaxRTCMLen {
		t.Fatal("payload too long")
	}
	body := append([]byte{Preamble, byte(len(payload) >> 8), byte(len(payload))}, payload...)
	crc := CRC24Q(body)
	return append(body, byte(crc>>16), byte(crc>>8), byte(crc))
}

func testStream() []byte {
	var out []byte
	for _, msg := range []int{1005, 1077, 1087} {
		// Build frames directly to avoid t.Helper outside tests.
		head := []byte{byte(msg >> 4), byte(msg&0x0F) << 4}
		payload := append(head, 0x00, 0x01)
		body := append([]byte{Preamble, byte(len(payload) >> 8), byte(len(payload))}, payload...)
		crc := CRC24Q(body)
		out = append(out, body...)
		out = append(out, byte(crc>>16), byte(crc>>8), byte(crc))
	}
	return out
}

func TestFramerSplitAcrossSingleByteReads(t *testing.T) {
	data := testStream()
	framer, err := NewFramer(MaxRTCMLen)
	if err != nil {
		t.Fatal(err)
	}
	var frames []Frame
	for i := range data {
		frames = append(frames, framer.Feed(data[i:i+1])...)
	}
	if len(frames) != 3 {
		t.Fatalf("frames = %d, want 3", len(frames))
	}
	for _, frame := range frames {
		if !frame.CRCOK || frame.MessageNumber == nil {
			t.Fatalf("bad frame: %+v", frame)
		}
	}
	if *frames[0].MessageNumber != 1005 || *frames[1].MessageNumber != 1077 {
		t.Fatalf("message numbers = %d %d", *frames[0].MessageNumber, *frames[1].MessageNumber)
	}
	if frames[1].ByteOffset != int64(len(frames[0].Raw)) {
		t.Fatalf("offset = %d", frames[1].ByteOffset)
	}
}

func TestFramerMultipleFramesOneRead(t *testing.T) {
	framer, _ := NewFramer(MaxRTCMLen)
	frames := framer.Feed(testStream())
	if len(frames) != 3 {
		t.Fatalf("frames = %d, want 3", len(frames))
	}
}

func TestFramerCRCFailure(t *testing.T) {
	data := testStream()
	bad := append([]byte(nil), data...)
	bad[5] ^= 0x01
	framer, _ := NewFramer(MaxRTCMLen)
	frames := framer.Feed(bad)
	if len(frames) != 3 || frames[0].CRCOK {
		t.Fatalf("first frame crc state wrong: %+v", frames)
	}
	found := false
	for _, finding := range framer.Findings {
		found = found || strings.Contains(finding, "CRC_FAIL")
	}
	if !found {
		t.Fatalf("findings = %v", framer.Findings)
	}
}

func TestFramerStrayBytes(t *testing.T) {
	framer, _ := NewFramer(MaxRTCMLen)
	frames := framer.Feed(append([]byte{0x00, 0xFF}, testStream()...))
	if len(frames) != 3 || framer.StrayBytes != 2 {
		t.Fatalf("frames = %d stray = %d", len(frames), framer.StrayBytes)
	}
}

func TestFramerOversizeRefused(t *testing.T) {
	framer, err := NewFramer(10)
	if err != nil {
		t.Fatal(err)
	}
	header := []byte{Preamble, 0x03, 0xFF}
	if frames := framer.Feed(append(header, bytes.Repeat([]byte{0}, 32)...)); len(frames) != 0 {
		t.Fatalf("frames = %d, want 0", len(frames))
	}
	found := false
	for _, finding := range framer.Findings {
		found = found || strings.Contains(finding, "OVERSIZED_LENGTH")
	}
	if !found {
		t.Fatalf("findings = %v", framer.Findings)
	}
	if _, err := NewFramer(0); err == nil {
		t.Fatal("expected error for max_frame_length=0")
	}
}

func TestExtractMessageNumber(t *testing.T) {
	if msg := ExtractMessageNumber([]byte{0x3E, 0xD0}); msg == nil || *msg != 1005 {
		t.Fatalf("msg = %+v", msg)
	}
	if ExtractMessageNumber([]byte{0x3E}) != nil {
		t.Fatal("short payload must yield nil")
	}
}

func TestBasicAuthHeader(t *testing.T) {
	want := "Basic " + base64.StdEncoding.EncodeToString([]byte("user:s3cret"))
	if BasicAuthHeader("user", "s3cret") != want {
		t.Fatal("bad auth header")
	}
}

func TestRedaction(t *testing.T) {
	if redacted := RedactURL("http://user:s3cret@caster:2101/M"); strings.Contains(redacted, "s3cret") || !strings.Contains(redacted, "caster") {
		t.Fatalf("url = %q", redacted)
	}
	if redacted := RedactText("use s3cret now", []string{"s3cret"}); strings.Contains(redacted, "s3cret") {
		t.Fatalf("text = %q", redacted)
	}
	headers := RedactHeaders(map[string]string{"Authorization": "Basic abc", "Host": "caster"}, []string{"abc"})
	if headers["Authorization"] != Redacted || headers["Host"] != "caster" {
		t.Fatalf("headers = %v", headers)
	}
	clean := SanitizeMapping(map[string]string{"password": "s3cret", "host": "caster"})
	if clean["password"] != Redacted || clean["host"] != "caster" {
		t.Fatalf("mapping = %v", clean)
	}
}
