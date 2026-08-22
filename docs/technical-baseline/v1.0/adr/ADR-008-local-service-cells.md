# ADR-008-local-service-cells - Regional/local NRTK cells instead of one nationwide network model

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Model corrections in validated cells and coordinate them nationally.

## Rationale
Sparse national geometry and atmospheric variability make one monolithic interpolation surface inappropriate.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
