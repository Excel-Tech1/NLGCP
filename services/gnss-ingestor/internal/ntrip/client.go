package ntrip

import (
	"crypto/tls"
	"net"
	"strconv"
	"time"
)

// ConnectionState is the observable client lifecycle state.
type ConnectionState string

const (
	StateDisconnected   ConnectionState = "DISCONNECTED"
	StateConnecting     ConnectionState = "CONNECTING"
	StateAuthenticating ConnectionState = "AUTHENTICATING"
	StateStreaming      ConnectionState = "STREAMING"
	StateDegraded       ConnectionState = "DEGRADED"
	StateReconnecting   ConnectionState = "RECONNECTING"
	StateStopped        ConnectionState = "STOPPED"
	StateBlocked        ConnectionState = "BLOCKED"
)

// Metrics are measured-only live transport counters (never fabricated).
type Metrics struct {
	ConnectionsAttempted   int
	ConnectionsSuccessful  int
	AuthenticationFailures int
	Reconnects             int
	BytesReceived          int64
	FramesReceived         int
	FramesCRCValid         int
	FramesCRCInvalid       int
	MessageTypeCounts      map[string]int
	IdleEvents             int
	CaptureDurationS       float64
	BufferHighWaterMark    int
	FramesDropped          int
	ProducerWaits          int
	ConsumerWaits          int
}

// Arrival is the genuine network arrival timing of one frame (not a GNSS epoch).
type Arrival struct {
	ConnectionID     string
	Sequence         int64
	ArrivalMonotonic time.Time
	ArrivalUTC       time.Time
	ByteOffset       int64
	FrameLength      int
	MessageNumber    *int
	CRCStatus        string
	FrameSHA256      string
}

// IdleTracker detects stalled streams from last-byte/last-frame times.
type IdleTracker struct {
	IdleTimeout   time.Duration
	LastByteTime  time.Time
	LastFrameTime time.Time
	Events        int
	now           func() time.Time
}

// NewIdleTracker returns a tracker anchored at now.
func NewIdleTracker(idleTimeout time.Duration, now func() time.Time) *IdleTracker {
	if now == nil {
		now = time.Now
	}
	current := now()
	return &IdleTracker{IdleTimeout: idleTimeout, LastByteTime: current, LastFrameTime: current, now: now}
}

// NoteBytes records wire activity.
func (t *IdleTracker) NoteBytes() { t.LastByteTime = t.now() }

// NoteFrame records a valid frame.
func (t *IdleTracker) NoteFrame() { t.LastFrameTime = t.now() }

// IdleDuration reports time since the last wire byte.
func (t *IdleTracker) IdleDuration() time.Duration { return t.now().Sub(t.LastByteTime) }

// Stalled reports STREAM_STALLED when silence exceeds the idle timeout.
func (t *IdleTracker) Stalled() bool {
	stalled := t.IdleDuration() > t.IdleTimeout
	if stalled {
		t.Events++
	}
	return stalled
}

// Client is the fail-closed live NTRIP client with observable states.
type Client struct {
	cfg         Config
	provider    string
	registry    map[string]string
	authBasis   string
	state       ConnectionState
	Transitions []ConnectionState
	Metrics     Metrics
}

// NewClient returns a client; no network activity happens before use.
func NewClient(cfg Config, provider string, registry map[string]string, authBasis string) *Client {
	if registry == nil {
		registry = map[string]string{}
	}
	c := &Client{cfg: cfg, provider: provider, registry: registry, authBasis: authBasis}
	c.setState(StateDisconnected)
	return c
}

// State returns the current lifecycle state.
func (c *Client) State() ConnectionState { return c.state }

func (c *Client) setState(state ConnectionState) {
	c.state = state
	c.Transitions = append(c.Transitions, state)
}

// Dial opens the caster connection with bounded timeouts and validated TLS by default.
func (c *Client) Dial() (net.Conn, error) {
	address := net.JoinHostPort(c.cfg.Host, strconv.Itoa(c.cfg.Port))
	dialer := &net.Dialer{Timeout: seconds(c.cfg.DialTimeoutS)}
	if !c.cfg.UseTLS {
		return dialer.Dial("tcp", address)
	}
	if c.cfg.AllowInsecureTLS {
		// Diagnostic only, never default: skips certificate verification.
		raw, err := dialer.Dial("tcp", address)
		if err != nil {
			return nil, err
		}
		tlsCfg := &tls.Config{InsecureSkipVerify: true} //nolint:gosec // explicit diagnostic mode
		return tls.Client(raw, tlsCfg), nil
	}
	tlsCfg := &tls.Config{ServerName: c.cfg.Host, MinVersion: tls.VersionTLS12} //nolint:gosec // validated TLS
	return tls.DialWithDialer(dialer, "tcp", address, tlsCfg)
}

func seconds(value float64) time.Duration {
	return time.Duration(value * float64(time.Second))
}
