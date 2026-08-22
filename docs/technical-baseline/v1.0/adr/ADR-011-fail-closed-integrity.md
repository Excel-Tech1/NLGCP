# ADR-011-fail-closed-integrity - Fail closed on correction integrity

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Suppress/downgrade high-precision service when scientific integrity cannot be established.

## Rationale
Incorrect precision is more harmful than declared unavailability.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
