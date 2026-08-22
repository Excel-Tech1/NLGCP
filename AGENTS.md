# NLGCP Agent Instructions

These instructions apply to the entire repository.

## Start and finish every task

1. Read this file, `CURRENT_WORK.md`, `PROJECT_STATUS.md`, and relevant `docs/`.
2. Inspect `git status`, the latest commit, and the existing implementation.
3. Preserve working code and do not duplicate completed components.
4. Run tests and checks appropriate to the change.
5. Update `CURRENT_WORK.md`, `PROJECT_STATUS.md`, and `EVIDENCE_INDEX.md` when their facts change.

Codex and OpenCode may alternate. Continue the recorded handoff rather than recreating work, and update the handoff before stopping. Only one primary implementation agent should modify the active branch at a time unless explicit parallel work has been authorised.

## Scientific integrity

Do not invent GNSS mathematics.

Do not fabricate observations.

Do not claim RTK accuracy without validation.

Do not change geodetic reference frames silently.

Do not modify raw GNSS data.

Use RTKLIB for validated RTK functionality where documented.

Use PRIDE PPP-AR for precise offline processing and independent validation where documented.

Scientific calculations must be reproducible.

Unavailable external services must remain explicit dependencies.

Synthetic fixtures must be labelled `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`. Never silently substitute synthetic inputs for unavailable observations. Do not add scientific thresholds without documented evidence and review.

## Repository and security rules

- Never commit secrets, private keys, `.env`, real NTRIP credentials, or large GNSS datasets.
- Treat `data/raw/` as immutable. Derived output belongs outside it.
- Keep the control plane separate from real-time correction transport.
- Do not add Kubernetes, billing, production authentication, live NIGNET integration, correction streaming, NRTK/VRS algorithms, or scientific processing during Phase 1.
- Prefer focused dependencies and reproducible commands. Document external dependencies explicitly.
- Scientific GNSS changes require the review and evidence described in `CONTRIBUTING.md`.
