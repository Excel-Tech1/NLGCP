# Interim Scientific Expansion Sprint Toolkit

Toolkit for the one end-to-end multi-day 2024 validation sprint
(Stages A/B/C/D/E/F/G). It builds coverage matrices, multi-station overlap,
navigation acquisition plans, processable-day catalogs, and the evidence-
derived final report. RTK estimation, QC admission, and spatial modelling
remain in the Phase 3/4/5/6 packages with frozen gates; this package only
orchestrates and reports their stored evidence.

Outputs are written under:

```text
${NLGCP_DATA_ROOT}/validation/scientific-expansion-2024/
```

Synthetic tests are explicitly labelled and are not scientific evidence.

The CLI is intentionally staged:

```text
coverage -> overlap -> plan-nav -> fetch-nav -> verify-nav -> catalog -> report
```

`fetch-nav` is the only network-touching command. `report` reads only stored
data-root artefacts and writes `reports/scientific-expansion-report.md`.
