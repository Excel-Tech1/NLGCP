package main

import (
	"net/http"
	"testing"
)

func TestBuildHTTPServerConfiguresBoundedTimeouts(t *testing.T) {
	srv := buildHTTPServer("127.0.0.1:8081", http.NewServeMux())
	if srv.ReadHeaderTimeout <= 0 {
		t.Fatalf("expected positive ReadHeaderTimeout (SEC-05), got %v", srv.ReadHeaderTimeout)
	}
	if srv.ReadTimeout <= 0 || srv.WriteTimeout <= 0 || srv.IdleTimeout <= 0 {
		t.Fatalf("expected positive Read/Write/Idle timeouts (SEC-05), got %v/%v/%v", srv.ReadTimeout, srv.WriteTimeout, srv.IdleTimeout)
	}
	if srv.MaxHeaderBytes <= 0 || srv.MaxHeaderBytes > 65536 {
		t.Fatalf("expected bounded MaxHeaderBytes, got %d", srv.MaxHeaderBytes)
	}
}
