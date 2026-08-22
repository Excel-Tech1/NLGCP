# ADR-004-go-ingestion - Go for persistent CORS ingestion

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Use Go for long-lived stream adapters and endpoint health.

## Rationale
Concurrency and simple deployment suit many simultaneous station connections.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
