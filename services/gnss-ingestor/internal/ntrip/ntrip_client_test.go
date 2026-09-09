package ntrip

import (
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// fakeCaster is a deterministic local NTRIP stand-in (no internet).
type fakeCaster struct {
	listener net.Listener
	scenario string
	payload  []byte
	user     string
	password string
}

func startFakeCaster(t *testing.T, scenario string, payload []byte) *fakeCaster {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	caster := &fakeCaster{listener: listener, scenario: scenario, payload: payload}
	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go caster.handle(conn)
		}
	}()
	t.Cleanup(func() { _ = listener.Close() })
	return caster
}

func (c *fakeCaster) addr() (string, int) {
	parts := strings.Split(c.listener.Addr().String(), ":")
	port := 0
	_, _ = fmt.Sscanf(parts[len(parts)-1], "%d", &port)
	return "127.0.0.1", port
}

func (c *fakeCaster) handle(conn net.Conn) {
	defer func() { _ = conn.Close() }()
	_ = conn.SetReadDeadline(time.Now().Add(5 * time.Second))
	buffer := make([]byte, 0, 4096)
	chunk := make([]byte, 1024)
	for !strings.Contains(string(buffer), "\r\n\r\n") {
		n, err := conn.Read(chunk)
		if err != nil {
			return
		}
		buffer = append(buffer, chunk[:n]...)
		if len(buffer) > 16384 {
			return
		}
	}
	request := string(buffer)
	switch c.scenario {
	case "auth-fail":
		_, _ = conn.Write([]byte("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n"))
	case "notfound":
		_, _ = conn.Write([]byte("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"))
	case "html":
		_, _ = conn.Write([]byte("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<html>oops</html>"))
	default:
		if !strings.Contains(request, "/TEST00SYN") {
			_, _ = conn.Write([]byte("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"))
			return
		}
		_, _ = conn.Write([]byte("HTTP/1.1 200 OK\r\nContent-Type: gnss/data\r\nConnection: close\r\n\r\n"))
		step := len(c.payload)
		if c.scenario == "split" {
			step = 1
		}
		for offset := 0; offset < len(c.payload); offset += step {
			end := offset + step
			if end > len(c.payload) {
				end = len(c.payload)
			}
			if _, err := conn.Write(c.payload[offset:end]); err != nil {
				return
			}
		}
	}
}

func testPayload() []byte {
	var out []byte
	for _, msg := range []int{1005, 1077, 1087} {
		head := []byte{byte(msg >> 4), byte(msg&0x0F) << 4}
		payload := append(head, 0x00, 0x01)
		body := append([]byte{Preamble, byte(len(payload) >> 8), byte(len(payload))}, payload...)
		crc := CRC24Q(body)
		out = append(out, body...)
		out = append(out, byte(crc>>16), byte(crc>>8), byte(crc))
	}
	return out
}

func testClientFor(host string, port int) *Client {
	cfg := DefaultConfig()
	cfg.Host = host
	cfg.Port = port
	cfg.Mountpoint = "TEST00SYN"
	cfg.ReadTimeoutS = 2
	cfg.HandshakeTimeoutS = 5
	return NewClient(cfg, "test-provider", map[string]string{"TEST00SYN": "EKAK00NGA"}, "test-auth")
}

func readHeadAndPrefix(t *testing.T, conn net.Conn, maxHeader int) (string, map[string]string, []byte) {
	t.Helper()
	_ = conn.SetDeadline(time.Now().Add(5 * time.Second))
	data := make([]byte, 0, 8192)
	chunk := make([]byte, 1024)
	for {
		head, rest, ok := SplitHead(data, maxHeader)
		if ok {
			status, headers := ParseHead(head)
			return status, headers, rest
		}
		n, err := conn.Read(chunk)
		if err != nil {
			status, headers := ParseHead(data)
			return status, headers, nil
		}
		data = append(data, chunk[:n]...)
	}
}

func TestClientProbeValid(t *testing.T) {
	payload := testPayload()
	caster := startFakeCaster(t, "valid", payload)
	host, port := caster.addr()
	client := testClientFor(host, port)
	conn, err := client.Dial()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()
	if _, err := conn.Write(BuildStreamRequest(client.cfg)); err != nil {
		t.Fatal(err)
	}
	status, _, prefix := readHeadAndPrefix(t, conn, client.cfg.MaxHeaderBytes)
	result := ValidateStreamResponse(status, nil, prefix)
	if !result.OK {
		t.Fatalf("handshake = %+v", result)
	}
	framer, _ := NewFramer(MaxRTCMLen)
	frames := len(framer.Feed(prefix))
	chunk := make([]byte, 4096)
	_ = conn.SetDeadline(time.Now().Add(5 * time.Second))
	for {
		n, err := conn.Read(chunk)
		if n > 0 {
			frames += len(framer.Feed(chunk[:n]))
		}
		if err != nil {
			break
		}
	}
	if frames != 3 {
		t.Fatalf("frames = %d, want 3", frames)
	}
}

func TestClientProbeAuthFailureTerminal(t *testing.T) {
	caster := startFakeCaster(t, "auth-fail", nil)
	host, port := caster.addr()
	client := testClientFor(host, port)
	conn, err := client.Dial()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()
	_, _ = conn.Write(BuildStreamRequest(client.cfg))
	status, _, prefix := readHeadAndPrefix(t, conn, client.cfg.MaxHeaderBytes)
	result := ValidateStreamResponse(status, nil, prefix)
	if result.OK || result.Failure != FailureAuth || !IsTerminal(result.Failure) {
		t.Fatalf("result = %+v", result)
	}
}

func TestClientProbeNotFoundTerminal(t *testing.T) {
	caster := startFakeCaster(t, "notfound", nil)
	host, port := caster.addr()
	client := testClientFor(host, port)
	conn, err := client.Dial()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()
	_, _ = conn.Write(BuildStreamRequest(client.cfg))
	status, _, prefix := readHeadAndPrefix(t, conn, client.cfg.MaxHeaderBytes)
	result := ValidateStreamResponse(status, nil, prefix)
	if result.OK || result.Failure != FailureNotFound {
		t.Fatalf("result = %+v", result)
	}
}

func TestClientProbeHTMLRejected(t *testing.T) {
	caster := startFakeCaster(t, "html", nil)
	host, port := caster.addr()
	client := testClientFor(host, port)
	conn, err := client.Dial()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()
	_, _ = conn.Write(BuildStreamRequest(client.cfg))
	status, _, prefix := readHeadAndPrefix(t, conn, client.cfg.MaxHeaderBytes)
	// The HTML body may arrive after the head; read a little more if needed.
	if len(prefix) == 0 {
		_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
		extra := make([]byte, 1024)
		if n, err := conn.Read(extra); err == nil {
			prefix = append(prefix, extra[:n]...)
		}
	}
	result := ValidateStreamResponse(status, nil, prefix)
	if result.OK || result.Failure != FailureWrongContent {
		t.Fatalf("result = %+v status=%q prefix=%q", result, status, prefix)
	}
}

func TestClientProbeSplitDelivery(t *testing.T) {
	payload := testPayload()
	caster := startFakeCaster(t, "split", payload)
	host, port := caster.addr()
	client := testClientFor(host, port)
	conn, err := client.Dial()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = conn.Close() }()
	_, _ = conn.Write(BuildStreamRequest(client.cfg))
	status, _, prefix := readHeadAndPrefix(t, conn, client.cfg.MaxHeaderBytes)
	if result := ValidateStreamResponse(status, nil, prefix); !result.OK {
		t.Fatalf("handshake = %+v", result)
	}
	framer, _ := NewFramer(MaxRTCMLen)
	frames := framer.Feed(prefix)
	_ = conn.SetDeadline(time.Now().Add(5 * time.Second))
	chunk := make([]byte, 64)
	for {
		n, err := conn.Read(chunk)
		if n > 0 {
			frames = append(frames, framer.Feed(chunk[:n])...)
		}
		if err != nil {
			break
		}
	}
	if len(frames) != 3 {
		t.Fatalf("frames = %d, want 3", len(frames))
	}
}

func TestClientDialFailure(t *testing.T) {
	client := testClientFor("127.0.0.1", 1)
	if _, err := client.Dial(); err == nil {
		t.Fatal("dial to closed port must fail")
	}
}

func TestCaptureWriterRoundTrip(t *testing.T) {
	root := t.TempDir()
	writer, err := CreateCapture(root, "test-provider", "TEST00SYN", "EKAK00NGA", "2026-01-01",
		"cap-1", "127.0.0.1", 2101, "plain", "test-auth", "abc123", "00", "ENDSOURCETABLE\n")
	if err != nil {
		t.Fatal(err)
	}
	payload := testPayload()
	framer, _ := NewFramer(MaxRTCMLen)
	frames := framer.Feed(payload)
	now := time.Now()
	for i, frame := range frames {
		arrival := Arrival{
			ConnectionID: "conn-1", Sequence: int64(i), ArrivalMonotonic: now,
			ArrivalUTC: now.UTC(), ByteOffset: frame.ByteOffset,
			FrameLength: len(frame.Raw), MessageNumber: frame.MessageNumber,
			CRCStatus: "PASS", FrameSHA256: SHA256Hex(frame.Raw),
		}
		if err := writer.WriteFrame(frame.Raw, arrival); err != nil {
			t.Fatal(err)
		}
	}
	writer.NoteReconnect()
	meta, err := writer.Close(CaptureComplete)
	if err != nil {
		t.Fatal(err)
	}
	if meta.ValidFrames != 3 || meta.Reconnects != 1 || meta.Status != CaptureComplete {
		t.Fatalf("meta = %+v", meta)
	}
	for _, name := range []string{"stream.rtcm3", "arrival-index.csv", "source-table.txt", "capture.json", "SHA256SUMS.txt"} {
		if _, err := os.Stat(filepath.Join(writer.Dir(), name)); err != nil {
			t.Fatalf("missing %s: %v", name, err)
		}
	}
	if !strings.Contains(writer.Dir(), "EKAK00NGA") {
		t.Fatalf("dir = %s", writer.Dir())
	}
	// Traversal attempt must stay inside the root.
	evil, err := CreateCapture(root, "../../etc", "/x", "..", "", "cap", "h", 1, "plain", "t", "c", "00", "t")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := filepath.Rel(root, evil.Dir()); err != nil {
		t.Fatalf("evil dir escapes root: %s", evil.Dir())
	}
	if _, err := evil.Close(CaptureFailed); err != nil {
		t.Fatal(err)
	}
}
