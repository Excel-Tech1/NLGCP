package ntrip

import (
	"os"
	"strconv"
	"strings"
)

// Environment variable convention for secure NTRIP configuration.
// Secrets travel via environment only and are never required for tests.
const (
	EnvHost      = "NLGCP_NTRIP_HOST"
	EnvPort      = "NLGCP_NTRIP_PORT"
	EnvMount     = "NLGCP_NTRIP_MOUNTPOINT"
	EnvUser      = "NLGCP_NTRIP_USERNAME"
	EnvPassword  = "NLGCP_NTRIP_PASSWORD"
	EnvTLS       = "NLGCP_NTRIP_TLS"
	EnvUserAgent = "NLGCP_NTRIP_USER_AGENT"
	EnvGGA       = "NLGCP_NTRIP_GGA"

	DefaultPort      = 2101
	DefaultUserAgent = "NLGCP-Phase10/1.0"
)

// Config is the secure NTRIP client configuration.
type Config struct {
	Host                string
	Port                int
	Mountpoint          string
	Username            string
	Password            string
	UseTLS              bool
	UserAgent           string
	GGASentence         string
	DialTimeoutS        float64
	TLSHandshakeTimeout float64
	HandshakeTimeoutS   float64
	ReadTimeoutS        float64
	IdleTimeoutS        float64
	MaxReconnects       int
	ReconnectBaseDelayS float64
	ReconnectMaxDelayS  float64
	BufferCapacity      int
	MaxFrameLength      int
	MaxHeaderBytes      int
	MaxSourcetableBytes int
	MaxCaptureBytes     int64
	MaxCaptureSeconds   float64
	AllowInsecureTLS    bool
}

// DefaultConfig returns bounded production defaults (no secrets).
func DefaultConfig() Config {
	return Config{
		Port:                DefaultPort,
		UserAgent:           DefaultUserAgent,
		DialTimeoutS:        5,
		TLSHandshakeTimeout: 5,
		HandshakeTimeoutS:   10,
		ReadTimeoutS:        10,
		IdleTimeoutS:        30,
		MaxReconnects:       8,
		ReconnectBaseDelayS: 1,
		ReconnectMaxDelayS:  30,
		BufferCapacity:      64,
		MaxFrameLength:      MaxRTCMLen,
		MaxHeaderBytes:      8192,
		MaxSourcetableBytes: 65536,
		MaxCaptureBytes:     64 << 20,
		MaxCaptureSeconds:   60,
	}
}

// ConfigFromEnv builds configuration from the process environment.
// Missing optional values fall back to defaults; secrets are never invented.
func ConfigFromEnv() Config {
	cfg := DefaultConfig()
	cfg.Host = strings.TrimSpace(os.Getenv(EnvHost))
	if port, err := strconv.Atoi(strings.TrimSpace(os.Getenv(EnvPort))); err == nil && port != 0 {
		cfg.Port = port
	}
	cfg.Mountpoint = strings.TrimSpace(os.Getenv(EnvMount))
	cfg.Username = os.Getenv(EnvUser)
	cfg.Password = os.Getenv(EnvPassword)
	cfg.UseTLS = parseBool(os.Getenv(EnvTLS))
	cfg.AllowInsecureTLS = parseBool(os.Getenv("NLGCP_NTRIP_INSECURE_TLS"))
	if agent := os.Getenv(EnvUserAgent); agent != "" {
		cfg.UserAgent = agent
	}
	cfg.GGASentence = os.Getenv(EnvGGA)
	return cfg
}

func parseBool(raw string) bool {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

// Validate reports fail-closed configuration problems (empty = valid).
func (c Config) Validate() []string {
	var problems []string
	if c.Host == "" {
		problems = append(problems, "host must be non-empty")
	}
	if c.Port < 1 || c.Port > 65535 {
		problems = append(problems, "port out of range")
	}
	if c.Mountpoint == "" || c.Mountpoint == "/" {
		problems = append(problems, "mountpoint must be non-empty")
	}
	for name, value := range map[string]float64{
		"dial_timeout_s": c.DialTimeoutS, "tls_timeout_s": c.TLSHandshakeTimeout,
		"handshake_timeout_s": c.HandshakeTimeoutS, "read_timeout_s": c.ReadTimeoutS,
		"idle_timeout_s": c.IdleTimeoutS,
	} {
		if value <= 0 {
			problems = append(problems, name+" must be > 0")
		}
	}
	if c.MaxReconnects < 0 {
		problems = append(problems, "max_reconnects must be >= 0")
	}
	if c.ReconnectBaseDelayS <= 0 || c.ReconnectMaxDelayS <= 0 {
		problems = append(problems, "reconnect delays must be > 0")
	}
	if c.BufferCapacity < 1 {
		problems = append(problems, "buffer_capacity must be >= 1")
	}
	if c.MaxFrameLength < 1 || c.MaxFrameLength > MaxRTCMLen {
		problems = append(problems, "max_frame_length must be within 1..1023")
	}
	if c.MaxCaptureBytes < 1 {
		problems = append(problems, "max_capture_bytes must be >= 1")
	}
	return problems
}

// RedactedSnapshot returns a log-safe configuration copy (no password).
func (c Config) RedactedSnapshot() map[string]string {
	password := ""
	if c.Password != "" {
		password = Redacted
	}
	tls := "false"
	if c.UseTLS {
		tls = "true"
	}
	return map[string]string{
		"host": c.Host, "port": strconv.Itoa(c.Port), "mountpoint": c.Mountpoint,
		"username": c.Username, "password": password, "tls": tls, "user_agent": c.UserAgent,
	}
}
