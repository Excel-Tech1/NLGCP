# ADR-001-source-independent-ingestion - Source-independent GNSS ingestion

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
All station providers map into a canonical observation and metadata model. NIGNET remains strategically preferred for national geodetic anchoring, but provider-specific formats/endpoints stay inside adapters.

## Rationale
Prevents vendor/provider lock-in and supports densification from partner/platform-owned CORS.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
