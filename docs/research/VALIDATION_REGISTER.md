# NLGCP Validation & Findings Register

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Machine-Readable Registers:** [`findings_register.json`](file:///home/excellence/NLGCP/research/archive/validation/findings_register.json) (`18` findings) & [`repro_records.json`](file:///home/excellence/NLGCP/research/archive/reproducibility/repro_records.json) (`6` reproduction records)
**Last Updated:** 2026-11-26

---

## 1. Strict Validation Evidence Hierarchy

Evidence levels are never automatically promoted:

`IMPLEMENTED` → `UNIT_TESTED` → `INTEGRATION_TESTED` → `INDEPENDENTLY_VALIDATED` → `SCIENTIFICALLY_VALIDATED` → `HARDWARE_VALIDATED` → `OPERATIONALLY_APPROVED`

No NLGCP component currently holds `HARDWARE_VALIDATED` or `OPERATIONALLY_APPROVED` (`OPERATIONAL_APPROVED = FORBIDDEN`).

---

## 2. Registered Findings (Positive, Negative, Inconclusive & Defect Fixes)

| Finding ID | Polarity | Level | Supporting Experiments | Concise Finding Summary |
|---|---|---|---|---|
| `NLGCP-FIND-001` | `POSITIVE_WITH_LIMITATIONS` | `INDEPENDENTLY_VALIDATED` | `EXP-016` | Verified 2024 `PHRI`: `vrs_idw2_unb3m` improved static FLOAT H `+8.23%` (CI `[+0.047, +0.121] m`) and kinematic 3D `+14.14%`. |
| `NLGCP-FIND-002` | `POSITIVE_WITH_LIMITATIONS` | `INTEGRATION_TESTED` | `EXP-017` | Interior 2011 `OSGF` (provisional truth): `vrs_ipp_idw2_unb3m` cut kinematic H `+56.65%`, static H `+57.06%`, centered scatter `-57.2%`; DGPS H `+45.38%`. |
| `NLGCP-FIND-003` | **`NEGATIVE`** | `INDEPENDENTLY_VALIDATED` | `EXP-002, 004, 016, 017` | **Zero genuine RTK FIX (`0.0%`)** across all 52 B-02 runs (`149,760` ep) and all Phase 3/5 baselines (`ANCHOR_RELATIVE_FLOAT`). |
| `NLGCP-FIND-004` | **`NEGATIVE`** | `INTEGRATION_TESTED` | `EXP-017` | All **7 `Q=1` epochs** on 2011 non-ionospheric VRS were forensically confirmed wrong-integer false fixes (`1.30–2.43 m` H error). |
| `NLGCP-FIND-005` | **`NEGATIVE`** | `INDEPENDENTLY_VALIDATED` | `EXP-016, 017` | **Geometry-only VRS degraded positioning** (`-8.4%` to `-25.3%` H) because RTKLIB `zdres()` hydrostatic cancellation vanishes without VRS differential troposphere. |
| `NLGCP-FIND-006` | **`INCONCLUSIVE`** | `INDEPENDENTLY_VALIDATED` | `EXP-016` | Full-day 2024 `PHRI` kinematic H gain (`+5.70%`, CI `[-0.085, +0.240] m`) crosses zero under 3-ref extrapolation (`-0.53` sats/ep). |
| `NLGCP-FIND-007` | **`NEGATIVE`** | `INTEGRATION_TESTED` | `EXP-001, 017` | **2011 OSGoF coordinates remain provisional** (`PROVISIONAL_OSGOF_2011_01_01`) with zero local 2011 `SP3`/`CLK`/`ERP`/`OSB` products (`B-01`). |
| `NLGCP-FIND-008` | **`NEGATIVE`** | `INDEPENDENTLY_VALIDATED` | `EXP-006, 007` | **Perimeter extrapolation stays `ZERO`-dominated** in Phase 6 LOOCV (`2024` `zero 3.076 m` wins); interior 9-station 2011 hulls improve `+26.1%`–`+30.0%`. |
| `NLGCP-FIND-009` | **`DEFECT_FOUND_AND_FIXED`** | `UNIT_TESTED` | `EXP-016` | **ZWD bug in `experimental_vrs.py:517`** (`spatial_model="zero"` + `network_ztd` injected `+0.54–0.74 m` Up bias) caught in B-02, fixed (`idw2`), and regression-tested. |
| `NLGCP-FIND-010` | **`NEGATIVE`** | `INDEPENDENTLY_VALIDATED` | `EXP-009, 013` | **No non-RTKLIB RTCM MSM4 decoder** available locally (ESA gLAB v6.0.0 verifies CRC-24Q + `1005` only; MSM4 `NOT_SUPPORTED_BY_GLAB_V6`). |
| `NLGCP-FIND-011` | **`NEGATIVE`** | `INTEGRATION_TESTED` | `EXP-001` | **132 CDDIS 2011 nav attempts returned `AUTHENTICATION_REQUIRED`**; public BKG fallback succeeded `66/66`. |
| `NLGCP-FIND-012` | **`NEGATIVE`** | `INTEGRATION_TESTED` | `EXP-001, 017` | **Missing local precise/bias products**: `external-products/igs/2024/` is empty (0 DCB/IONEX), 2011 `SP3`/`CLK` absent, WUM `CLK`/`BIA`/`ERP` cleaned by PRIDE. |
| `NLGCP-FIND-013` | **`NEGATIVE`** | `INTEGRATION_TESTED` | `EXP-015` | **14 Day 7 security findings** (`2 CRITICAL`, `4 HIGH`) strictly block non-loopback deployment (`SEC-01`–`SEC-14`). |
| `NLGCP-FIND-014` | `POSITIVE` | `INDEPENDENTLY_VALIDATED` | `EXP-002, 016` | Phase 3 `EKAK→PHRI` static baseline numerically reproduced to 4 decimals in B-02 (`0.9677 / 0.5838 / 1.1301 m`). |
| `NLGCP-FIND-015` | `POSITIVE_WITH_LIMITATIONS` | `INDEPENDENTLY_VALIDATED` | `EXP-007` | UNB3m ZHD matches PRIDE PPP-AR ZTD to `1.85 mm` RMSE while exposing a `12.6 cm` coastal-vs-Harmattan ZWD gradient. |
| `NLGCP-FIND-016` | `POSITIVE_WITH_LIMITATIONS` | `INTEGRATION_TESTED` | `EXP-013, 014` | Synthetic Phase 11 `1005/1074/1084` + loopback Phase 12 `NLGCP_TEST` validated byte-exact with RTKLIB (strictly synthetic). |
| `NLGCP-FIND-017` | **`NEGATIVE`** | `INTEGRATION_TESTED` | `EXP-011, 012` | Real Phase 9 RTCM replay and real Phase 10 live CORS ingestion remain **`BLOCKED`** (zero authorized Nigerian CORS streams). |
| `NLGCP-FIND-018` | `POSITIVE_WITH_LIMITATIONS` | `INDEPENDENTLY_VALIDATED` | `EXP-009, 016` | Phase 7 authentic VRS streams decoded cleanly over isolated `/NLGCP_VRS_EXP` in RTKLIB & gLAB (`1005`), while B-02 showed `120 s` cadence exceeded `maxage=30 s`. |

---

## 3. Reproducibility Records (`NLGCP-REPRO-2026-001` – `006`)

| Repro ID | Original Exp | Level | Outcome | Evidence Summary |
|---|---|---|---|---|
| `NLGCP-REPRO-2026-001` | `EXP-002` (Phase 3) | `LEVEL_3_NUMERICAL` | `REPRODUCED` | B-02 reproduced `EKAK→PHRI` static control (`0.9677/0.5838/1.1301 m` vs. `0.968/0.584/1.130 m`). |
| `NLGCP-REPRO-2026-002` | `EXP-016` (B-02) | `LEVEL_3_NUMERICAL` | `REPRODUCED` | Deterministic re-run post-ZWD fix (`52/52` runs, `311` SHA-256 outputs, `12/12` failure checks). |
| `NLGCP-REPRO-2026-003` | `EXP-006` (Phase 6 `v3`) | `LEVEL_1_RECORD_COMPLETE` | `PARTIALLY_REPRODUCED` | Authoritative `metrics.json` (`3a2e79db…`) & config (`f9828fec…`) intact; shell cmd not archived. |
| `NLGCP-REPRO-2026-004` | `EXP-014` (Phase 12 demo) | `LEVEL_2_COMPUTATIONAL` | `REPRODUCED` | Repeated across Days 5–7, Phase 6/7, and B-02 (`10/10` stages PASS, synthetic-only). |
| `NLGCP-REPRO-2026-005` | `EXP-009` (Phase 7 VRS) | `LEVEL_4_INDEPENDENT` | `PARTIALLY_REPRODUCED` | gLAB v6.0.0 cross-decoded CRC-24Q + `1005` (`0.0000 m`), but MSM4 unsupported (`B-06`). |
| `NLGCP-REPRO-2026-006` | `EXP-017` (2011 PPP truth) | `LEVEL_0_NONE` | **`BLOCKED`** | Offline PRIDE PPP-AR blocked by absent 2011 `SP3`/`CLK`/`ERP`/`OSB` (`NLGCP-DATA-2011-006`). |
