# ADR-005-nats-jetstream - NATS JetStream for internal real-time event backbone

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Use NATS for low-latency pub/sub plus bounded persistence/replay.

## Rationale
Separates ingestion from processing/archive/monitoring consumers.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
