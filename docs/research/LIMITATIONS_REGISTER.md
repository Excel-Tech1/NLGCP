# NLGCP Limitations Register

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Machine-Readable Register:** [`limitations_register.json`](file:///home/excellence/NLGCP/research/archive/validation/limitations_register.json) (`12` registered limitations)
**Last Updated:** 2026-11-26

---

## 1. Registered Scientific, Data, Engineering & Security Limitations

| Limitation ID | Blocker | Severity | Title & Evidence-Backed Scope | Related Experiments |
|---|---|---|---|---|
| `NLGCP-LIM-001` | `B-03` | `CRITICAL` | **Zero genuine RTK integer ambiguity resolution (`FIX = 0.0%`):** Experimental VRS uses `ANCHOR_RELATIVE_FLOAT` across `105–716 km` baselines; no centimetre RTK FIX achieved (`0/149,760` genuine FIX in B-02; 7 `Q=1` epochs confirmed false fixes). | `EXP-002, 004, 016, 017` |
| `NLGCP-LIM-002` | `B-01` | `CRITICAL` | **Provisional 2011 OSGoF coordinate provenance:** All 11 stations in `NIGNET2011.zip` lack documented ITRF realization, ARP continuity, and uncertainty; zero local 2011 `SP3`/`CLK`/`ERP`/`OSB` files exist for offline PRIDE PPP-AR. | `EXP-001, 007, 009, 017` |
| `NLGCP-LIM-003` | `B-05` | `CRITICAL` | **Single-day verified 2024 scope & sparse 3-ref extrapolation:** Only DOY `2024/026` admits 4 verified IGS20 stations (`105–1,029 km`), forcing extrapolation in every fold and causing `-0.53` fewer satellites/epoch on 2024 atmospheric VRS. | `EXP-001, 003, 006, 016` |
| `NLGCP-LIM-004` | `B-08` | `HIGH` | **Offline non-causal atmospheric arc leveling:** `common_arc` and `nighttime` ionospheric leveling use full-24h windows (look-ahead), demonstrating offline potential rather than causal real-time streaming. | `EXP-007, 009, 016, 017` |
| `NLGCP-LIM-005` | `GN-01` | `CRITICAL` | **No authorized live or recorded Nigerian CORS/NTRIP stream:** Phases 9, 10, 11, and 12 transport/encoding remain synthetically validated only (`REAL LIVE INGESTION = BLOCKED`). | `EXP-011, 012, 013, 014` |
| `NLGCP-LIM-006` | `B-06` | `HIGH` | **No independent non-RTKLIB RTCM MSM4 decoder or second positioning engine:** gLAB v6.0.0 decodes `1005`/CRC-24Q only; MSM4 (`1074`/`1084`) and all rover positioning rely solely on `RTKLIB v2.4.2-p13`. | `EXP-009, 013, 016, 017` |
| `NLGCP-LIM-007` | `B-07` | `HIGH` | **GPS-only VRS & missing GLONASS FCN / antenna RTCM messages:** VRS emits GPS `1005`+`1074` only; standalone synthetic `1084` lacks FCN/`1020`/`1230`; `1006`/`1007`/`1008`/`1033`/Galileo/BeiDou are absent. | `EXP-009, 013, 016, 017` |
| `NLGCP-LIM-008` | `B-09` | `CRITICAL` | **Day 7 security blockers (`SEC-01`–`SEC-10`):** Plaintext auth, static credentials, missing pre-auth limits/rate limiting, Go HTTP timeouts, and Compose `CHANGE_ME` defaults forbid non-`127.0.0.1` deployment. | `EXP-014, 015` |
| `NLGCP-LIM-009` | `B-10` | `HIGH` | **Zero hardware-in-loop (HIL) or field rover validation:** No commercial GNSS receiver testing or surveyed Nigerian control-point campaign executed (`Phase 16 Not Started`). | `EXP-016, 017` |
| `NLGCP-LIM-010` | `B-01` | `MEDIUM` | **Missing external DCB/IONEX & incomplete raw WUM product retention:** `external-products/igs/2024/` has `0` files; PRIDE cleaned raw WUM `CLK`/`BIA`/`ERP` after converting to internal files while preserving `ORB.SP3`. | `EXP-001, 007, 016` |
| `NLGCP-LIM-011` | `B-05` | `MEDIUM` | **Equatorial scintillation & single-day seasonal coverage:** Post-sunset irregularities (`18–24 UTC`, ROTI up to `3.07 TECU/min`) still left `1.03–1.33 m` kinematic H RMSE even with best atmospheric VRS. | `EXP-007, 016, 017` |
| `NLGCP-LIM-012` | `GN-05` | `LOW` | **Provisional Phase 4 QC calibration & partial early CLI provenance:** QC thresholds await Level 3 field calibration; several early feature-branch pilots (`EXP-001`–`008`, `010`–`012`) did not archive shell command strings or environment snapshots uniformly. | `EXP-002..006, 008` |
