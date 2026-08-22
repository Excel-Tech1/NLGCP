# Nigeria Localised GNSS Correction Platform (NLGCP)

NLGCP is a scientific and real-time GNSS infrastructure project. Nigeria has national GNSS reference infrastructure, but sparse reference geometry and operational constraints create challenges for reliable local centimetre-level RTK coverage. The project will investigate and build a NIGNET-anchored local correction system that may eventually support:

```text
CORS observations
  -> network processing
  -> single-base/VRS corrections
  -> RTCM
  -> NTRIP
  -> GNSS rover
```

**Current Phase: Phase 1 — Engineering Foundation.** No live correction service, validated accuracy result, station coverage claim, or production GNSS algorithm exists yet.

## Technology direction

- GNSS core: RTKLIB plus reviewed custom C/C++
- Independent offline validation: PRIDE PPP-AR
- Research: Python
- Ingestion: Go
- Control-plane API: FastAPI
- Database: PostgreSQL/PostGIS
- Streaming backbone: NATS JetStream
- Cache and short-lived state: Redis
- Web: Next.js/TypeScript and, later, MapLibre
- Local development: Docker Compose

The web application is a user interface, not the real-time correction transport. See [docs/README.md](docs/README.md) for architecture and operating notes.

## Quick start

Prerequisites: Ubuntu-compatible Linux, Git, Python 3.12+, Go 1.24+, a C/C++ compiler, CMake 3.25+, Node.js 20+, Docker, and Docker Compose.

```bash
cp .env.example .env
make setup
make up
make check
make health
```

Stop services with `make down`. `make setup` installs repository-local dependencies and never installs system packages or overwrites `.env`.

External RTKLIB and PRIDE PPP-AR installation is deliberately separate; see `tools/`.
