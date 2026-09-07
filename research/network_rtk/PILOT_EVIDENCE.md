# Phase 5 Pilot — Lightweight Evidence Summary

`SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS` does not apply:
values below are observed outputs of the real-data pilot. Large solution
files (`.pos`, per-epoch CSVs) remain outside Git under
`${NLGCP_DATA_ROOT}/processed/network-rtk/`; only this summary is tracked.

## Experiment

- `net-2024d026-phri-rover` — 2024 DOY 026, static, IGS20
- References: ABFC00NGA, EKAK00NGA, MGBO00NGA (all `network_rtk` ACCEPT)
- Rover: PHRI00NGA (`network_rtk` ACCEPT)
- Navigation: `external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz`
- Common overlap: 2024-01-26T00:00:00Z .. 2024-01-26T23:59:30Z, 2880 epochs
- RTKLIB `rnx2rtkp v2.4.2-p13`, SHA `b4a96cd0…f7d21` (matches Phase 1)

## Geometry

- EKAK→PHRI 105.553 km (nearest), ABFC→PHRI 470.870 km, MGBO→PHRI 1029.034 km
- Mean reference distance 535.152 km, extent 1029.034 km
- Reference triangle area 1.5659e11 m²

## Baseline solutions (network INPUTS, not a network correction)

| Baseline | Dist (km) | Epochs | Availability | FIX | FLOAT | TTFF | Horiz RMSE (m) | Vert RMSE (m) | 3D RMSE (m) |
|---|---|---|---|---|---|---|---|---|---|
| ABFC→PHRI | 470.870 | 2880 | 100% | 0 | 2880 | — | 1.093 | 1.254 | 1.664 |
| EKAK→PHRI | 105.553 | 2880 | 100% | 0 | 2880 | — | 0.968 | 0.584 | 1.130 |
| MGBO→PHRI | 1029.034 | 2880 | 100% | 2 | 2878 | 71280 s | 1.802 | 1.871 | 2.598 |

ABFC→PHRI and EKAK→PHRI reproduce the Phase 3 benchmark/control values
exactly. MGBO→PHRI shows 2 isolated late-day FIX epochs (fix rate
0.0007); no ambiguity-resolution success is claimed — the outcome is
effectively FLOAT-only under the tested configuration.

## Network-input aggregate (NOT a VRS solution)

- Mean horizontal RMSE 1.288 m, mean 3D RMSE 1.797 m, mean availability 100%
- Inter-baseline consistency (std of horizontal RMSE) 0.367 m
- Nearest single reference (EKAK, 0.968 m) outperforms the mean of the
  three independent baselines (1.288 m): **no network improvement is
  claimed**. The mean is degraded by the 1029 km baseline, as expected.

## Real-data availability

Only DOY 026 of the canonical 2024 archive admits ≥3 `network_rtk`
sessions. All other days are `BLOCKED` with recorded reasons — a valid
scientific result, not a defect.
