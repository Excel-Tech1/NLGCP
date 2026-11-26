# B-02 Offline Rover Positioning Benchmark for Experimental VRS Corrections

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Milestone:** B-02 — Offline Rover Positioning Benchmark
**Date:** 2026-11-26
**Branch / Revision:** `research/nlgcp-14-day-beta-sprint` (HEAD `0cea5bade59a1e623505c33351fdb33cad8b1282`, dirty working tree preserving Day 7, Phase 6/7, and B-02 work)
**Benchmark Runner Version:** `b02-rover-benchmark-v1.0` (`scripts/run_b02_rover_benchmark.py`)
**RTKLIB Provenance:** Pinned unmodified `v2.4.2-p13` (commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`), `rnx2rtkp` SHA-256 `b4a96cd0…4f7d21`, `convbin` SHA-256 `b575f81e…08e278`
**Machine-Readable Evidence:** `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/` (`311` SHA-256-hashed output artifacts)
**Validation Verdict:**
- **Dataset B (`2024-01-26`, `PHRI00NGA`, verified IGS20 truth, 3-ref extrapolation):** `EXPERIMENTALLY_VALIDATED` for modest static FLOAT (`+8.23%` horizontal RMSE, 95% CI `[+0.047, +0.121] m`) and kinematic 3D FLOAT (`+14.14%`) improvement; kinematic horizontal gain (`+5.70%`, 95% CI `[-0.085, +0.240] m`) is statistically inconclusive under 3-station extrapolation; **RTK FIX = `0.0%` (`0 / 2,880` epochs)**.
- **Dataset A (`2011-03-20`, `OSGF`, interior 8-ref convex hull, provisional truth only):** `TECHNICALLY_VALIDATED` / exploratory (provisional coordinate truth blocks verified-accuracy promotion); atmospheric VRS (`vrs_ipp_idw2_unb3m`) slashed kinematic horizontal RMSE by **`+56.65%`** (`1.456 → 0.631 m`, 95% CI `[+0.590, +1.015] m`, epoch win rate `97.5%`), static horizontal RMSE by **`+57.06%`** (`0.917 → 0.394 m`), and truth-independent centered horizontal scatter by **`-57.2%`** (`1.452 → 0.622 m`); **genuine RTK FIX = `0.0%`** (7 transient `Q=1` epochs on non-ionospheric variants were confirmed wrong-integer false fixes with `1.30–2.43 m` horizontal error).
- **Operational Approval:** **`OPERATIONAL_APPROVED = FORBIDDEN`** (operational Phase 6 remains `BEST = ZERO`; operational Phase 7 remains `VRS_GEOMETRY_ONLY`; `NLGCP_VRS_EXP` stays strictly isolated from `NLGCP_TEST`).

---

## 1. Executive Summary

This benchmark resolves **Blocker B-02** from the Phase 6/7 sprint by moving beyond RTCM decoding and held-out observation residuals to **actual offline rover positioning** using pinned **RTKLIB `v2.4.2-p13` (`convbin` + `rnx2rtkp`)** across two full-24-hour (`2,880` epochs at `30.0 s`) authentic Nigerian dual-frequency GPS datasets:

1. **Does atmospheric experimental VRS improve rover positioning in actual RTKLIB solutions?**
   - **Yes — decisively inside a multi-station convex hull (`2011-03-20` interior `OSGF`, 8 refs, 216.32 km anchor), and modestly under sparse 3-station extrapolation (`2024-01-26` verified `PHRI00NGA`, 105.55 km anchor), strictly in FLOAT / DGPS modes.**
   - On **verified-IGS20 `2024-01-26` `PHRI00NGA`** (outside the 3-reference convex hull), `vrs_idw2_unb3m` improved static FLOAT horizontal RMSE by **`+8.23%`** (`0.9677 → 0.8881 m`, 95% block-bootstrap CI `[+0.0468, +0.1213] m`, winning `94.8%` of epochs) and 3D RMSE by **`+8.14%`** (`1.1301 → 1.0382 m`). In kinematic FLOAT mode, `vrs_idw2_unb3m` improved 3D RMSE by **`+14.14%`** (`2.5449 → 2.1851 m`), vertical RMSE by **`+17.37%`**, and median horizontal error by **`-29.0%`** (`0.4879 → 0.3464 m`), while eliminating all `>5 m` outliers (`9 → 0`); however, full-day kinematic horizontal RMSE gain (`+5.70%`, `1.3074 → 1.2329 m`, 95% CI `[-0.0847, +0.2399] m`) crosses zero because of `00–06 UTC` extrapolation errors and `-0.53` fewer satellites/epoch (`8.06 → 7.53`).
   - On **interior-hull `2011-03-20` `OSGF`** (inside the 8-reference convex hull, `99.95%` satellite-count parity at `8.01` vs `8.02` sats/epoch), `vrs_ipp_idw2_unb3m` cut kinematic FLOAT horizontal RMSE by **`+56.65%`** vs physical anchor `CGGT` (`1.4562 → 0.6313 m`, 95% CI `[+0.5899, +1.0148] m`, winning `97.5%` of epochs) and **`+57.50%`** vs geometry-only VRS (`1.4854 → 0.6313 m`), cut static FLOAT horizontal RMSE by **`+57.06%`** (`0.9166 → 0.3935 m`, `100.0%` win rate vs geometry-only), and cut truth-independent horizontal scatter (`horiz_centered_rms_m`) by **`-57.2%`** (`1.4521 → 0.6218 m`), proving the gain is real and not an artifact of provisional OSGoF coordinates. In pure code-differential DGPS, `vrs_nighttime_ipp_idw2_unb3m` cut horizontal RMSE by **`+45.38%`** (`0.7891 → 0.4310 m`, `>2 m` epochs cut `52 → 0`).
2. **Does the current experimental VRS support genuine rover RTK integer ambiguity resolution (FIX)?**
   - **No. Genuine centimetre RTK FIX rate is `0.0%` across every dataset, variant, and carrier-phase profile.**
   - All `2024` solutions were `100.0%` FLOAT (`0 / 2,880` FIX, max LAMBDA ratio `1.7–2.6 < 3.0`).
   - On `2011`, all atmospheric VRS and physical-anchor solutions were `100.0%` FLOAT (`0 / 2,880` FIX). The only `Q=1` flags (`2` epochs on `vrs_zero_geom_only`, `5` epochs on `vrs_tropo_unb3m_only`) were inspected epoch-by-epoch and confirmed to be **wrong-integer false fixes** with `1.30–2.43 m` horizontal errors (`1.30–3.89 m` 3D).
   - This confirms that `ANCHOR_RELATIVE_FLOAT` VRS synthesis across `105–716 km` baselines without network integer ambiguity resolution (**B-03**) improves FLOAT and DGPS positioning substantially inside a hull, but **cannot deliver centimetre RTK FIX**.
3. **Engineering & scientific defects caught and fixed during B-02 execution:**
   - **RTKLIB parallel `.rnx.gz` decompression race:** Concurrent `rnx2rtkp` workers reading gzipped `BRDC00IGS_R_20240260000_01D_MN.rnx.gz` raced on RTKLIB's internal `uncompress()`, causing `no nav data` failures; resolved by decompressing once into derived storage while preserving the immutable `.rnx.gz` and logging both SHA-256 hashes.
   - **Real VRS tropospheric ZWD interpolation bug (`experimental_vrs.py:517`):** When `tropo_mode="network_ztd"` was combined with `spatial_model="zero"` (`vrs_tropo_pride_ztd_only`), `predict_spatial()` received `model_name="zero"`, setting target ZWD to `0.0 m` against `EKAK`'s `0.229 m` and injecting a spurious `+0.54–0.74 m` vertical position bias. Fixing line 517 to interpolate ZWD via `idw2` eliminated the bias (`2024` DGPS 3D RMSE dropped `1.4456 → 1.3419 m`, kinematic 3D RMSE dropped `2.9255 → 2.5546 m`) and is now covered by a unit regression test.
   - **Source-verified RTKLIB `v2.4.2-p13` relative atmospheric behavior (`src/rtkpos.c:883–885`):** `zdres()` unconditionally applies hydrostatic Saastamoinen + Niell regardless of `pos1-tropopt=saas` vs `off`, and `relpos()` ignores `pos1-ionoopt=brdc` — mechanistically explaining both why `kinematic_brdc_saas` and `kinematic_vrs_iono_off` produced bit-identical solutions and why `vrs_zero_geom_only` underperformed the physical anchor until differential troposphere (`UNB3m` or `network_ztd`) was restored in the VRS.

---

## 2. Research Objectives

B-02 evaluates whether NLGCP's observation-based experimental VRS corrections deliver measurable improvements in downstream rover ENU positioning accuracy and repeatability relative to:

1. **Configuration 1 — Physical-anchor single-base baseline** (distinct real reference station RINEX + verified/provisional ECEF).
2. **Configuration 2 — Geometry-only VRS (`vrs_zero_geom_only`)** (RTCM `1005 + 1074` stream with geometric + SV clock translation only).
3. **Configuration 3 — Atmospheric-model-assisted VRS** (`tropo`-only, `idw2`, `ipp_idw2`, and `nighttime`-leveled variants).
4. **Reference context — Standalone Single-Point Positioning (`spp_single`)**.

Throughout this report, the following six concepts remain strictly separated:
1. **Observation-level correction quality** (Phase 7 residual reductions — necessary, not sufficient).
2. **RTCM protocol correctness** (`convbin` / `input_rtcm3()` / gLAB decoding — proves wire validity, not positioning accuracy).
3. **Rover positioning performance** (ENU RMSE, median, P95, bias, and repeatability in `rnx2rtkp`).
4. **Ambiguity-resolution performance** (verified FIX rate, TTFF, ambiguity resets, and false-FIX inspection).
5. **Scientific validation** (requires defensible independent truth, zero leakage, and reproducible statistical evidence).
6. **Operational readiness** (requires B-01 through B-10 closure; remains `FORBIDDEN`).

---

## 3. Dataset Selection

Full screening and manifest details are documented in [b02_rover_dataset_selection.md](file:///home/excellence/NLGCP/docs/research/b02_rover_dataset_selection.md) and `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/dataset_manifest.json` (SHA-256 `61acf424…8e254b`).

| Dataset | Date / DOY | Withheld Rover | Reference Network (Rover Excluded) | Nearest Anchor & Baseline | Hull Geometry | Cadence & Epochs | Truth Classification |
|---|---|---|---|---|---|---|---|
| **Dataset B (Primary Verified Truth)** | `2024-01-26` / `026` | `PHRI00NGA` (`PHRI0260.24O`) | `ABFC00NGA`, `EKAK00NGA`, `MGBO00NGA` (3 refs) | `EKAK00NGA` (`105.553 km`) | **OUTSIDE** (extrapolation; `181,177.5 km²`) | `30.0 s`, `2,880 / 2,880` (`00:00:00–23:59:30 GPST`) | **`VERIFIED_IGS20_PPP_AR`** (`accuracy_claim_permitted = True`) |
| **Dataset A (Secondary Interior Hull)** | `2011-03-20` / `079` | `OSGF` (`OSGF0790.11O`, read-only from `NIGNET2011.zip`) | `ABUZ, BKFP, CGGT, FUTY, MDGR, RUST, ULAG, UNEC` (8 refs) | `CGGT` (`216.320 km`) | **INSIDE** (interpolation; `607,707.15 km²`) | `30.0 s`, `2,880 / 2,880` (`00:00:00–23:59:30 GPST`) | **`PROVISIONAL_OSGOF_LIMITED`** (`accuracy_claim_permitted = False`) |

### Preserved Phase 7 120-Second RTCM Stream Probes (Read-Only Traceability)

Before generating full-day 30-second streams, the two pre-existing Phase 7 streams under `/home/excellence/nlgcp-data/processed/vrs/sprint-phase67/` were preserved untouched and probed read-only via `convbin` + `rnx2rtkp` (`kinematic_brdc_saas`, `00:00:00–00:58:00 GPST`):

| Preserved Phase 7 File | SHA-256 (prefix) | Decoded Epochs | `rnx2rtkp` Valid | `FIX` | `FLOAT` | `SINGLE` | Resets | Max Age (s) | Horiz RMSE (m) | Vert RMSE (m) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `vrs_2024_01_26_phri_exp.rtcm3` | `d9eb20c31b3e740c` | `30` (120 s) | `117` | `0` | `59` | `58` | `29` | `90.0` | `1.4301` | `1.4851` |
| `vrs_2011_03_20_osgf_exp.rtcm3` | `e4f492655df99670` | `30` (120 s) | `117` | `0` | `59` | `58` | `29` | `90.0` | `1.0344` | `0.7816` |

Because Phase 7 used `stride=4` (`120 s` cadence), every intermediate `30 s` rover epoch exceeded RTKLIB's `pos2-maxage = 30 s` (`age_max = 90.0 s`), forcing `29` ambiguity resets and dropping `58 / 117` epochs to `SINGLE` (`Q=5`). Furthermore, Phase 7 encoded RTCM `1005` at the target station coordinate for observation-residual checks. B-02 therefore generated dedicated **full-24-hour `30.0 s` (`stride=1`, `2,880` epochs)** RTCM `1005 + 1074` streams placed at each rover's **autonomous epoch-0 SPP GGA position** so that `age = 0.0 s` at every epoch and coordinate leakage is strictly zero.

---

## 4. Rover Truth Establishment

| Attribute | Dataset B — `PHRI00NGA` (Verified Truth) | Dataset A — `OSGF` (Provisional Truth Only) |
|---|---|---|
| **Truth Tier** | **`VERIFIED_IGS20_PPP_AR`** | **`PROVISIONAL_OSGOF_LIMITED`** (`LIMITED_PROVISIONAL_TRUTH`) |
| **Verified Accuracy Claim Permitted?** | **Yes** | **No** (exploratory accuracy vs OSGoF + truth-independent repeatability) |
| **ECEF XYZ (m)** | `(6308877.98392, 772269.10256, 530087.60603)` | `(6246471.2000, 820848.7400, 994267.9300)` |
| **Reference Frame & Epoch** | `IGS20` at `2024-01-26T11:59:42Z` (`MJD 60335.4998`) | Undocumented ITRF realization; published epoch `2011-01-01` |
| **Antenna Model & ARP Delta H/E/N** | `TRM59900.00 NONE`, `(0.1710, 0.0000, 0.0000) m` | `TRM59800.00`, `(0.1710, 0.0000, 0.0000) m` (identical across all 9 stations) |
| **Processing Method & Uncertainty** | PRIDE PPP-AR 3.2.8 static daily solution (`45` fixed GPS amb, `26,065` obs; formal `σ_X/Y/Z = 0.55 / 0.16 / 0.13 mm`; realistic external ~5–15 mm) | OSGoF published coordinate table; formal uncertainty `UNKNOWN`; offline 2011 PPP `BLOCKED` (zero 2011 SP3/CLK/OSB products on disk) |
| **Precise Products & Biases** | `WUM0MGXRAP` `ORB.SP3`, `30S_CLK.CLK`, `30S_ATT.OBX`, `01D_OSB.BIA`, `01D_ERP.ERP`; `bias_products_available = True` | None on disk (`bias_products_available = False`) |
| **Source File SHA-256** | `7f62d2466fe9cf2df8acff390a97f4d85a8e456b27ba2b7b3bc9c6dafdc5965f` (`pos_2024026_phri`) | `e48cd164c4524dcd88692b93a4d5cb152dd16834889de2046c65530a07a14b1c` (`coordinate_provenance.csv`) |
| **RINEX Header Discrepancy (Rejected)** | `5.22 m` from PRIDE truth (strictly rejected) | `0.77 m` from OSGoF table (strictly rejected) |

---

## 5. Experiment Design and Fair-Comparison Controls

### Package Architecture
Implemented under `research/rover_benchmark/src/nlgcp_rover_benchmark/`:
- [`models.py`](file:///home/excellence/NLGCP/research/rover_benchmark/src/nlgcp_rover_benchmark/models.py): `TruthTier`, `BenchmarkOutcome`, `ProcessingProfile`, `RoverTruthRecord.validate()`, `DatasetWindowSpec`, `LeakageAuditResult`, and fail-closed `assert_no_rover_leakage()`.
- [`rtklib_pipeline.py`](file:///home/excellence/NLGCP/research/rover_benchmark/src/nlgcp_rover_benchmark/rtklib_pipeline.py): Pinned binary SHA-256 verification (`rtklib_tool_provenance`), RTCM 3.x pre-conversion framing/CRC-24Q validator, `convbin` RINEX 3.02 converter with header/epoch auditing, comparable config renderer (`render_profile_config`), deterministic CLI command builder (`build_rnx2rtkp_command`), and fail-closed `execute_rnx2rtkp()`.
- [`metrics.py`](file:///home/excellence/NLGCP/research/rover_benchmark/src/nlgcp_rover_benchmark/metrics.py): Reuses Phase 3's validated WGS84 ENU rotation (`nlgcp_single_base.coordinates`) and `.pos` parser (`nlgcp_single_base.solution`) to compute all 19 required positioning metrics, truth-independent repeatability, convergence checkpoints, 6-hour UTC time blocks, satellite-count bins, outlier summaries, and deterministic moving-block bootstrap (`40`-epoch / `20`-minute blocks, `500` iterations, fixed seed `20261125`) paired comparisons.
- [`benchmark.py`](file:///home/excellence/NLGCP/research/rover_benchmark/src/nlgcp_rover_benchmark/benchmark.py) & [`scripts/run_b02_rover_benchmark.py`](file:///home/excellence/NLGCP/scripts/run_b02_rover_benchmark.py): End-to-end reproducible runner executing both datasets, preserved Phase 7 probes, all 12 Phase H failure scenarios, and full SHA-256 artifact manifests.

### Strict Non-Leakage & GGA Virtual Position Protocol
For both datasets, `assert_no_rover_leakage()` verified all five guards (`passed = True`, `findings = []`):
1. `rover_station_id not in reference_coords`
2. `rover_station_id not in reference_datasets`
3. `rover_station_id not in iono_field_station_ids` (`common_arc` and `nighttime`)
4. `rover_station_id not in reference_ztd_station_ids` (`2024` PRIDE ZTD loaded strictly for `ABFC00NGA`, `EKAK00NGA`, `MGBO00NGA`)
5. `physical_anchor_id != rover_station_id`
6. **Zero truth-coordinate leakage into VRS synthesis:** Rather than passing `rover_truth.ecef_xyz_m` to the VRS generator, the benchmark first ran standalone `spp_single` on the rover and synthesized every VRS stream at the rover's **autonomous epoch-0 broadcast SPP coordinate** (simulating an authentic NTRIP NMEA GGA coordinate):
   - `2024 PHRI00NGA`: VRS virtual ARP = `(6308882.3625, 772268.6201, 530088.8002) m` — **`4.5641 m` offset** from verified PRIDE truth.
   - `2011 OSGF`: VRS virtual ARP = `(6246471.8550, 820849.0422, 994268.3595) m` — **`0.8395 m` offset** from provisional OSGoF coordinate.

---

## 6. Physical-Anchor Baseline

- **Dataset B (`2024-01-26`):** `EKAK00NGA` (`EKAK0260.24O`, SHA-256 `57e1917a…aabb9fc`, verified IGS20 ECEF `(6296841.3252, 875621.0042, 512343.1243) m`, `105.553 km` East of `PHRI00NGA`). In `static_brdc_saas`, `rnx2rtkp` produced **`H = 0.9677 m, V = 0.5838 m, 3D = 1.1301 m`** (`2,880/2,880` FLOAT), reproducing Phase 3's recorded `EKAK→PHRI` control (`0.968 / 0.584 / 1.130 m`) to the fourth decimal place.
- **Dataset A (`2011-03-20`):** `CGGT` (`CGGT0790.11O`, SHA-256 `95f3bad2…dba06672`, provisional OSGoF ECEF `(6201034.2300, 995277.3100, 1113817.4300) m`, `216.320 km` NE of `OSGF`, altitude `917 m` vs `OSGF` `533 m`).

---

## 7. Geometry-Only VRS (`vrs_zero_geom_only`)

- Synthesized from the nearest physical anchor using exact light-time + Sagnac geometric range translation and broadcast SV clock difference (`spatial_model="zero"`, `tropo_mode="zero"`), encoded to RTCM `1005 + 1074` (`2,881` frames: `1×1005 + 2,880×1074`), and decoded to RINEX 3.02 via `convbin`:
  - `2024 PHRI`: `417,994 B`, SHA-256 `9e1f568f…ca21ad`, `23,308` obs, `2,880/2,880` decoded epochs, `89` integer arc offsets, `0` excluded RTCM cells.
  - `2011 OSGF`: `414,641 B`, SHA-256 `6923955d…de19fd8`, `23,083` obs, `2,880/2,880` decoded epochs, `89` integer arc offsets, `0` excluded RTCM cells.
- **Critical physical finding:** Geometry-only VRS consistently **underperformed** the physical anchor (`2024` DGPS `-8.41%` H, kinematic `-13.02%` H; `2011` DGPS `-14.98%` H, static `-25.28%` H, kinematic `-2.00%` H / `-10.25%` V). Source inspection of RTKLIB `v2.4.2-p13` (`src/rtkpos.c:883–885`) proved why: RTKLIB's `zdres()` unconditionally removes the hydrostatic Saastamoinen + Niell delay at both rover and base positions. For a `105–216 km` physical baseline, RTKLIB automatically removes the differential hydrostatic delay (including `CGGT`'s `384 m` elevation offset and `EKAK`'s `105 km` East-West mapping-function difference). When a geometry-only VRS places a virtual station `0.8–4.6 m` from the rover without applying differential troposphere, RTKLIB's hydrostatic cancellation drops to `~0`, exposing the full unmodeled differential hydrostatic delay as a position bias (`-0.354 m` East in `2024` DGPS; `+0.890 m` Up in `2011` kinematic).

---

## 8. Atmospheric-Model-Assisted VRS Variants

Every atmospheric VRS stream passed RTCM 3.x framing/CRC-24Q validation (`0` CRC errors, `0` truncated frames, `0` excluded RTCM cells) and `convbin` RINEX 3.02 decoding (`2,880 / 2,880` epochs preserved; `APPROX POSITION XYZ` exact to `0.0000 m`):

| Dataset | Variant ID | Ionosphere Model | Troposphere Model | Obs | RTCM Bytes | RTCM SHA-256 (prefix) | Arc Offsets | Mean Sats in `rnx2rtkp` |
|---|---|---|---|---:|---:|---|---:|---:|
| `2024 PHRI` | `vrs_tropo_unb3m_only` | `zero` | `unb3m` | `23,308` | `417,994` | `c0a109fdad4a8398` | `89` | `8.05` |
| `2024 PHRI` | `vrs_tropo_pride_ztd_only` | `zero` | `network_ztd` (3-ref IDW²) | `23,308` | `417,994` | `8295db3d2006762e` | `89` | `8.05` |
| `2024 PHRI` | `vrs_idw2_unb3m` | `idw2` (`common_arc`) | `unb3m` | `21,818` | `396,248` | `0c02c76345ff1c55` | `90` | `7.53` |
| `2024 PHRI` | `vrs_idw2_pride_ztd` | `idw2` (`common_arc`) | `network_ztd` (3-ref IDW²) | `21,818` | `396,248` | `bb068cac9a04639e` | `90` | `7.53` |
| `2024 PHRI` | `vrs_nighttime_idw2_pride_ztd` | `idw2` (`nighttime`) | `network_ztd` (3-ref IDW²) | `21,818` | `396,248` | `241e7bca08e7df7a` | `90` | `7.53` |
| `2011 OSGF` | `vrs_tropo_unb3m_only` | `zero` | `unb3m` | `23,083` | `414,641` | `b6a32d4dfc5c62ba` | `89` | `8.01` |
| `2011 OSGF` | `vrs_idw2_unb3m` | `idw2` (`common_arc`) | `unb3m` | `23,072` | `414,480` | `8b599a885e298674` | `86` | `8.01` |
| `2011 OSGF` | `vrs_ipp_idw2_unb3m` | `ipp_idw2` (`common_arc`) | `unb3m` | `23,072` | `414,480` | `4a0b867eac22dae4` | `86` | `8.01` |
| `2011 OSGF` | `vrs_nighttime_ipp_idw2_unb3m` | `ipp_idw2` (`nighttime`) | `unb3m` | `23,072` | `414,480` | `e41d63f1dfbf0253` | `86` | `8.01` |

Note: `2011` does not mix measured meteorology with modelled climatology (`UNB3m` climatology only, `ref_ztd = None`); `2024` separates `UNB3m` climatology from independent 3-reference PRIDE PPP-AR ZTD (`network_ztd`).

---

## 9. RTKLIB Configuration

All configurations within each profile used **identical** RTKLIB `v2.4.2-p13` settings (`pos1-navsys=1` GPS-only, `pos1-frequency=l1+l2`, `pos1-soltype=forward`, `pos1-elmask=15`, `pos2-arthres=3.0`, `pos2-maxage=30`, `stats-eratio1=100`, `out-solformat=llh`, `out-timesys=gpst`, `out-height=ellipsoidal`, explicit `ant2-postype=xyz` + `-r x y z`), differing only in the base observation input and its exact coordinate. Full templates and hashes are archived in `experiment_config.json` (SHA-256 `44d22f17…f1b`).

| Profile ID | `posmode` | `ionoopt` | `tropopt` | `armode` | Scientific Role |
|---|---|---|---|---|---|
| `spp_single` | `single` | `brdc` | `saas` | `off` | Standalone rover reference + epoch-0 GGA seed |
| `dgps_code_diff` | `dgps` | `off` | `off` | `off` | Pure pseudorange differential (isolates `C1/P2` atmospheric gain without phase ambiguity coupling) |
| `kinematic_brdc_saas` | `kinematic` | `brdc` | `saas` | `continuous` | Standard dual-frequency epoch-by-epoch RTK (code + carrier + LAMBDA AR attempt) |
| `kinematic_vrs_iono_off` | `kinematic` | `off` | `off` | `continuous` | Double-correction control; empirically bit-identical to `kinematic_brdc_saas` in RTKLIB `v2.4.2-p13` `relpos()` |
| `static_brdc_saas` | `static` | `brdc` | `saas` | `continuous` | Static carrier-phase accumulation baseline (reproduces Phase 3 `EKAK→PHRI` exact config) |

Direct raw `.rtcm3` consumption by `rnx2rtkp` was empirically tested and confirmed unsupported (`error : station pos computation`); all VRS streams therefore pass through unmodified RTKLIB `convbin -r rtcm3 -v 3.02 -f 3 -os -scan` while preserving every `.rtcm3` file as the primary evidence artifact.

---

## 10. Positioning Results

All `52` relative positioning runs and `2` SPP runs completed with **`2,880 / 2,880` valid epochs (`100.0%` availability)** and `time_to_first_valid_s = 0.0 s`. Because `kinematic_vrs_iono_off` produced values identical to `kinematic_brdc_saas` to the last digit across all 13 variants (verified mechanistically in `src/rtkpos.c:883–1110`), tables below show `kinematic_brdc_saas`, `static_brdc_saas`, and `dgps_code_diff`.

### 10.1 Dataset B — `2024-01-26` `PHRI00NGA` (`VERIFIED_IGS20_PPP_AR`, Extrapolated 3-Ref Network)

**Standalone SPP (`spp_single`):** `H RMSE = 3.0404 m`, `V RMSE = 5.3663 m`, `3D RMSE = 6.1678 m`, `Med H = 1.3876 m`, `P95 H = 7.1009 m`, `P95 V = 11.0753 m`, `Max H = 9.7023 m`, `Rep H = 2.5012 m`, `Sats = 8.16 (5–11)`.

#### Kinematic Relative (`kinematic_brdc_saas` & `kinematic_vrs_iono_off`, `n = 2,880`, `FIX = 0.0%`, `FLOAT = 100.0%`)

| Variant | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Med H (m) | P95 H (m) | P95 V (m) | Max H (m) | Post-30m H (m) | Rep H (m) | Sats | `>2m` / `>5m` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `physical_anchor_ekak00nga` | `1.3074` | `2.1834` | `2.5449` | `0.4879` | `2.8688` | `4.3519` | `6.525` | `1.2405` | `1.2683` | `8.06` | `385 / 9` |
| `vrs_zero_geom_only` | `1.4777` | `2.2673` | `2.7063` | `0.4576` | `3.6094` | `4.4923` | `6.591` | `1.4191` | `1.4586` | `8.05` | `456 / 9` |
| `vrs_tropo_unb3m_only` | `1.5144` | `2.1879` | `2.6609` | `0.4736` | `3.8042` | `4.3461` | `6.413` | `1.4617` | `1.4944` | `8.05` | `455 / 18` |
| `vrs_tropo_pride_ztd_only` | `1.3460` | `2.1713` | `2.5546` | `0.4569` | `3.2351` | `4.2986` | `6.512` | `1.2821` | `1.3004` | `8.05` | — |
| **`vrs_idw2_unb3m`** | **`1.2329`** | **`1.8041`** | **`2.1851`** | **`0.3464`** | **`2.8182`** | **`4.2008`** | **`4.419`** | **`1.1579`** | **`1.2308`** | `7.53` | `395 / 0` |
| **`vrs_idw2_pride_ztd`** | **`1.2347`** | **`1.8785`** | **`2.2479`** | `0.3585` | `2.9750` | `4.3620` | **`4.418`** | `1.1598` | `1.2321` | `7.53` | `387 / 0` |
| `vrs_nighttime_idw2_pride_ztd` | `1.3151` | `1.9028` | `2.3130` | `0.3635` | `3.1905` | `4.3191` | `5.995` | `1.2475` | `1.3060` | `7.53` | `399 / 9` |

#### Static Relative (`static_brdc_saas`, `n = 2,880`, `FIX = 0.0%`, `FLOAT = 100.0%`)

| Variant | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Med H (m) | P95 H (m) | P95 V (m) | Max H (m) | Post-30m H (m) | Rep H (m) | Sats |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `physical_anchor_ekak00nga` | `0.9677` | `0.5838` | `1.1301` | `0.3736` | **`0.8938`** | `1.2944` | `6.015` | `0.7361` | `0.9528` | `8.06` |
| `vrs_zero_geom_only` | `0.9577` | `0.6585` | `1.1622` | **`0.2955`** | `1.7010` | `1.5145` | `5.995` | `0.7192` | `0.9529` | `8.05` |
| `vrs_tropo_unb3m_only` | `0.9834` | `0.6579` | `1.1831` | `0.3694` | `1.6850` | `1.5451` | `6.018` | `0.7574` | `0.9733` | `8.05` |
| `vrs_tropo_pride_ztd_only` | `0.9941` | `0.5782` | `1.1500` | `0.3940` | `1.7575` | `1.4241` | `6.017` | `0.7713` | `0.9747` | `8.05` |
| **`vrs_idw2_unb3m`** | **`0.8881`** | `0.5378` | **`1.0382`** | `0.3217` | `0.9909` | `1.2636` | `5.482` | **`0.6561`** | **`0.8830`** | `7.53` |
| **`vrs_idw2_pride_ztd`** | `0.8921` | `0.5385` | `1.0420` | `0.3209` | `0.9920` | `1.2640` | `5.481` | `0.6612` | `0.8873` | `7.53` |
| **`vrs_nighttime_idw2_pride_ztd`** | `0.8903` | **`0.5377`** | `1.0401` | `0.3155` | `0.9868` | **`1.2622`** | **`5.478`** | `0.6596` | `0.8858` | `7.53` |

#### Code Differential (`dgps_code_diff`, `n = 2,880`, `DGPS = 100.0%`)

| Variant | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Med H (m) | P95 H (m) | P95 V (m) | Max H (m) | Rep H (m) | Sats |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `physical_anchor_ekak00nga` | `0.7749` | `1.0996` | `1.3452` | `0.4158` | `1.4329` | `2.1306` | `4.946` | `0.7517` | `8.06` |
| `vrs_zero_geom_only` | `0.8401` | `1.0974` | `1.3820` | `0.5400` | `1.4192` | `2.1242` | **`4.845`** | `0.7612` | `8.05` |
| `vrs_tropo_unb3m_only` | `0.7695` | `1.1006` | `1.3429` | **`0.4044`** | `1.4405` | `2.1226` | `4.965` | `0.7507` | `8.05` |
| **`vrs_tropo_pride_ztd_only`** | `0.7701` | **`1.0990`** | **`1.3419`** | `0.4055` | `1.4398` | **`2.1174`** | `4.944` | `0.7507` | `8.05` |
| `vrs_idw2_unb3m` | **`0.7664`** | `1.1555` | `1.3866` | `0.4146` | `1.3835` | `2.2088` | `5.139` | `0.7435` | `7.53` |
| `vrs_idw2_pride_ztd` | `0.7667` | `1.1540` | `1.3854` | `0.4165` | **`1.3826`** | `2.2091` | `5.142` | **`0.7431`** | `7.53` |
| `vrs_nighttime_idw2_pride_ztd` | `0.7780` | `1.1185` | `1.3625` | `0.4227` | `1.4465` | `2.1722` | `4.967` | `0.7566` | `7.53` |

---

### 10.2 Dataset A — `2011-03-20` `OSGF` (`PROVISIONAL_OSGOF_LIMITED`, Interior 8-Ref Convex Hull)

> **Truth Disclaimer:** `OSGF` coordinates carry `PROVISIONAL_OSGOF_LIMITED` status (undocumented ITRF realization, ARP continuity, and uncertainty). Accuracy figures below are **exploratory**; therefore **truth-independent repeatability (`Rep H`, `Rep 3D`)** around each solution's own session mean is reported side-by-side.

**Standalone SPP (`spp_single`):** `H RMSE = 1.2677 m`, `V RMSE = 3.3505 m`, `3D RMSE = 3.5823 m`, `Med H = 1.0673 m`, `P95 H = 2.2642 m`, `P95 V = 6.7069 m`, `Max H = 3.0967 m`, `Rep H = 1.1696 m`, `Sats = 8.19 (6–11)`.

#### Kinematic Relative (`kinematic_brdc_saas` & `kinematic_vrs_iono_off`, `n = 2,880`)

| Variant | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Med H (m) | P95 H (m) | P95 V (m) | Max H (m) | Rep H (m) | Rep 3D (m) | `Q=1` (False FIX) | Sats | `>2m` / `>5m` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `physical_anchor_cggt` | `1.4562` | `1.4676` | `2.0675` | `0.4698` | `3.3403` | `3.5486` | `5.555` | `1.4521` | `2.0324` | `0` (`0.0%`) | `8.02` | `402 / 19` |
| `vrs_zero_geom_only` | `1.4854` | `1.6180` | `2.1964` | `0.4378` | `3.1208` | `3.7672` | `6.085` | `1.4655` | `1.9935` | `2` (`0.1%` false) | `8.01` | `495 / 27` |
| `vrs_tropo_unb3m_only` | `1.4531` | `1.4560` | `2.0571` | `0.5124` | `3.3408` | `3.5612` | `5.552` | `1.4461` | `2.0356` | `5` (`0.2%` false) | `8.01` | `396 / 19` |
| `vrs_idw2_unb3m` | `0.7018` | `0.9539` | `1.1843` | **`0.2156`** | `1.6546` | `2.5287` | `2.724` | `0.6972` | `1.1783` | `0` (`0.0%`) | `8.01` | `67 / 0` |
| **`vrs_ipp_idw2_unb3m`** | **`0.6313`** | **`0.9333`** | **`1.1268`** | `0.2213` | **`1.4235`** | **`2.4392`** | **`2.525`** | **`0.6218`** | **`1.1212`** | `0` (`0.0%`) | `8.01` | **`20 / 0`** |
| `vrs_nighttime_ipp_idw2_unb3m` | `0.7509` | `1.0240` | `1.2698` | `0.2234` | `1.8706` | `2.5696` | `2.545` | `0.7204` | `1.2519` | `0` (`0.0%`) | `8.01` | `123 / 0` |

#### Static Relative (`static_brdc_saas`, `n = 2,880`, `FIX = 0.0%`, `FLOAT = 100.0%`)

| Variant | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Med H (m) | P95 H (m) | P95 V (m) | Max H (m) | Post-30m H (m) | Rep H (m) | Rep 3D (m) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `physical_anchor_cggt` | `0.9166` | `0.6088` | `1.1003` | `0.2700` | `2.1831` | `0.7393` | `4.761` | `0.7768` | `0.8120` | `0.8349` |
| `vrs_zero_geom_only` | `1.1483` | `0.8875` | `1.4513` | `0.2835` | `2.7966` | `1.0955` | `5.254` | `1.0079` | `0.9383` | `0.9666` |
| `vrs_tropo_unb3m_only` | `0.9049` | `0.5284` | `1.0479` | `0.2777` | `2.1466` | `0.6584` | `4.758` | `0.7633` | `0.8077` | `0.8311` |
| `vrs_idw2_unb3m` | `0.4663` | `0.4078` | `0.6194` | **`0.1203`** | `1.0344` | `0.5307` | `3.029` | `0.3606` | `0.4224` | `0.4515` |
| **`vrs_ipp_idw2_unb3m`** | **`0.3935`** | `0.4137` | **`0.5710`** | `0.1219` | `0.8232` | `0.5288` | **`2.825`** | **`0.2902`** | **`0.3619`** | **`0.3913`** |
| `vrs_nighttime_ipp_idw2_unb3m` | `0.4062` | **`0.4075`** | `0.5754` | `0.1224` | **`0.8061`** | **`0.5274`** | `2.950` | `0.2960` | `0.3717` | `0.4061` |

#### Code Differential (`dgps_code_diff`, `n = 2,880`, `DGPS = 100.0%`)

| Variant | H RMSE (m) | V RMSE (m) | 3D RMSE (m) | Med H (m) | P95 H (m) | P95 V (m) | Max H (m) | Rep H (m) | Rep 3D (m) | `>2m` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `physical_anchor_cggt` | `0.7891` | `1.4149` | `1.6200` | `0.5296` | `1.5757` | `3.6340` | `3.420` | `0.7060` | `1.4393` | `52` |
| `vrs_zero_geom_only` | `0.9072` | `1.5773` | `1.8196` | `0.7232` | `1.6382` | `3.8947` | `4.273` | `0.7178` | `1.4558` | `67` |
| `vrs_tropo_unb3m_only` | `0.7867` | `1.3834` | `1.5914` | `0.5153` | `1.5802` | `3.5780` | `4.301` | `0.7106` | `1.4460` | `53` |
| `vrs_idw2_unb3m` | `0.6273` | `1.1823` | `1.3384` | `0.3996` | `1.3211` | `2.7069` | `2.071` | `0.5708` | `1.2086` | `3` |
| `vrs_ipp_idw2_unb3m` | `0.6216` | `1.1911` | `1.3435` | `0.3984` | `1.3097` | `2.6766` | `2.027` | `0.5674` | `1.2109` | `3` |
| **`vrs_nighttime_ipp_idw2_unb3m`** | **`0.4310`** | **`1.0119`** | **`1.0999`** | **`0.3021`** | **`0.8429`** | **`2.2247`** | **`1.626`** | **`0.4216`** | **`0.9964`** | **`0`** |

---

## 11. ENU Error, Diurnal Scintillation, and Convergence Analysis

### 11.1 Component Biases (Mean East / North / Up)
- **`2024 PHRI` Kinematic:** `physical_anchor_ekak00nga` exhibited `(+0.309, +0.072, +0.230) m` mean ENU bias; `vrs_idw2_unb3m` reduced this to `(+0.035, +0.061, -0.108) m` and `vrs_idw2_pride_ztd` to `(+0.079, -0.007, -0.019) m` (near-zero vertical bias).
- **`2024 PHRI` DGPS:** `vrs_zero_geom_only` suffered a `-0.354 m` East bias (vs `-0.188 m` physical anchor) caused by unmodeled `105 km` East-West hydrostatic mapping-function asymmetry; adding `UNB3m` (`-0.169 m`) or `PRIDE ZTD` (`-0.171 m`) completely removed that bias.
- **`2011 OSGF` Kinematic:** `vrs_zero_geom_only` carried a `+0.890 m` Up bias from `CGGT`'s unmodeled `384 m` height difference; `vrs_tropo_unb3m_only` cut it to `+0.260 m` (matching `physical_anchor_cggt` `+0.363 m`), and `vrs_ipp_idw2_unb3m` reduced mean ENU to `(-0.029, -0.105, -0.023) m`.
- **`2011 OSGF` DGPS:** `vrs_nighttime_ipp_idw2_unb3m` collapsed East bias from `-0.319 m` (`CGGT`) and `-0.555 m` (`zero_geom_only`) to `+0.027 m`, confirming that nighttime receiver-DCB leveling directly removes absolute pseudorange ionospheric offsets.

### 11.2 Six-Hour UTC Temporal Consistency (Including Equatorial Post-Sunset Scintillation)

| Dataset & Variant (`kinematic_brdc_saas`) | `00–06 UTC` H (m) | `06–12 UTC` H (m) | `12–18 UTC` H (m) | `18–24 UTC` H (m) | Consistency Verdict |
|---|---:|---:|---:|---:|---|
| `2024` `physical_anchor_ekak00nga` | `1.9217` | `0.7642` | `0.2390` | `1.5821` | Strong nighttime/scintillation degradation |
| `2024` `vrs_zero_geom_only` | `2.4140` | `0.7306` | `0.2402` | `1.5216` | Worse at `00–06 UTC` |
| `2024` `vrs_idw2_unb3m` | `2.0459` | **`0.3021`** (`-60.5%`) | **`0.1875`** (`-21.5%`) | **`1.3296`** (`-16.0%`) | Wins 3/4 windows; loses `00–06 UTC` (`+6.5%`) |
| `2011` `physical_anchor_cggt` | `1.6838` | `0.3556` | `0.4279` | `2.3102` | Severe `18–24 UTC` equatorial surge |
| `2011` `vrs_zero_geom_only` | `1.9870` | `0.3251` | `0.3160` | `2.1613` | High error in both nighttime windows |
| **`2011` `vrs_ipp_idw2_unb3m`** | **`0.6947`** (`-58.7%`) | **`0.1843`** (`-48.2%`) | **`0.1578`** (`-63.1%`) | **`1.0260`** (`-55.6%`) | **Wins ALL 4/4 UTC windows by 48–63%** |

### 11.3 Convergence and Outlier Behavior
- In `2011 OSGF` kinematic mode, `vrs_ipp_idw2_unb3m` cut initial filter transients by more than half across every checkpoint: `first_5m` (`0.951 → 0.434 m`), `first_15m` (`3.401 → 1.317 m`), `first_30m` (`4.114 → 1.648 m`), and `post_30m_steady` (`1.343 → 0.591 m`, 3D `2.000 → 1.109 m`). Severe `>2 m` excursions fell by `95.0%` (`402 → 20` epochs) and `>5 m` excursions dropped from `19 → 0`.
- In `2024 PHRI` kinematic mode, initial `first_30m` convergence was similar (`3.107 m` anchor vs `3.141 m` `vrs_idw2_unb3m`), while `post_30m_steady` improved (`1.241 → 1.158 m` H; `2.527 → 2.156 m` 3D) and `>5 m` outliers dropped from `9 → 0` (worst horizontal error fell from `6.525 m` at `23:20:00Z` to `4.419 m` at `00:11:30Z`; worst vertical outlier fell from `20.24 m` to `13.54 m`).

---

## 12. Ambiguity Resolution (FIX / FLOAT) Analysis

**Headline finding: Genuine centimetre RTK FIX was NOT achieved (`0.0%` genuine FIX rate across all 52 runs).**

| Dataset | Profile | Variants with `Q=1` Flags | Verified Genuine FIX Rate | `FLOAT` Rate | Max Ratio (`arthres=3.0`) | Ambiguity Resets | `TTFF` |
|---|---|---|---:|---:|---:|---:|---|
| `2024 PHRI` | `kinematic_*` & `static_brdc_saas` | None (`0 / 7` variants) | **`0.0%`** | `100.0%` | `1.7–2.6` | `0` | `None` |
| `2011 OSGF` | `static_brdc_saas` | None (`0 / 6` variants) | **`0.0%`** | `100.0%` | `1.5–2.3` | `0` | `None` |
| `2011 OSGF` | `kinematic_*` | `vrs_zero_geom_only` (`2` ep), `vrs_tropo_unb3m_only` (`5` ep); `0` on all 3 atmo VRS + anchor | **`0.0%`** (all 7 `Q=1` epochs confirmed **false fixes**) | `99.8–100.0%` | `2.0–2.8` (atmo), `3.4–3.8` (false FIX) | `0` (atmo), `1` (false FIX) | `None` (no genuine FIX) |

### Forensic Proof of False Fixes in 2011 Non-Ionospheric Variants
Inspecting `enu_residuals.csv` for all 7 `Q=1` epochs confirmed every single one was a **wrong-integer false fix** driven by unmodeled ionospheric delay on the `216 km` baseline:
- `vrs_zero_geom_only` (`2` epochs at `19:53:00Z–19:53:30Z`, 6 sats, post-sunset scintillation onset): `E = +2.29 to +2.40 m`, `N = +0.36 to +0.41 m`, `U = -2.83 to -3.04 m`, **`H = 2.32–2.43 m`**, **`3D = 3.66–3.89 m`**.
- `vrs_tropo_unb3m_only` (`5` epochs at `00:45:00Z–00:47:00Z`, 7 sats): `E = -1.20 to -1.22 m`, `N = -0.49 to -0.51 m`, `U = -0.06 to -0.12 m`, **`H = 1.29–1.32 m`**, **`3D = 1.30–1.33 m`**.
- None of the atmospheric VRS variants (`vrs_idw2_unb3m`, `vrs_ipp_idw2_unb3m`, `vrs_nighttime_ipp_idw2_unb3m`) emitted a single false fix.

**Physical root cause of 0% genuine FIX:**
1. Experimental VRS uses **`ANCHOR_RELATIVE_FLOAT`** carrier phases without network-level double-difference integer ambiguity resolution (**B-03**).
2. Even inside the 2011 8-reference hull (`200–716 km` spacing), residual differential ionospheric errors after `IPP-IDW2` remain `~0.1–0.5 m` (0.5–2.5 L1 cycles), exceeding the `< ~0.25 cycle` (~5 cm) narrow-lane residual budget required for reliable LAMBDA integer validation.

---

## 13. Paired Statistical Comparison (40-Epoch / 20-Min Moving-Block Bootstrap)

Positive `ΔH RMSE` indicates candidate error reduction over baseline; 95% confidence intervals exclude zero when bolded.

### 13.1 Dataset B — `2024-01-26` `PHRI00NGA` (Verified IGS20, `n = 2,880` paired epochs)

| Profile | Comparison (Candidate vs. Baseline) | `ΔH RMSE` (m) | `ΔH %` | 95% Block-Bootstrap CI (m) | `ΔV %` | `Δ3D %` | `ΔMed H` (m) | `ΔP95 H` (m) | Epoch Win |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|
| `static` | **`vrs_idw2_unb3m` vs. `physical_anchor_ekak`** | **`+0.0796`** | **`+8.23%`** | **`[+0.0468, +0.1213]`** | `+7.88%` | `+8.14%` | `-0.0519` | `+0.0971` | `94.8%` |
| `static` | **`vrs_idw2_pride_ztd` vs. `physical_anchor_ekak`** | **`+0.0756`** | **`+7.82%`** | **`[+0.0387, +0.1183]`** | `+7.74%` | `+7.80%` | `-0.0527` | `+0.0982` | `92.6%` |
| `static` | `vrs_idw2_unb3m` vs. `vrs_zero_geom_only` | `+0.0696` | `+7.27%` | `[-0.0099, +0.1242]` | `+18.34%` | `+10.67%` | `+0.0263` | `-0.7101` | `48.8%` |
| `kinematic` | `vrs_idw2_unb3m` vs. `physical_anchor_ekak` | `+0.0745` | `+5.70%` | `[-0.0847, +0.2399]` | `+17.37%` | `+14.14%` | `-0.1415` | `-0.0506` | `62.9%` |
| `kinematic` | `vrs_idw2_unb3m` vs. `vrs_zero_geom_only` | `+0.2448` | `+16.57%` | `[-0.0360, +0.4786]` | `+20.43%` | `+19.26%` | `-0.1112` | `-0.7911` | `57.6%` |
| `kinematic` | **`vrs_tropo_pride_ztd_only` vs. `vrs_zero_geom_only`** | **`+0.1317`** | **`+8.91%`** | **`[+0.0228, +0.2432]`** | `+4.24%` | `+5.61%` | `-0.0007` | `-0.3743` | `51.3%` |
| `dgps` | **`vrs_tropo_unb3m_only` vs. `physical_anchor_ekak`** | **`+0.0055`** | **`+0.71%`** | **`[+0.0028, +0.0091]`** | `-0.09%` | `+0.17%` | `-0.0114` | `+0.0075` | `74.2%` |
| `dgps` | **`vrs_tropo_pride_ztd_only` vs. `physical_anchor_ekak`** | **`+0.0048`** | **`+0.63%`** | **`[+0.0024, +0.0082]`** | `+0.06%` | `+0.25%` | `-0.0103` | `+0.0068` | `74.0%` |
| `dgps` | `vrs_idw2_unb3m` vs. `physical_anchor_ekak` | `+0.0086` | `+1.10%` | `[-0.0350, +0.0435]` | `-5.09%` | `-3.07%` | `-0.0013` | `-0.0494` | `51.8%` |
| `dgps` | **`vrs_idw2_unb3m` vs. `vrs_zero_geom_only`** | **`+0.0737`** | **`+8.77%`** | **`[+0.0395, +0.1093]`** | `-5.30%` | `-0.33%` | `-0.1254` | `-0.0357` | `78.3%` |
| `dgps` | `vrs_zero_geom_only` vs. `physical_anchor_ekak` | `-0.0651` | `-8.41%` | **`[-0.0986, -0.0404]`** | `+0.20%` | `-2.73%` | `+0.1242` | `-0.0138` | `19.0%` |

### 13.2 Dataset A — `2011-03-20` `OSGF` (Interior Hull, Provisional Truth, `n = 2,880` paired epochs)

| Profile | Comparison (Candidate vs. Baseline) | `ΔH RMSE` (m) | `ΔH %` | 95% Block-Bootstrap CI (m) | `ΔV %` | `Δ3D %` | `ΔMed H` (m) | `ΔP95 H` (m) | Epoch Win |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|
| `kinematic` | **`vrs_ipp_idw2_unb3m` vs. `physical_anchor_cggt`** | **`+0.8249`** | **`+56.65%`** | **`[+0.5899, +1.0148]`** | `+36.41%` | `+45.50%` | `-0.2485` | `-1.9167` | `97.5%` |
| `kinematic` | **`vrs_ipp_idw2_unb3m` vs. `vrs_zero_geom_only`** | **`+0.8541`** | **`+57.50%`** | **`[+0.6020, +1.0587]`** | `+42.32%` | `+48.70%` | `-0.2166` | `-1.6973` | `84.7%` |
| `kinematic` | **`vrs_idw2_unb3m` vs. `physical_anchor_cggt`** | **`+0.7544`** | **`+51.81%`** | **`[+0.5321, +0.9434]`** | `+35.00%` | `+42.72%` | `-0.2542` | `-1.6857` | `97.8%` |
| `kinematic` | `vrs_tropo_unb3m_only` vs. `physical_anchor_cggt` | `+0.0031` | `+0.21%` | `[-0.0052, +0.0111]` | `+0.79%` | `+0.50%` | `+0.0426` | `+0.0005` | `28.8%` |
| `static` | **`vrs_ipp_idw2_unb3m` vs. `physical_anchor_cggt`** | **`+0.5230`** | **`+57.06%`** | **`[+0.3832, +0.6610]`** | `+32.04%` | `+48.11%` | `-0.1481` | `-1.3599` | `73.7%` |
| `static` | **`vrs_ipp_idw2_unb3m` vs. `vrs_zero_geom_only`** | **`+0.7547`** | **`+65.73%`** | **`[+0.5636, +0.9435]`** | `+53.38%` | `+60.66%` | `-0.1617` | `-1.9734` | **`100.0%`** |
| `static` | `vrs_zero_geom_only` vs. `physical_anchor_cggt` | `-0.2317` | `-25.28%` | **`[-0.2879, -0.1733]`** | `-45.77%` | `-31.89%` | `+0.0136` | `+0.6135` | `5.3%` |
| `dgps` | **`vrs_nighttime_ipp_idw2_unb3m` vs. `physical_anchor_cggt`** | **`+0.3581`** | **`+45.38%`** | **`[+0.2501, +0.4735]`** | `+28.48%` | `+32.11%` | `-0.2275` | `-0.7328` | `78.4%` |
| `dgps` | **`vrs_nighttime_ipp_idw2_unb3m` vs. `vrs_zero_geom_only`** | **`+0.4762`** | **`+52.49%`** | **`[+0.3791, +0.5839]`** | `+35.84%` | `+39.55%` | `-0.4211` | `-0.7953` | `84.7%` |
| `dgps` | **`vrs_ipp_idw2_unb3m` vs. `physical_anchor_cggt`** | **`+0.1675`** | **`+21.22%`** | **`[+0.0839, +0.2603]`** | `+15.81%` | `+17.07%` | `-0.1312` | `-0.2660` | `74.6%` |

---

## 14. Failure and Robustness Testing (`12 / 12` PASS)

All 12 required Phase H fail-closed robustness scenarios executed cleanly against authentic data and verified zero synthetic fallback substitution:

| # | Scenario | Expected Fail-Closed Outcome | Observed Outcome | Status |
|---|---|---|---|---|
| 1 | Missing rover observations | `FAILED_MISSING_ROVER_OBS` | `FAILED_MISSING_ROVER_OBS` | **PASS** |
| 2 | Missing reference observations | `FAILED_MISSING_REFERENCE_OBS` | `FAILED_MISSING_REFERENCE_OBS` | **PASS** |
| 3 | Navigation product gap | `FAILED_MISSING_NAVIGATION` | `FAILED_MISSING_NAVIGATION` | **PASS** |
| 4 | Invalid RTCM frame (flipped CRC byte) | `FAILED_INVALID_RTCM` | `FAILED_INVALID_RTCM` (`crc_fail_count = 1`) | **PASS** |
| 5 | Truncated RTCM stream (`40 B`) | `FAILED_TRUNCATED_RTCM` | `FAILED_TRUNCATED_RTCM` (`TRUNCATED_FRAME offset=25`) | **PASS** |
| 6 | Insufficient satellite visibility (`1` sat) | `FAILED_INSUFFICIENT_SATELLITES` | `FAILED_INSUFFICIENT_SATELLITES` (`0` epochs) | **PASS** |
| 7 | Inconsistent observation epochs (`2024-01-27`) | `FAILED_EPOCH_MISMATCH` | `FAILED_EPOCH_MISMATCH` (`no obs data`) | **PASS** |
| 8 | Incorrect coordinate provenance (`PROVISIONAL` + `accuracy_claim_permitted=True`) | `BenchmarkFailure` raised | Blocked (`VERIFIED_IGS20_PPP_AR` required) | **PASS** |
| 9 | Unavailable atmospheric model (`idw2`, `iono=None`) | `ATMOSPHERIC_MODEL_UNAVAILABLE` | `ATMOSPHERIC_MODEL_UNAVAILABLE` | **PASS** |
| 10 | Rover outside convex hull (`require_interior_hull=True`) | `INSUFFICIENT_NETWORK_GEOMETRY` | `INSUFFICIENT_NETWORK_GEOMETRY` | **PASS** |
| 11 | Failed ambiguity resolution honest reporting | `fix=0`, `float=2880`, `ttff=None` | `fix_epochs=0`, `float_epochs=2880`, `ttff_s=None` | **PASS** |
| 12 | RTKLIB timeout (`0.001 s`) / non-zero exit | `FAILED_RTKLIB_EXECUTION` | `FAILED_RTKLIB_EXECUTION` (`timed out`) | **PASS** |

---

## 15. Limitations

Full details and fairness diagnostics are in [b02_rover_benchmark_limitations.md](file:///home/excellence/NLGCP/docs/research/b02_rover_benchmark_limitations.md). Key limits:
1. **Zero genuine RTK FIX (`B-03`):** `ANCHOR_RELATIVE_FLOAT` VRS cannot resolve integer ambiguities across `105–716 km` baselines.
2. **2011 coordinate provenance (`B-01`):** `OSGF` and the 8 reference coordinates remain `PROVISIONAL_OSGOF_2011_01_01` (offline 2011 PPP blocked by missing 2011 SP3/CLK/OSB files).
3. **2024 sparse extrapolation & satellite-count loss (`B-05`):** Only 3 verified references (`PHRI` outside hull) caused `1,485` dropped ionospheric obs (`8.06 → 7.53` mean sats), weakening DGPS vertical VDOP (`-5%`).
4. **Non-causal Phase 6 arc-median leveling (`B-08`):** Both `common_arc` and `nighttime` ionospheric estimators use full-24h offline arcs, not causal real-time filters.
5. **Single-day coverage per era:** One verified 2024 day and one 2011 interior day; multi-season / storm-day generalization is not yet established.
6. **GPS-only (`1005 + 1074`) & single positioning engine (`RTKLIB v2.4.2-p13`):** No GLONASS/Galileo multi-GNSS positioning and no commercial receiver hardware validation (`B-06`, `B-07`, `B-10`).

---

## 16. Scientific Interpretation

The B-02 benchmark establishes three clear, defensible scientific conclusions:
1. **Geometry-only VRS is insufficient — differential tropospheric modelling is mandatory when relocating an anchor to a virtual position.** Because RTKLIB's `zdres()` applies hydrostatic Saastamoinen at the base coordinate, placing a geometry-only VRS next to the rover disables RTKLIB's automatic baseline hydrostatic cancellation, making `vrs_zero_geom_only` worse than a physical anchor by `2–25%` until differential troposphere (`UNB3m` or `network_ztd`) is restored.
2. **Inside a true multi-station convex hull, atmospheric VRS (`IPP-IDW2 + UNB3m`) delivers large, consistent, truth-independent FLOAT and DGPS positioning improvements across Nigeria's equatorial ionosphere.** At `OSGF` (`216 km` from `CGGT`, surrounded by 8 NIGNET stations), `vrs_ipp_idw2_unb3m` cut horizontal positioning error and centered scatter by **`55–57%`** in both kinematic (`1.456 → 0.631 m`) and static (`0.917 → 0.394 m`) modes across all four 6-hour UTC windows (including `18–24 UTC` post-sunset plasma bubbles), while `vrs_nighttime_ipp_idw2_unb3m` cut DGPS horizontal RMSE by **`45.4%`** (`0.789 → 0.431 m`).
3. **Under sparse 3-station extrapolation (`2024 PHRI`, `105–1,029 km`), atmospheric VRS yields modest static (`+8.2%`) and kinematic 3D (`+14.1%`) gains, while remaining FLOAT-only.** Achieving operational centimetre RTK FIX in Nigeria requires closing **B-01** (verified IGS20 2011 coordinates via PRIDE PPP-AR), **B-05** (denser verified `<70–100 km` CORS spacing with interior coverage), and **B-03** (network double-difference integer ambiguity resolution). Operational controls (`BEST = ZERO`, `VRS_GEOMETRY_ONLY`, `OPERATIONAL_APPROVED = FORBIDDEN`) must remain unchanged.

---

## 17. Acceptance Criteria Matrix (`B02-01` – `B02-18`)

| ID | Criterion | Status | Evidence |
|---|---|---|---|
| `B02-01` | Repository and dataset preflight completed | **PASS** (`TECHNICALLY_VALIDATED`) | [b02_rover_benchmark_preflight.md](file:///home/excellence/NLGCP/docs/research/b02_rover_benchmark_preflight.md) |
| `B02-02` | Authentic rover candidate selected and documented | **PASS** | `PHRI00NGA` (2024) + `OSGF` (2011) in [b02_rover_dataset_selection.md](file:///home/excellence/NLGCP/docs/research/b02_rover_dataset_selection.md) |
| `B02-03` | Rover/reference separation established | **PASS** | `assert_no_rover_leakage()` PASS on both datasets + epoch-0 SPP GGA virtual ARP (`4.56 m` / `0.84 m` offset) |
| `B02-04` | Rover coordinate truth and uncertainty documented | **PASS** (2024 verified; 2011 `LIMITED_PROVISIONAL_TRUTH`) | `RoverTruthRecord` + `dataset_manifest.json` (`VERIFIED_IGS20_PPP_AR` vs `PROVISIONAL_OSGOF_LIMITED`) |
| `B02-05` | Physical-anchor baseline processed | **PASS** | `EKAK00NGA` (`105.55 km`, reproduces Phase 3 exact static `0.9677/0.5838/1.1301 m`) & `CGGT` (`216.32 km`) |
| `B02-06` | Geometry-only VRS processed | **PASS** | `vrs_zero_geom_only` (`2,880/2,880` ep on both datasets) |
| `B02-07` | Atmospheric VRS processed | **PASS** | `5` atmo variants (2024) + `4` atmo variants (2011), all `2,880/2,880` ep |
| `B02-08` | RTKLIB processing settings documented and comparable | **PASS** | `experiment_config.json` + `rtklib.conf` SHA-256s + `src/rtkpos.c` audit |
| `B02-09` | ENU positioning errors calculated against defensible truth | **PASS** (2024 verified; 2011 exploratory + repeatability) | Per-epoch `enu_residuals.csv` + `b02_benchmark_summary.json` |
| `B02-10` | FIX/FLOAT and solution availability metrics reported | **PASS** | `100%` availability; **`0.0%` genuine FIX** (`7` false fixes exposed forensically) |
| `B02-11` | Paired comparison and statistical analysis completed | **PASS** | `2,880` paired epochs/profile + 40-epoch moving-block bootstrap 95% CIs (`comparison_summary.json`) |
| `B02-12` | Data leakage and experimental fairness assessed | **PASS** | Programmatic leakage checks + `P1/C1`, antenna PCO, and satellite-visibility audit |
| `B02-13` | Failure tests implemented | **PASS** (`12 / 12` scenarios) | `failure_and_robustness_suite` (`all_passed = True`) |
| `B02-14` | Reproducible benchmark runner and machine-readable results created | **PASS** | `research/rover_benchmark/`, `scripts/run_b02_rover_benchmark.py`, `311` hashed outputs |
| `B02-15` | Research report and limitations report completed | **PASS** | This report + [b02_rover_benchmark_limitations.md](file:///home/excellence/NLGCP/docs/research/b02_rover_benchmark_limitations.md) |
| `B02-16` | Project status and evidence records updated | **PASS** | `CURRENT_WORK.md`, `PROJECT_STATUS.md`, `EVIDENCE_INDEX.md`, sprint docs `02` & `06` |
| `B02-17` | Existing repository quality gates pass | **PASS** | Verified in Section 18 / handover (`make check` + focused `RTKLIB_SOURCE` pytest) |
| `B02-18` | Operational controls remain unchanged | **PASS** | `OPERATIONAL_APPROVED = FORBIDDEN`, `BEST = ZERO`, `VRS_GEOMETRY_ONLY`, `NLGCP_TEST` untouched |

---

## 18. Recommendations & Reproducibility Instructions

### Prioritized Next Milestones
1. **Milestone B-01 (Highest Scientific ROI):** Acquire checksummed 2011 IGS/repro3 precise products (`SP3`, `CLK`, `ERP`, `OSB`/`DCB`) for `2011-03-20..21` and `2011-12-05..08` and process all 9 NIGNET stations with **PRIDE PPP-AR 3.2.8** to upgrade `OSGF` and the 8 references from `PROVISIONAL_OSGOF_LIMITED` to `VERIFIED_IGS20_PPP_AR` and generate independent 9-station 2011 ZTD truth — unlocking full `SCIENTIFICALLY_VALIDATED` status on Nigeria's interior convex-hull benchmark.
2. **Milestone B-03 (Path to Centimetre RTK FIX):** Implement offline network double-difference integer ambiguity resolution (Melbourne-Wubbena wide-lane + narrow-lane LAMBDA) and test on denser `<70–100 km` verified Nigerian baselines once available.
3. **Milestone B-08a (Causal Real-Time Filter):** Replace offline 24-hour arc-median ionospheric leveling with a causal epoch-by-epoch Kalman filter so B-02 can benchmark true real-time-compatible atmospheric VRS without look-ahead bias.

### Exact Reproducibility Commands
```bash
# 1. Run focused B-02 + Phase 6/7 unit & integration tests (with RTKLIB_SOURCE)
RTKLIB_SOURCE=/home/excellence/RTKLIB .venv/bin/python -m pytest \
  research/rover_benchmark/tests research/vrs_generator/tests \
  research/atmospheric_spatial_model/tests -q

# 2. Execute full 24-hour B-02 Offline Rover Positioning Benchmark (~12.5 min on 4 cores)
NLGCP_DATA_ROOT=/home/excellence/nlgcp-data \
  .venv/bin/python scripts/run_b02_rover_benchmark.py --data-root /home/excellence/nlgcp-data
```
Primary machine-readable outputs under `/home/excellence/nlgcp-data/processed/rover-benchmark/b02/`:
- `dataset_manifest.json` (`61acf424…8e254b`)
- `experiment_config.json` (`44d22f17…491f1b`)
- `execution_metadata.json` (`73f95431…7a898`)
- `comparison_summary.json` (`f36956c0…26bd5e`)
- `b02_benchmark_summary.json` (`47dc7457…043c98`)
- `hashes_manifest.json` (`311` output SHA-256 hashes + `9` input SHA-256 hashes)
