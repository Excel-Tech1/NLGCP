package ntrip

import (
	"bytes"
	"fmt"
	"strconv"
	"strings"
)

// NTRIP v2 is spoken first; v1-compatible ICY 200 responses are tolerated.
// Documented accepted successes: "HTTP/1.x 200" and "ICY 200".

// FailureClass classifies handshake/stream failures for fail-closed handling.
type FailureClass string

const (
	FailureAuth         FailureClass = "AUTH_FAILURE"
	FailureForbidden    FailureClass = "AUTHORIZATION_REJECTED"
	FailureNotFound     FailureClass = "MOUNTPOINT_NOT_FOUND"
	FailureConfig       FailureClass = "CONFIG_INVALID"
	FailureProtocol     FailureClass = "PROTOCOL_ERROR"
	FailureWrongContent FailureClass = "WRONG_CONTENT"
	FailureEmpty        FailureClass = "EMPTY_RESPONSE"
	FailureTimeout      FailureClass = "TIMEOUT"
	FailureStalled      FailureClass = "STALLED"
	FailureLost         FailureClass = "CONNECTION_LOST"
	FailureNMEARequired FailureClass = "NMEA_POSITION_REQUIRED"
)

// TerminalFailures must never reconnect without a configuration change:
// bad credentials, unknown mountpoint, explicit rejection, bad config.
func IsTerminal(failure FailureClass) bool {
	switch failure {
	case FailureAuth, FailureNotFound, FailureForbidden, FailureConfig:
		return true
	default:
		return false
	}
}

// HandshakeResult is a validated (or refused) stream handshake.
type HandshakeResult struct {
	OK         bool
	Failure    FailureClass
	Reason     string
	StatusCode int
}

// BuildStreamRequest renders a GET request for the mountpoint (NTRIP v2 first).
func BuildStreamRequest(cfg Config) []byte {
	mount := cfg.Mountpoint
	if !strings.HasPrefix(mount, "/") {
		mount = "/" + mount
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "GET %s HTTP/1.1\r\n", mount)
	fmt.Fprintf(&sb, "Host: %s:%d\r\n", cfg.Host, cfg.Port)
	sb.WriteString("Ntrip-Version: Ntrip/2.0\r\n")
	fmt.Fprintf(&sb, "User-Agent: %s\r\n", cfg.UserAgent)
	sb.WriteString("Accept: */*\r\nConnection: close\r\n")
	if cfg.Username != "" {
		fmt.Fprintf(&sb, "Authorization: %s\r\n", BasicAuthHeader(cfg.Username, cfg.Password))
	}
	if strings.TrimSpace(cfg.GGASentence) != "" {
		fmt.Fprintf(&sb, "Ntrip-GGA: %s\r\n", strings.TrimSpace(cfg.GGASentence))
	}
	sb.WriteString("\r\n")
	return []byte(sb.String())
}

// BuildSourcetableRequest renders a source-table request (GET /).
func BuildSourcetableRequest(cfg Config) []byte {
	var sb strings.Builder
	sb.WriteString("GET / HTTP/1.1\r\n")
	fmt.Fprintf(&sb, "Host: %s:%d\r\n", cfg.Host, cfg.Port)
	sb.WriteString("Ntrip-Version: Ntrip/2.0\r\n")
	fmt.Fprintf(&sb, "User-Agent: %s\r\n", cfg.UserAgent)
	sb.WriteString("Accept: */*\r\nConnection: close\r\n")
	if cfg.Username != "" {
		fmt.Fprintf(&sb, "Authorization: %s\r\n", BasicAuthHeader(cfg.Username, cfg.Password))
	}
	sb.WriteString("\r\n")
	return []byte(sb.String())
}

// ParseStatusLine splits a status line into protocol, code (0 if absent), text.
func ParseStatusLine(line string) (string, int, string) {
	parts := strings.SplitN(strings.TrimSpace(line), " ", 3)
	if len(parts) < 2 {
		return "", 0, strings.TrimSpace(line)
	}
	code, err := strconv.Atoi(parts[1])
	if err != nil {
		return parts[0], 0, strings.TrimSpace(line)
	}
	text := ""
	if len(parts) > 2 {
		text = parts[2]
	}
	return parts[0], code, text
}

func looksLikeSourcetable(prefix []byte) bool {
	if len(prefix) > 512 {
		prefix = prefix[:512]
	}
	text := string(prefix)
	upper := strings.ToUpper(text)
	return strings.HasPrefix(text, "STR;") || strings.HasPrefix(text, "CAS;") ||
		strings.HasPrefix(text, "NET;") || strings.Contains(upper, "ENDSOURCETABLE")
}

func looksLikeHTML(prefix []byte) bool {
	if len(prefix) > 1024 {
		prefix = prefix[:1024]
	}
	lowered := strings.ToLower(strings.TrimSpace(string(prefix)))
	return strings.HasPrefix(lowered, "<html") || strings.HasPrefix(lowered, "<!doctype")
}

// ValidateStreamResponse validates a stream handshake, failing closed so
// no binary parser ever consumes an HTTP error body as RTCM.
func ValidateStreamResponse(statusLine string, headers map[string]string, bodyPrefix []byte) HandshakeResult {
	_ = headers
	if strings.TrimSpace(statusLine) == "" {
		return HandshakeResult{Failure: FailureEmpty, Reason: "empty status line"}
	}
	protocol, code, _ := ParseStatusLine(statusLine)
	known := protocol == "HTTP/1.0" || protocol == "HTTP/1.1" || protocol == "ICY" ||
		strings.HasPrefix(strings.ToUpper(strings.TrimSpace(statusLine)), "ICY ")
	if !known || code == 0 {
		return HandshakeResult{Failure: FailureProtocol, Reason: "malformed status line: " + statusLine}
	}
	switch code {
	case 200:
		if looksLikeHTML(bodyPrefix) {
			return HandshakeResult{Failure: FailureWrongContent, Reason: "HTML body where RTCM expected", StatusCode: code}
		}
		if looksLikeSourcetable(bodyPrefix) {
			return HandshakeResult{Failure: FailureWrongContent, Reason: "source-table body where RTCM stream expected", StatusCode: code}
		}
		return HandshakeResult{OK: true, Reason: "handshake_success", StatusCode: code}
	case 401:
		return HandshakeResult{Failure: FailureAuth, Reason: "authorization rejected: 401", StatusCode: code}
	case 403:
		return HandshakeResult{Failure: FailureForbidden, Reason: "authorization rejected: 403", StatusCode: code}
	case 404:
		return HandshakeResult{Failure: FailureNotFound, Reason: "mountpoint not found: 404", StatusCode: code}
	default:
		return HandshakeResult{Failure: FailureProtocol, Reason: "unexpected status: " + strconv.Itoa(code), StatusCode: code}
	}
}

// SplitHead splits raw bytes into head and rest at the first blank line.
// It returns ok=false when no terminator is present yet (or on oversize).
func SplitHead(data []byte, maxHeaderBytes int) (head, rest []byte, ok bool) {
	for _, sep := range [][]byte{[]byte("\r\n\r\n"), []byte("\n\n")} {
		if index := bytes.Index(data, sep); index >= 0 {
			head = data[:index]
			if len(head) > maxHeaderBytes {
				return nil, nil, false
			}
			return head, data[index+len(sep):], true
		}
	}
	if len(data) > maxHeaderBytes {
		return nil, nil, false
	}
	return nil, nil, false
}

// ParseHead parses a response head into status line and headers.
func ParseHead(head []byte) (string, map[string]string) {
	lines := strings.Split(string(head), "\n")
	status := ""
	if len(lines) > 0 {
		status = strings.TrimRight(lines[0], "\r")
	}
	headers := map[string]string{}
	for _, line := range lines[1:] {
		line = strings.TrimRight(line, "\r")
		if key, value, found := strings.Cut(line, ":"); found {
			headers[strings.TrimSpace(key)] = strings.TrimSpace(value)
		}
	}
	return status, headers
}
