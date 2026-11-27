# B-05 Causal Atmospheric Filter Validation Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-05 — Causal Processing Validation  
**Date:** 2026-11-26  
**Classification:** `IMPLEMENTED` | `UNIT_TESTED` (`6/6` PASS) | `INDEPENDENTLY_VALIDATED` | Operational Status: `NOT_APPROVED`

---

## 1. Objective

Validate strictly causal epoch-by-epoch atmospheric estimators (`CausalIonoFilter`, `CausalNetworkDiffIonoTracker`, and `CausalTropoZwdFilter`) against Phase 6 offline full-arc baselines and 54 authentic PRIDE PPP-AR 3.2.8 ZTD station-days, quantifying early-arc transient loss, steady-state convergence, outage relaxation, and deterministic prefix invariance.

---

## 2. Causality Guarantees & Architectural Controls

| Requirement (Section 6.3) | Ionosphere Implementation (`causal_iono.py`) | Troposphere Implementation (`causal_tropo.py`) | Verification |
|---|---|---|---|
| Zero future leakage | `process_epoch(ep_k, ...)` reads only `<= k` state | `predict_at(ep_k)` before `update(ep_k)` | Bit-identical prefix-invariance unit tests (`test_causal_iono.py`, `test_causal_tropo.py`) |
| Explicit filter state & variance | `_CausalSatState` (`w_sum`, `w2_sum`, `level_mean_tecu`, `leveling_sigma_tecu`) | `CausalTropoState` (`residual_zwd_est_m`, `residual_zwd_sigma_m`) | `UNIT_TESTED` |
| Cycle-slip reset logic | Welford MW (`4σ`, floor `0.75 m`) + GF (`0.25/0.35 m`) + LLI/gap -> `_reset_arc()` | N/A (zenith parameter) | `UNIT_TESTED` + real 2011/2024 slip counts recorded |
| Outage / time-gap handling | Gap `> 1.5 * nominal_step_s` resets arc; bounded `deque` for ROTI | Exponential decay `phi = exp(-dt/7200)` toward UNB3m; `stale = True` when `dt > 900 s`; variance relaxes to `prior_sigma^2` | `UNIT_TESTED` (3-hour gap test) |
| Station-health gating | Missing dual-frequency / LLI bit-2 / epoch_flag != 0 skipped fail-closed | `station_healthy=False` ignores outlier spikes (`0.999 m` rejected) without advancing `sample_count` | `UNIT_TESTED` |
| Bounded memory & deterministic replay | `O(N_sat)` state per station; sorted satellite/station iteration | `O(1)` scalar state per station | Deterministic across runs |

---

## 3. Causal vs. Offline Ionospheric Performance Gap (Authentic Data)

Evaluated on identical `(epoch, satellite, station)` keys across 4 authentic days (`stride = 4`, `120 s` step, `720` epochs/day) using B-04 verified `IGS05`/`IGS08` coordinates (2011) and verified `IGS20` coordinates (2024):

| Dataset | Stations | Pair-Arc Common Samples | Causal vs. Offline Pair-Arc All RMSE (m) | Early Arc (`<=15` ep) RMSE (m) | Steady Arc (`>15` ep) RMSE (m) | Leveled vs. Nighttime Common Samples | Causal Leveled vs. Offline Nighttime RMSE (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `2011-03-20` (Equinox) | 9 (`IGS05`) | 44,090 | `0.5090` | `0.9587` | `0.4277` | 45,153 | `0.2681` |
| `2011-03-21` (Equinox) | 9 (`IGS05`) | 43,353 | `0.3699` | `0.6622` | `0.3173` | 44,523 | `0.2957` |
| `2011-12-05` (Harmattan) | 8 (`IGS08`) | 33,234 | `0.7568` | `1.1877` | `0.6961` | 33,989 | `0.4030` |
| `2024-01-26` (Sparse) | 4 (`IGS20`) | 15,597 | `0.7813` | `1.1693` | `0.7213` | 15,996 | `0.4575` |

### Key Observation on Spatial Interpolation Parity
Despite the expected arc-level offset difference between causal running-mean leveling and offline full-arc median leveling (`0.37–0.78 m` overall, `0.66–1.19 m` during initial 15-epoch convergence), **spatial interpolation performance inside the convex hull is preserved virtually without loss**:

| Dataset | Offline Pair-Arc Interior Best (`gain %`) | Causal Pair-Arc Interior Best (`gain %`) | Causal Leveled Interior Best (`gain %`) | Causal Interior 95% Block-Bootstrap CI (`ipp_idw2`) |
|---|---|---|---|---|
| `2011-03-20` | `idw2` `0.2595 m` (`+27.66%`) | **`ipp_idw2` `0.2392 m` (`+27.48%`)** | **`ipp_idw2` `0.3976 m` (`+27.31%`)** | **`[+24.30%, +30.72%]`** (`win=1.000`) |
| `2011-03-21` | `ipp_idw2` `0.3008 m` (`+29.89%`) | **`ipp_idw2` `0.2894 m` (`+30.35%`)** | **`ipp_idw2` `0.4188 m` (`+29.07%`)** | **`[+28.33%, +32.56%]`** (`win=1.000`) |
| `2011-12-05` | `idw2` `0.3263 m` (`+29.03%`) | **`ipp_idw2` `0.3041 m` (`+30.43%`)** | **`planar` `0.4239 m` (`+32.07%`)** | **`[+9.16%, +18.83%]`** (`win=1.000`) |
| `2024-01-26` | `zero` (perimeter only) | **`zero` (`0.6685 m`, perimeter)** | **`zero` (`0.9800 m`, perimeter)** | Perimeter CI `[-4.13%, -0.50%]` (`win=0.005`) |

---

## 4. Causal Tropospheric ZWD Filter Performance (`54` Station-Days)

Using strictly causal one-step prediction (`predict_at(t_k)` evaluated before `update(t_k)` at `120 s` intervals across `50` 2011 + `4` 2024 PRIDE PPP-AR ZTD station-days):

- **Static UNB3m climatology overall ZWD RMSE:** `0.1333 m` (`133.3 mm`)
- **Causal 1-step `CausalTropoZwdFilter` overall ZWD RMSE:** **`0.00363 m` (`3.63 mm`)**
- Daily station-mean causal 1-step RMSE: `2.79–2.87 mm` (March 2011), `3.48–4.07 mm` (December 2011), `2.52 mm` (`2024-01-26`).

---

## 5. Limitations, Unresolved Issues & Reproducibility

- **Real-Time Suitability Boundary:** Offline replay of a strictly causal algorithm proves architectural causality (`<= k`), **not** live real-time operational suitability. Live suitability requires real-time observation streams (B-09), real-time ZWD estimation (rather than feeding post-processed PRIDE ZTD), and live broadcast/SSR orbit latency testing.
- **Early-Arc Convergence:** Newly risen satellites or post-slip arcs exhibit `~2.1×` higher causal-vs-offline deviation in the first `15` epochs (`0.66–1.19 m` vs. `0.32–0.72 m` steady state), motivating explicit `arc_epoch_count` / `leveling_sigma_tecu` down-weighting in downstream VRS synthesis.
- **Reproducibility:**
  ```bash
  NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b05_atmospheric_sprint.py --stride 4
  ```
- **Next Steps:** Feed strictly causal B-05 VRS outputs directly into pinned RTKLIB rover positioning in **Milestone B-03** to quantify causal vs. offline positioning RMSE.
