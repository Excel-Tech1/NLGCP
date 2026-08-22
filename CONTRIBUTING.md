# Contributing

Use short-lived branches and focused commits. Pull requests must explain scope, risk, tests, documentation changes, and evidence. Run `make check` before requesting review and update project tracking when phase facts change. Never commit secrets, `.env`, credentials, raw observations, or large generated data.

## Review levels

- **Level 1 — ordinary software:** normal review and relevant automated tests.
- **Level 2 — GNSS infrastructure:** domain-aware review, integration tests, failure-mode analysis, and operational documentation.
- **Level 3 — scientific GNSS algorithms:** literature/reference verification, tests, a known and legally usable dataset, reproducible configuration, and independent scientific validation.

Reference-frame, station-coordinate, observation-processing, ambiguity, atmospheric, interpolation, or accuracy changes are Level 3 unless reviewers document why they are not. Synthetic tests must be clearly labelled and cannot substantiate scientific performance.
