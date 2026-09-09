package ntrip

import (
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

// Capture layout: <root>/<provider>/<station>/<date>/<capture-id>/
// with stream.rtcm3, arrival-index.csv, source-table.txt, capture.json,
// and SHA256SUMS.txt. Raw captures are immutable by convention once closed.

// CaptureStatus marks a closed capture COMPLETE, PARTIAL, or FAILED.
type CaptureStatus string

const (
	CaptureComplete CaptureStatus = "COMPLETE"
	CapturePartial  CaptureStatus = "PARTIAL"
	CaptureFailed   CaptureStatus = "FAILED"
)

// CaptureMetadata is the password-free capture description.
type CaptureMetadata struct {
	CaptureID               string
	Provider                string
	CasterHost              string
	CasterPort              int
	Mountpoint              string
	StationMapping          string
	StartUTC                time.Time
	EndUTC                  time.Time
	DurationS               float64
	BytesReceived           int64
	ValidFrames             int
	InvalidFrames           int
	ObservedMessageTypes    []string
	Disconnects             int
	Reconnects              int
	TLSMode                 string
	SoftwareCommit          string
	SourceTableSHA256       string
	StreamSHA256            string
	AuthorizationProvenance string
	Status                  CaptureStatus
}

// CaptureWriter appends raw bytes plus arrival-index rows incrementally
// so partial files remain analyzable after interruption.
type CaptureWriter struct {
	dir            string
	captureID      string
	provider       string
	casterHost     string
	casterPort     int
	mountpoint     string
	stationMapping string
	tlsMode        string
	authProvenance string
	softwareCommit string
	sourceTableSHA string
	startUTC       time.Time
	startMono      time.Time
	stream         *os.File
	index          *os.File
	indexWriter    *csv.Writer
	bytesReceived  int64
	validFrames    int
	invalidFrames  int
	messageTypes   map[string]bool
	disconnects    int
	reconnects     int
	shaAccumulator []byte
	streamSHA      string
}

// CreateCapture opens a sanitized capture directory (originals stay in metadata).
func CreateCapture(root, provider, mountpoint, stationID, date, captureID, casterHost string, casterPort int, tlsMode, authProvenance, softwareCommit, sourceTableSHA, sourceTableText string) (*CaptureWriter, error) {
	if date == "" {
		date = time.Now().UTC().Format("2006-01-02")
	}
	dir := filepath.Join(root,
		SanitizeIdentifier(provider, "unknown"),
		SanitizeIdentifier(stationID, "unknown"),
		SanitizeIdentifier(date, "unknown"),
		SanitizeIdentifier(captureID, "unknown"),
	)
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return nil, err
	}
	stream, err := os.OpenFile(filepath.Join(dir, "stream.rtcm3"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640)
	if err != nil {
		return nil, err
	}
	index, err := os.OpenFile(filepath.Join(dir, "arrival-index.csv"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640)
	if err != nil {
		_ = stream.Close()
		return nil, err
	}
	writer := &CaptureWriter{
		dir: dir, captureID: captureID, provider: provider, casterHost: casterHost,
		casterPort: casterPort, mountpoint: mountpoint, stationMapping: stationID,
		tlsMode: tlsMode, authProvenance: authProvenance, softwareCommit: softwareCommit,
		sourceTableSHA: sourceTableSHA, startUTC: time.Now().UTC(), startMono: time.Now(),
		stream: stream, index: index, messageTypes: map[string]bool{},
	}
	writer.indexWriter = csv.NewWriter(index)
	if info, err := index.Stat(); err == nil && info.Size() == 0 {
		_ = writer.indexWriter.Write([]string{"sequence", "byte_offset", "frame_length", "arrival_utc", "arrival_monotonic_ns", "message_number", "crc_status", "frame_sha256"})
		writer.indexWriter.Flush()
	}
	if err := os.WriteFile(filepath.Join(dir, "source-table.txt"), []byte(sourceTableText), 0o640); err != nil {
		_ = stream.Close()
		_ = index.Close()
		return nil, err
	}
	return writer, nil
}

// Dir returns the capture directory.
func (w *CaptureWriter) Dir() string { return w.dir }

// NoteReconnect records a reconnect boundary (new connection id upstream).
func (w *CaptureWriter) NoteReconnect() {
	w.disconnects++
	w.reconnects++
}

// WriteFrame appends one frame's bytes plus its arrival-index row (flushed).
func (w *CaptureWriter) WriteFrame(raw []byte, arrival Arrival) error {
	if _, err := w.stream.Write(raw); err != nil {
		return err
	}
	if err := w.stream.Sync(); err != nil {
		return err
	}
	msg := ""
	if arrival.MessageNumber != nil {
		msg = strconv.Itoa(*arrival.MessageNumber)
		w.messageTypes[msg] = true
	}
	record := []string{
		strconv.FormatInt(arrival.Sequence, 10),
		strconv.FormatInt(arrival.ByteOffset, 10),
		strconv.Itoa(arrival.FrameLength),
		arrival.ArrivalUTC.UTC().Format(time.RFC3339Nano),
		strconv.FormatInt(arrival.ArrivalMonotonic.UnixNano(), 10),
		msg,
		arrival.CRCStatus,
		arrival.FrameSHA256,
	}
	if err := w.indexWriter.Write(record); err != nil {
		return err
	}
	w.indexWriter.Flush()
	if err := w.index.Sync(); err != nil {
		return err
	}
	w.shaAccumulator = append(w.shaAccumulator, raw...)
	w.bytesReceived += int64(len(raw))
	if arrival.CRCStatus == "PASS" {
		w.validFrames++
	} else {
		w.invalidFrames++
	}
	return nil
}

// Close finalises the capture: capture.json + SHA256SUMS, then immutable.
func (w *CaptureWriter) Close(status CaptureStatus) (CaptureMetadata, error) {
	_ = w.stream.Close()
	w.indexWriter.Flush()
	_ = w.index.Close()
	end := time.Now().UTC()
	sum := sha256.Sum256(w.shaAccumulator)
	w.streamSHA = hex.EncodeToString(sum[:])
	var observed []string
	for msg := range w.messageTypes {
		observed = append(observed, msg)
	}
	meta := CaptureMetadata{
		CaptureID: w.captureID, Provider: w.provider, CasterHost: w.casterHost,
		CasterPort: w.casterPort, Mountpoint: w.mountpoint, StationMapping: w.stationMapping,
		StartUTC: w.startUTC, EndUTC: end, DurationS: time.Since(w.startMono).Seconds(),
		BytesReceived: w.bytesReceived, ValidFrames: w.validFrames, InvalidFrames: w.invalidFrames,
		ObservedMessageTypes: observed, Disconnects: w.disconnects, Reconnects: w.reconnects,
		TLSMode: w.tlsMode, SoftwareCommit: w.softwareCommit, SourceTableSHA256: w.sourceTableSHA,
		StreamSHA256: w.streamSHA, AuthorizationProvenance: w.authProvenance, Status: status,
	}
	payload := fmt.Sprintf(
		"{\n  \"capture_id\": %q,\n  \"provider\": %q,\n  \"caster_host\": %q,\n  \"caster_port\": %d,\n  \"mountpoint\": %q,\n  \"station_mapping\": %q,\n  \"start_utc\": %q,\n  \"end_utc\": %q,\n  \"bytes_received\": %d,\n  \"valid_frames\": %d,\n  \"invalid_frames\": %d,\n  \"tls_mode\": %q,\n  \"stream_sha256\": %q,\n  \"capture_status\": %q\n}\n",
		meta.CaptureID, meta.Provider, meta.CasterHost, meta.CasterPort, meta.Mountpoint,
		meta.StationMapping, meta.StartUTC.Format(time.RFC3339Nano), meta.EndUTC.Format(time.RFC3339Nano),
		meta.BytesReceived, meta.ValidFrames, meta.InvalidFrames, meta.TLSMode, meta.StreamSHA256, string(meta.Status),
	)
	if err := os.WriteFile(filepath.Join(w.dir, "capture.json"), []byte(payload), 0o640); err != nil {
		return meta, err
	}
	var sums string
	for _, name := range []string{"stream.rtcm3", "arrival-index.csv", "source-table.txt", "capture.json"} {
		data, err := os.ReadFile(filepath.Join(w.dir, name))
		if err != nil {
			return meta, err
		}
		digest := sha256.Sum256(data)
		sums += hex.EncodeToString(digest[:]) + "  " + name + "\n"
	}
	if err := os.WriteFile(filepath.Join(w.dir, "SHA256SUMS.txt"), []byte(sums), 0o640); err != nil {
		return meta, err
	}
	return meta, nil
}
