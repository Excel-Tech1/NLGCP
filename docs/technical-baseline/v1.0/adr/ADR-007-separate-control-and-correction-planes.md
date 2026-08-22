# ADR-007-separate-control-and-correction-planes - Separate web control plane from correction data plane

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
NTRIP corrections do not transit the web frontend/API per epoch.

## Rationale
Web outages must not cause scientifically valid correction streams to fail.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
