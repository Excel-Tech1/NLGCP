# NLGCP Interim Scientific Expansion — thesis-ready evidence (2024 multi-day)

Scope: one end-to-end scientific-validation sprint strengthening Phases 2, 3,
5 and 6 while authorized live CORS/NTRIP access remains pending. All
statements below describe the evaluated 2024 OSGoF/NIGNET subset only. No
national-level claim is made. Branch: `interim/scientific-expansion`.

## 1. Methodology

- Frozen admission gates were reused without modification: Phase 4 QC
  profile classification, verified IGS20 PRIDE PPP-AR coordinates with an
  observation-epoch match, temporally compatible broadcast navigation, and
  the pinned RTKLIB `rnx2rtkp v2.4.2-p13` configuration
  (SHA-256 `b4a96cd0d5ffc00b44dab3a4fda214318c9f69cccee52128aec8bc26ad4f7d21`).
- Broadcast navigation was acquired exclusively from the public BKG/IGS
  archive with per-file provenance (URL, retrieval UTC, SHA-256) and
  RINEX-level validation (gzip integrity, header, day compatibility,
  non-zero ephemeris count). HTTP success was never equated with usability.
- Precise MGEX/WUM products for per-day coordinate derivation were probed
  across seven public endpoints (WHU FTP/HTTPS, bdspride FTPS, IGN FTP, GFZ
  FTP, CDDIS HTTPS, BKG MGEX) and found inaccessible without registration;
  per-day PRIDE PPP-AR coordinates therefore remain BLOCKED. No coordinate
  was reused across days and no admission threshold was changed.
- Failed and blocked experiments are retained in every denominator.

## 2. Dataset

- Canonical 2024 archive: 1290 station-days across 8 stations on 294 days
  with observations (ABFC 276, EKAK 269, PHRI 221, MGBO 198, UNEC 105,
  FUTY 104, BKFP 87, ULAG 30).
- Days with >=2 stations: 266. Days with >=3: 222. Days with >=4: 198.
- Coordinated full-session subset (ABFC/EKAK/MGBO/PHRI, the only stations
  with scientifically valid coordinates): >=2 stations on 220 days, >=3 on
  171 days, all 4 on 36 days.
- Navigation coverage before the sprint: 1 day (DOY 026). After the sprint:
  220 candidate days (including DOY 026), each validated at RINEX level.
  Coverage improvement: 1 -> 220 days.
- Processable under frozen gates: 1 day (DOY 2024/026). Primary blocker for
  the remaining 219 multi-station candidate days is
  `BLOCKED_COORDINATE_INTERVAL` (verified coordinates exist only at the
  DOY-026 observation epoch); the navigation blocker was removed for all
  220 candidate days.

## 3. Single-base RTK (Stage C)

- The admitted DOY-026 matrix was completed to all six unordered pairs
  (frozen static configuration; per-base configuration hashes reproduced
  exactly): EKAK->MGBO (979.075 km, FLOAT-only, horiz RMSE 1.778 m /
  3D 2.589 m) and MGBO->PHRI (1029.034 km, 2 isolated FIX epochs of 2880,
  horiz 1.802 m / 3D 2.598 m, reproducing the independent Phase 5
  network-input solution to three decimals). The MGBO->PHRI fixes are
  treated as effectively FLOAT-only per Phase 5 precedent; no
  fixed-ambiguity accuracy is claimed.
- Across six successfully processed baselines (105.553-1029.034 km, 17280
  epochs total), ambiguity-fixed solutions occurred in one run (2 epochs,
  0.07%); five runs were strictly FLOAT-only. Under the frozen RTKLIB
  broadcast-ephemeris configuration, fixing does not occur consistently
  anywhere in the evaluated subset.
- Baseline distance is descriptively associated with horizontal RMSE
  (Pearson r = 0.970, 95% CI 0.746-0.997, n = 6) and 3D RMSE (r = 0.870,
  95% CI 0.198-0.986, n = 6). With n = 6 no causal or predictive claim is
  made; the intervals are reported so the limitation is explicit.
- DOY 026 remains the only admittable day, so its representativeness
  across seasons cannot be tested. Within-day, the shortest baseline
  (EKAK-PHRI, 105.553 km) performs best (horiz 0.968 m) and error grows
  with distance, but FLOAT-only behavior persists at every distance.

## 4. Network experiments (Stage D)

- One admitted network day (DOY 2024/026, references ABFC/EKAK/MGBO,
  held-out rover PHRI). Nearest single reference (EKAK->PHRI, 0.968 m
  horiz) outperforms the three-baseline network-input mean (1.288 m
  horiz): no network improvement is observed or claimed.
- Held-out geometry classification: all four possible held-out rotations
  are EXTRAPOLATION (triangle-containment check recomputed from verified
  coordinates in this sprint; agrees with the reviewed geometry-v3
  record). No admitted 2024 geometry supports genuine interpolation, so
  interpolation-specific analysis remains INSUFFICIENT DATA.

## 5. Phase-6 spatial models (Stage E)

- No new admittable day exists, so the multi-day re-evaluation reports the
  reviewed single-day evidence unchanged (regression requirement): on
  15948 identical LOOCV samples, ZERO RMSE 3.076 m beats IDW 3.352 m,
  NEAREST 3.757 m and PLANAR 14.373 m. Fold-level results (n = 3987 each)
  are tabulated in Table G.
- Model decision: ZERO_REMAINS_BEST. Promoted non-zero model: NONE. The
  Phase 6 conclusion (no promoted model) remains supported; the
  multi-day promotion gate (multiple independent days, interpolation
  cases, consistency) cannot be exercised until per-day coordinates exist.
- Seasonal, ionosphere-magnitude and troposphere-absolute analyses are not
  performed beyond the existing single-day proxies: the geometry-free
  observable remains a relative ionospheric proxy (not absolute TEC) and
  tropospheric terms remain PROVISIONAL standard-atmosphere assumptions.

## 6. Limitations (discussion-ready)

1. The 2024 evidence base remains one admittable day for positioning; all
   accuracy statements are conditional on DOY 2024/026.
2. 219 multi-station candidate days are navigation-ready but
   coordinate-blocked; unlocking them requires authorized MGEX/WUM product
   access for per-day PRIDE PPP-AR derivation (specified, not substituted).
3. Stations BKFP (invalid coordinate), UNEC/FUTY/ULAG (no coordinate entry)
   cannot participate under frozen gates.
4. Distance/RMSE associations use n = 6 and are descriptive only.
5. No measured meteorology exists; troposphere stays provisional.
6. No interpolation geometry was available; non-zero spatial models were
   tested in extrapolation only.

## 7. Figure and table references

- Tables A-J: `${NLGCP_DATA_ROOT}/validation/scientific-expansion-2024/statistics/tables/`
- Figures 1-12 with SHA-256 provenance sidecars:
  `${NLGCP_DATA_ROOT}/validation/scientific-expansion-2024/statistics/figures/`
- Coverage/overlap/processable catalogs:
  `${NLGCP_DATA_ROOT}/validation/scientific-expansion-2024/inventory/`
- Batch records: `.../single-base/batch-sb-matrix-completion-001.json`
