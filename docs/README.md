# Documentation Index

The technical documentation supplied for NLGCP is authoritative. Add documents under the appropriate heading without rewriting established decisions silently.

| Area | Documents |
|---|---|
| Product | Root `README.md`, `PROJECT_STATUS.md` |
| GNSS science | `scientific-integrity.md`, `../tools/README.md` |
| Data architecture | `../data/README.md`, `../storage/README.md` |
| System architecture | `architecture.md` |
| NRTK/VRS | Future Phase 5–7 documentation |
| Real-time streaming | `streaming-conventions.md` |
| Platform | `architecture.md` |
| Security | `../SECURITY.md` |
| Infrastructure | `../infrastructure/README.md` |
| Observability | Future Phase 14 documentation |
| Testing | `../tests/README.md` |
| Operations | `development.md` |
| Research | `../research/README.md` |
| Roadmap | `../PROJECT_STATUS.md` |
| UI/UX | `../apps/web/` foundation; detailed design deferred |

---

## Authoritative NLGCP Technical Baseline

The complete NLGCP technical architecture baseline is located at:

    docs/technical-baseline/v1.0/

It contains:

- 24 core technical specifications
- 12 Architecture Decision Records
- architecture diagrams
- operational runbooks
- machine-readable schemas
- standards and source register
- documentation completion register

### Authority

For system architecture, GNSS processing, data architecture, NRTK/VRS,
RTCM/NTRIP, security, infrastructure, scientific validation, and
operations, the documents under:

    docs/technical-baseline/v1.0/

are the authoritative baseline unless a later approved ADR or versioned
technical document explicitly supersedes them.

### Mandatory Agent Reading Order

Before modifying code, implementation agents must read:

1. `AGENTS.md`
2. `CURRENT_WORK.md`
3. `PROJECT_STATUS.md`
4. `docs/README.md`
5. `docs/scientific-integrity.md`
6. Technical documents relevant to the active phase
7. Relevant ADRs

Agents must not load all technical documents unnecessarily. Prompts should
identify the documents relevant to the active phase.

### Technical Documents

Core technical specifications:

    docs/technical-baseline/v1.0/docs/

Architecture Decision Records:

    docs/technical-baseline/v1.0/adr/

Operational runbooks:

    docs/technical-baseline/v1.0/runbooks/

Scientific/data schemas:

    docs/technical-baseline/v1.0/schemas/

Architecture diagrams:

    docs/technical-baseline/v1.0/diagrams/

### Scientific Integrity

No implementation agent may:

- invent GNSS equations;
- fabricate observations or station metadata;
- invent reference frames or coordinates;
- claim RTK FIX without verified solution status;
- claim centimetre accuracy without independent validation;
- silently modify raw GNSS observations;
- substitute synthetic data for unavailable real observations without
  explicitly identifying it as synthetic test data.

