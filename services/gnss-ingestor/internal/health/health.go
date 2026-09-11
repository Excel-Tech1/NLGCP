// Package health provides process-liveness and readiness HTTP handling.
package health

import (
	"encoding/json"
	"net/http"
	"sync"
)

// Reporter exposes service health without claiming GNSS scientific validity.
type Reporter struct {
	mu             sync.RWMutex
	configured     bool
	configProblems []string
	streamState    string
}

// NewReporter creates a reporter. No network activity occurs here.
func NewReporter(configured bool, configProblems []string) *Reporter {
	return &Reporter{configured: configured, configProblems: append([]string(nil), configProblems...), streamState: "DISCONNECTED"}
}

// SetStreamState updates the operational state reported by /status.
func (r *Reporter) SetStreamState(state string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.streamState = state
}

func Handler(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "gnss-ingestor", "scientific_validity": "not_assessed"})
}

// ReadyHandler reports configuration/filesystem readiness, not stream or positioning validity.
func (r *Reporter) ReadyHandler(w http.ResponseWriter, _ *http.Request) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	status := "READY"
	reasons := append([]string(nil), r.configProblems...)
	if r.configured && len(reasons) > 0 {
		status = "NOT_READY"
	}
	if !r.configured && len(reasons) == 0 {
		reasons = []string{"INGESTION_DISABLED_NO_CASTER_CONFIGURED"}
	}
	code := http.StatusOK
	if status != "READY" {
		code = http.StatusServiceUnavailable
	}
	writeJSON(w, code, map[string]any{
		"status": status, "configured_stream": r.configured,
		"reason_codes": reasons, "stream_state": r.streamState,
		"scientific_validity": "not_assessed",
	})
}

// StatusHandler reports liveness, readiness and stream state together.
func (r *Reporter) StatusHandler(w http.ResponseWriter, _ *http.Request) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	reasons := append([]string(nil), r.configProblems...)
	ready := len(reasons) == 0
	if !r.configured {
		reasons = []string{"INGESTION_DISABLED_NO_CASTER_CONFIGURED"}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"liveness":     map[string]string{"status": "ALIVE", "scientific_validity": "NOT_ASSESSED"},
		"readiness":    map[string]any{"status": map[bool]string{true: "READY", false: "NOT_READY"}[ready], "reason_codes": reasons, "configured_stream": r.configured},
		"stream_state": r.streamState,
	})
}

func writeJSON(w http.ResponseWriter, code int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(payload)
}
