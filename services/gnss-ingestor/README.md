# GNSS Ingestor Service

Phase 1 health endpoint plus Phase 10 live CORS/NTRIP ingestion
transport (`internal/ntrip/`). The service never generates corrections,
serves rovers, or claims positioning accuracy.

## Layout

```text
cmd/ingestor        health HTTP endpoint (Phase 1 foundation)
internal/config     non-secret service configuration
internal/health     liveness handler
internal/ntrip      live NTRIP ingestion (Phase 10)
```

## `internal/ntrip` packages (single `ntrip` package, files by concern)

| File | Responsibility |
|---|---|
| `doc.go` | Package scope and integrity rules |
| `config.go` | `NLGCP_NTRIP_*` environment convention, validation, redacted snapshots |
| `auth.go` | Basic auth, URL/header/text redaction |
| `sourcetable.go` | Bounded `STR`/`CAS`/`NET` parsing |
| `handshake.go` | NTRIP v2 requests, v1 tolerance, fail-closed validation |
| `framing.go` | Streaming RTCM 3.x framer |
| `crc.go` | CRC-24Q (RTKLIB-compatible convention) |
| `reconnect.go` | Bounded backoff, terminal classification |
| `admission.go` | Mountpoint admission, station mapping, path sanitization |
| `buffer.go` | Bounded buffer with explicit backpressure |
| `client.go` | Lifecycle states, dial/TLS, idle tracking, metrics, arrivals |
| `capture.go` | Immutable capture writer |
| `subjects.go` | `correction.live.*` subject names |
| `util.go` | SHA-256 helpers, config errors |

## Operator interface

Use the Python research bridge CLI (same conventions):

```bash
.venv/bin/python scripts/run_ntrip_ingest.py sourcetable|probe|capture|validate-capture|summarize [--dry-run]
```

## Testing

```bash
cd services/gnss-ingestor && go test ./...   # 31 tests, no network required
```

The Go suite spins a local deterministic TCP stand-in covering valid,
auth-rejection, mountpoint-not-found, HTML-error, and split-delivery
scenarios. Real-provider validation remains BLOCKED (no authorized
source); see `research/ntrip_ingestion/PILOT_EVIDENCE.md`.
