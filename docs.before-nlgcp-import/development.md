# Development Setup

From the repository root:

```bash
cp .env.example .env
make setup
make up
make check
make health
```

`make setup` checks prerequisites and installs a local Python virtual environment and web dependencies. It does not install system packages, use root, or overwrite `.env`. `make up` starts local-only PostgreSQL/PostGIS, NATS JetStream, Redis, and the API. Stop them with `make down`.

Use `make api` and `make web` for host development. The Go and C/C++ services are Phase 1 toolchain foundations and are tested through `make check`.
