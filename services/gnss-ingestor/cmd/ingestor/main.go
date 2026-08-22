// Command ingestor hosts the Phase 1 health endpoint. It does not connect to GNSS streams.
package main

import (
	"log/slog"
	"net/http"
	"os"

	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/config"
	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/health"
)

func main() {
	settings := config.Load()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", health.Handler)
	slog.Info("starting GNSS ingestor foundation", "address", settings.Address)
	if err := http.ListenAndServe(settings.Address, mux); err != nil {
		slog.Error("server stopped", "error", err)
		os.Exit(1)
	}
}
