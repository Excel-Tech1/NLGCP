# ADR-009-immutable-raw-archive - Immutable raw GNSS archive

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Preserve source RINEX/RTCM and create derived artefacts separately.

## Rationale
Enables replay, audit and research reproducibility.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
