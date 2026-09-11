package health

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHandler(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()
	Handler(recorder, request)
	if recorder.Code != http.StatusOK || !strings.Contains(recorder.Body.String(), `"status":"ok"`) {
		t.Fatalf("unexpected response: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestDisabledServiceIsLiveAndReadyButNotScientific(t *testing.T) {
	reporter := NewReporter(false, nil)
	ready := httptest.NewRecorder()
	reporter.ReadyHandler(ready, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if ready.Code != http.StatusOK || !strings.Contains(ready.Body.String(), "INGESTION_DISABLED") {
		t.Fatalf("unexpected readiness: %d %s", ready.Code, ready.Body.String())
	}
	if !strings.Contains(ready.Body.String(), "not_assessed") {
		t.Fatalf("readiness made a scientific claim: %s", ready.Body.String())
	}
}

func TestInvalidConfiguredServiceIsNotReady(t *testing.T) {
	reporter := NewReporter(true, []string{"mountpoint must be non-empty"})
	ready := httptest.NewRecorder()
	reporter.ReadyHandler(ready, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if ready.Code != http.StatusServiceUnavailable || !strings.Contains(ready.Body.String(), "NOT_READY") {
		t.Fatalf("unexpected readiness: %d %s", ready.Code, ready.Body.String())
	}
}
