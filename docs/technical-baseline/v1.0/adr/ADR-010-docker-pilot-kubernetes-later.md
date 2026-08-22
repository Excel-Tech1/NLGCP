# ADR-010-docker-pilot-kubernetes-later - Docker Compose for pilot; Kubernetes only at justified scale

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Avoid Kubernetes during research/pilot; adopt when multi-node/multi-region operational needs justify it.

## Rationale
Reduces premature infrastructure complexity.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
