package ntrip

import (
	"math"
	"math/rand"
)

// ReconnectPolicy bounds automatic reconnection: exponential backoff
// with cap (1s, 2s, 4s, 8s, ... capped) and optional deterministic
// jitter. Delays are computed arithmetically so tests never sleep.
type ReconnectPolicy struct {
	BaseDelayS  float64
	MaxDelayS   float64
	MaxAttempts int
}

// DefaultReconnectPolicy mirrors the Python client defaults.
func DefaultReconnectPolicy() ReconnectPolicy {
	return ReconnectPolicy{BaseDelayS: 1, MaxDelayS: 30, MaxAttempts: 8}
}

// Validate reports policy problems (empty = valid).
func (p ReconnectPolicy) Validate() []string {
	var problems []string
	if p.BaseDelayS <= 0 {
		problems = append(problems, "base_delay_s must be > 0")
	}
	if p.MaxDelayS <= 0 {
		problems = append(problems, "max_delay_s must be > 0")
	}
	if p.MaxDelayS < p.BaseDelayS {
		problems = append(problems, "max_delay_s must be >= base_delay_s")
	}
	if p.MaxAttempts < 0 {
		problems = append(problems, "max_attempts must be >= 0")
	}
	return problems
}

// DelayForAttempt returns the backoff delay for 1-indexed attempt n.
// With seed != nil a deterministic ±10% jitter is applied (tests only).
func (p ReconnectPolicy) DelayForAttempt(attempt int, seed *int64) float64 {
	if attempt < 1 {
		panic("attempt must be >= 1")
	}
	delay := p.BaseDelayS * math.Pow(2, float64(attempt-1))
	if delay > p.MaxDelayS {
		delay = p.MaxDelayS
	}
	if seed != nil {
		rng := rand.New(rand.NewSource(*seed))
		delay *= 0.9 + 0.2*rng.Float64()
	}
	return delay
}

// Exhausted reports whether attemptsMade reached the configured cap.
func (p ReconnectPolicy) Exhausted(attemptsMade int) bool {
	return attemptsMade >= p.MaxAttempts
}

// ClassifyStatusCode maps HTTP status codes to failure classes.
func ClassifyStatusCode(code int) FailureClass {
	switch code {
	case 401:
		return FailureAuth
	case 403:
		return FailureForbidden
	case 404:
		return FailureNotFound
	default:
		return FailureProtocol
	}
}
