# ADR-012-hybrid-vrs-single-base - Hybrid VRS primary, single-base eligible fallback

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Prefer VRS in healthy validated cells; allow single-base only within empirically validated constraints.

## Rationale
Directly implements the research objective and provides resilience without hiding network failure.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
