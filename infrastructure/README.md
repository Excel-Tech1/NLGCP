# Infrastructure

`compose.yml` supplies Phase 1 development services bound to loopback: PostgreSQL/PostGIS, NATS with JetStream, Redis, and the API. Defaults are not production credentials. Copy `.env.example` to `.env` and choose local values before starting.

The subdirectories reserve reviewed Docker additions, compose overrides, and monitoring configuration; Kubernetes and production deployment are out of Phase 1 scope.
