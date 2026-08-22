# ADR-006-postgresql-postgis - PostgreSQL + PostGIS as authoritative structured store

**Status:** Accepted  
**Date:** 2026-08-21

## Context
This decision is part of the NLGCP baseline architecture and must remain stable unless implementation or field evidence demonstrates a material problem.

## Decision
Use one relational/spatial database for station metadata, cells, users, sessions and audit.

## Rationale
Spatial routing and relational integrity belong together.

## Consequences
- Implementations and tests shall conform to this decision.
- A future reversal requires a superseding ADR with migration and validation impact.
- Scientific results already produced under this decision remain reproducible through pinned versions/configuration.
