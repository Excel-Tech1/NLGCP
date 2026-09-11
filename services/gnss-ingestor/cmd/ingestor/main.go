// Command ingestor hosts the operational health boundary. It does not
// connect to GNSS streams until a later runtime orchestration layer starts it.
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/config"
	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/health"
	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/ntrip"
)

func main() {
	settings := config.Load()
	ntripConfig := ntrip.ConfigFromEnv()
	configured := ntripConfig.Host != "" || ntripConfig.Mountpoint != "" || ntripConfig.Username != ""
	problems := []string{}
	if configured {
		problems = ntripConfig.Validate()
	}
	reporter := health.NewReporter(configured, problems)
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", health.Handler)
	mux.HandleFunc("GET /live", health.Handler)
	mux.HandleFunc("GET /ready", reporter.ReadyHandler)
	mux.HandleFunc("GET /status", reporter.StatusHandler)
	server := &http.Server{Addr: settings.Address, Handler: mux}
	slog.Info("starting GNSS ingestor health boundary", "address", settings.Address, "configured_stream", configured)
	stopContext, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server stopped", "error", err)
			os.Exit(1)
		}
	}()
	<-stopContext.Done()
	slog.Info("shutdown requested")
	if err := server.Shutdown(context.Background()); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
		os.Exit(1)
	}
}
