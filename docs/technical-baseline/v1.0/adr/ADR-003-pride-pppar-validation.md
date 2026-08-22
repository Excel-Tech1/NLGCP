# ADR-003-pride-pppar-validation - PRIDE PPP-AR for precise offline validation

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Use PRIDE PPP-AR for station coordinate solutions and independent precise validation, not as the primary live NTRIP/VRS engine.

## Rationale
Separates PPP-AR strengths from the local NRTK operational path.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
