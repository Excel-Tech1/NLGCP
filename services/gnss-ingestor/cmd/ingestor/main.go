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
	"time"

	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/config"
	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/health"
	"github.com/nlgcp/nigeria-rtk-platform/services/gnss-ingestor/internal/ntrip"
)

const (
	defaultReadHeaderTimeout = 5 * time.Second
	defaultReadTimeout       = 10 * time.Second
	defaultWriteTimeout      = 10 * time.Second
	defaultIdleTimeout       = 60 * time.Second
	defaultShutdownTimeout   = 5 * time.Second
	defaultMaxHeaderBytes    = 8192
)

func buildHTTPServer(address string, handler http.Handler) *http.Server {
	return &http.Server{
		Addr:              address,
		Handler:           handler,
		ReadHeaderTimeout: defaultReadHeaderTimeout,
		ReadTimeout:       defaultReadTimeout,
		WriteTimeout:      defaultWriteTimeout,
		IdleTimeout:       defaultIdleTimeout,
		MaxHeaderBytes:    defaultMaxHeaderBytes,
	}
}

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
	server := buildHTTPServer(settings.Address, mux)
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
	shutdownCtx, cancel := context.WithTimeout(context.Background(), defaultShutdownTimeout)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
		os.Exit(1)
	}
}
