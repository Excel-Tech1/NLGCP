# Phase 1 Architecture Boundaries

```text
apps/web  -> user experience only
apps/api  -> control-plane API

services/gnss-ingestor   -> future incoming approved CORS/RTCM streams
services/nrtk-engine     -> future validated scientific processing
services/correction-service -> future output/session orchestration
NTRIP                    -> future correction distribution
```

The web and API control plane must not carry production correction streams. PostgreSQL/PostGIS stores durable structured metadata, NATS JetStream is the streaming backbone, Redis holds cache or short-lived state, and scientific observations belong in immutable/object storage rather than Redis or Git.

Phase 1 implements only process/toolchain health. It excludes GNSS processing, RTCM encoding, NTRIP, live CORS access, VRS, authentication, and billing.
