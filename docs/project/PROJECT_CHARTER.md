# NLGCP Project Charter

**Project Name:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Repository:** `/home/excellence/NLGCP`
**External Research Data Root:** `/home/excellence/nlgcp-data`
**Authoritative Baseline:** [`docs/technical-baseline/v1.0/`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/)
**Last Updated:** 2026-11-26

---

## 1. Mission and Scope

The Nigeria GNSS Localised Correction Platform (NLGCP) is a long-term scientific research and systems engineering initiative designed to investigate, validate, and eventually deliver traceable, high-integrity GNSS differential positioning corrections tailored to Nigerian equatorial ionospheric and tropical tropospheric conditions.

NLGCP operates under two strictly coupled tracks:

1. **Scientific Research Track:** Empirically evaluate single-base RTK, offline Network RTK (NRTK), Nigerian ionospheric and tropospheric spatial modelling, Virtual Reference Station (VRS) synthesis, and rover positioning accuracy using authentic Nigerian GNSS observations (NIGNET/OSGoF) and independent reference processing engines (`RTKLIB v2.4.2-p13`, `PRIDE PPP-AR 3.2.8`, `ESA/gAGE-UPC gLAB v6.0.0`).
2. **Correction Platform Engineering Track:** Build clean, modular, fail-closed ingestion, replay, hybrid decision, RTCM 3.x encoding, and NTRIP distribution services with strict separation between control-plane APIs and real-time correction transport.

---

## 2. Non-Negotiable Governance & Scientific Integrity Principles

Every engineering and research milestone obeys [`AGENTS.md`](file:///home/excellence/NLGCP/AGENTS.md), [`CONTRIBUTING.md`](file:///home/excellence/NLGCP/CONTRIBUTING.md), and the v1.0 technical baseline:

1. **No Fabricated Evidence:** Observations, hashes, software versions, coordinates, accuracy metrics, FIX rates, and external products are never fabricated. Unavailable data is recorded explicitly (`UNKNOWN`, `NOT_AVAILABLE`, `BLOCKED`).
2. **Immutable Raw Observations:** Original RINEX, navigation, SP3, and raw delivery files under `/home/excellence/nlgcp-data` (`incoming/`, `00-deliveries/`, `raw/`) are read-only research evidence (`ADR-009`).
3. **Strict Authentic vs. Synthetic Separation:** Synthetic test data is explicitly labelled `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS` and programmatically blocked from contaminating authentic scientific experiments.
4. **Fail-Closed Integrity (`ADR-011`):** Every quality-control, spatial-model promotion, VRS admission, RTCM encoding, and NTRIP publication boundary fails closed when evidence, coordinates, or provenance are incomplete.
5. **Evidence-Based Phase Advancement:** Compilation, unit tests, and RTCM wire decoding are never conflated with scientific positioning validation or operational approval. `OPERATIONAL_APPROVED = FORBIDDEN` remains enforced until all scientific, security, interoperability, and field blockers (`B-01`–`B-10`) are formally resolved.

---

## 3. Governance Artifacts & Single Authorities

- **Engineering & Scientific Rules:** [`AGENTS.md`](file:///home/excellence/NLGCP/AGENTS.md)
- **Technical Baseline & ADRs:** [`docs/technical-baseline/v1.0/`](file:///home/excellence/NLGCP/docs/technical-baseline/v1.0/) and [`TECHNICAL_DECISION_REGISTER.md`](file:///home/excellence/NLGCP/docs/project/TECHNICAL_DECISION_REGISTER.md)
- **Project Status Authority:** Root [`PROJECT_STATUS.md`](file:///home/excellence/NLGCP/PROJECT_STATUS.md) (mirrored and indexed by [`docs/project/PROJECT_STATUS.md`](file:///home/excellence/NLGCP/docs/project/PROJECT_STATUS.md))
- **Active Handoff & Evidence Log:** [`CURRENT_WORK.md`](file:///home/excellence/NLGCP/CURRENT_WORK.md) and [`EVIDENCE_INDEX.md`](file:///home/excellence/NLGCP/EVIDENCE_INDEX.md)
- **Machine-Readable Research Archive:** [`research/archive/`](file:///home/excellence/NLGCP/research/archive/) verified read-only via `nlgcp archive verify`
