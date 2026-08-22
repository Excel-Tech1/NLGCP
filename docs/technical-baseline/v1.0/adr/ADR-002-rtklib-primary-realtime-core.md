# ADR-002-rtklib-primary-realtime-core - RTKLIB as primary real-time GNSS foundation

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Use RTKLIB and selected custom C/C++ modules for standard RTK/stream/RTCM/NTRIP GNSS functionality.

## Rationale
Matches the RTK/VRS research problem and avoids rebuilding baseline GNSS mechanics.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
