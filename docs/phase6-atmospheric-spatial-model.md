# Phase 6 — Atmospheric & Spatial Error Model: Observation Model

## 1. Objective

Estimate and model the spatially correlated GNSS error field across the
admitted DOY 026 reference network (ABFC, EKAK, MGBO; target PHRI) from
satellite-level observables, producing a Phase 7-ready correction
representation. No VRS is generated in Phase 6.

## 2. Symbols, units, frames, conventions

| Symbol | Meaning | Unit |
|---|---|---|
| `P_i`, `Φ_i` | code / carrier-phase observation on band `i` | m / cycles |
| `ρ` | geometric range | m |
| `c`, `dt`, `dT` | light speed; receiver / satellite clock bias | m/s; s |
| `I_1`, `I_i` | slant ionospheric delay (L1 / band i, positive = delay) | m |
| `T` | slant tropospheric delay | m |
| `λ_i`, `N_i` | wavelength / integer ambiguity | m / cycles |
| `γ` | `(f1/f2)^2` frequency-squared ratio (GPS ≈ 1.6469) | — |
| `GF` | geometry-free combination | m |
| `SD_AB`, `DD` | single / double difference | m |
| `m_h`, `m_w` | Niell hydrostatic / wet mapping | — |

* Coordinate frame: IGS20 at the observation epoch (verified PRIDE PPP-AR
  coordinates in `processed/single-base/derived-coordinates.json`).
* Time system: GPST internally (UTC + 18 s for 2024); epochs stored as
  ISO-8601 UTC with `+00:00`.
* Sign: `GF = λ1·L1 − λ2·L2` in metres; `SD_AB = GF_A − GF_B`.
* Code files: `research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/`.

## 3. Undifferenced observation equations

Code and carrier phase on frequency band `i` (Hofmann-Wellenhof et al. 2008):

```text
P_i = ρ + c·(dt − dT) + I_i + T + b_P,i + ε_P,i
Φ_i = ρ + c·(dt − dT) − I_i + T + λ_i·N_i + b_Φ,i + ε_Φ,i
```

First-order ionosphere scales with `1/f²`: `I_i = I_1·(f1²/fi²)`.
Higher-order terms (mm-level) are neglected and documented as a limitation.

## 4. Geometry-free combination (ionosphere proxy)

```text
GF = Φ_1·λ_1 − Φ_2·λ_2   [metres]
   = (I_1 − I_2) + (λ_1·N_1 − λ_2·N_2) + (b_Φ,1 − b_Φ,2) + noise
   = I_1·(1 − γ) + const_per_arc + noise
```

Geometry, clocks, and troposphere cancel. With GPS
`f1 = 1575.42 MHz`, `f2 = 1227.60 MHz` (IS-GPS-200):

```text
γ = (f1/f2)² ≈ 1.6469444444
I_1 = −GF / (γ − 1) ≈ −1.5457277802 · GF
```

First-order slant TEC: `TECU = I_1·f1² / (40.308·10¹⁶)` (≈ 0.162 m/TECU
on L1). Implemented in `combinations.py`.

**Restriction:** GF is derived for GPS L1/L2 only. GLONASS FDMA channel
numbers are absent from the RINEX 2 headers, and generic RINEX 2 codes for
other constellations have ambiguous band mappings, so non-GPS combinations
are excluded with explicit reasons (`observations.py`).

## 5. Single and double differences

Between-station single difference on common epochs/satellites:

```text
SD_AB = GF_A − GF_B   (satellite biases cancel)
```

Per-station, per-satellite continuous arcs are segmented on observation
gaps (a missing epoch, or missing L1/L2, ends the arc and the next valid
sample opens a *new* arc — pre-gap arc numbers are never rejoined, since
the ambiguity state after a gap is unknown), on epoch spacings wider than
1.5x the effective sampling step (`header interval x epoch stride`, so
decimated datasets do not shred into singleton arcs), on *changes* of the
L1/L2 LLI flags between consecutive epochs, and on GF jumps above 0.5 m
(a documented cycle-slip segmentation heuristic). Each arc is detrended
by its median, removing the constant-per-arc ambiguity/hardware-bias
term. The remainder is an **arc-detrended double-differenced residual
proxy** (`GF_SD_ARC_DETRENDED`): differential ionosphere plus unmodelled
effects. It is never labelled absolute TEC.

LLI changes (rather than any nonzero LLI) delimit arcs because a flag
that is constant across a day cannot encode per-epoch events. Evidence:
the PHRI00NGA DOY 026 file carries a static LLI=4 on every L2 observable
(Trimble NETR9/converter annotation), yet its header declares full-cycle
tracking (`WAVELENGTH FACT L1/2 = 1 1`), its L1/L2 cycle ratio equals
`f1/f2` (1.2834, proving full-cycle L2), its GF series is smooth and
physical, and the same file supported 100% RTKLIB availability in
Phase 3/5. Transitions (`4 -> 5` loss-of-lock, `-> blank`) still open new
arcs, and the GF-jump test provides independent slip protection.

RINEX 2 parsing consumes exactly `ceil(ntypes/5)` lines per satellite,
including blank lines for absent observables (e.g. SBAS satellites with
only C1). Blank lines inside an observation block are structural and are
never skipped: skipping them desynchronises every later record (observed
failure mode on the real archive: L1/L2 columns misassigned, metre-level
GF replaced by 1e7 m garbage).

## 6. Satellite geometry

Elevation/azimuth come from verified station ECEF plus satellite ECEF from
GPS broadcast navigation (RINEX 3 merged BRDC) propagated with the
IS-GPS-200 Table 20-IV Kepler solution. Signal-travel-time Earth-rotation
correction is omitted (documented ~3 m simplification, negligible for mask
and mapping use). Non-GPS satellites and epochs without a broadcast record
fail closed. The navigation file hash is recorded with every geometry.

## 7. Tropospheric a priori chain

Station meteorology is unavailable, so the chain is strictly a priori and
labelled `not measured station meteorology`:

* Berg (1948) standard pressure `P = 1013.25·(1 − 2.2557·10⁻⁵·h)^5.2559`;
* Saastamoinen (1972) `ZHD = 0.0022768·P / (1 − 0.00266·cos2φ − 0.00028·h_km)`;
* standard wet a priori `ZWD = 0.12·exp(−h/2000)` (documented default);
* Niell (1996) hydrostatic/wet mapping functions (undefined below 3°).

Between-station single differences of the a priori slant form the
`troposphere_proxy`. Implemented in `troposphere.py`.

## 8. Spatial error representation

Per epoch/satellite/reference, relative to a datum reference (the first
listed reference station):

```text
ionosphere_proxy_m   SD ionospheric residual proxy (m)
troposphere_proxy_m  SD a priori slant difference (m)
combined_residual_m  sum where both exist (else partial/null + reason)
```

Unsupported fields are null with reasons (`spatial.py`). The datum
station's single difference against itself is identically zero, so one
explicit zero record per (epoch, satellite) anchors the differential
field at the datum (`datum <station> self-difference identically zero`
in provenance). Without it the datum-target leave-one-out fold would
have no observed values and the target fit would never see three
references. Target-fit reference sets exclude the target station's own
record (predicting a station from its own value at distance zero would
be leakage, not modelling).

## 9. Interpolation candidates

`zero` (control), `nearest` (transfer control), `idw` (power 2.0), `planar`
(least-squares plane in local ENU; singular/collinear geometry returns null
instead of coefficients). Minimum references: planar 3, IDW 2, nearest 1,
zero 0. Targets outside the reference bounding circle are flagged
`extrapolated`. No kriging: three references cannot support it.

## 10. Validation

Leave-one-out over station rotations (min 2 remaining refs): predict the
satellite-derived term at the held-out station, compare with its observed
SD proxy. Metrics: bias, MAE, RMSE, std, predicted–observed correlation,
coverage within 0.05 m. Model ranking uses only the comparison samples
predicted by *every* model (identical-sample comparison; per-model
evaluable counts are reported alongside), so a model that fails closed
on hard samples is not rewarded for skipping them. Every model is ranked
against zero/nearest on those identical samples; simpler winners are
reported, not hidden. Decorrelation (RMS-vs-distance slope) is labelled
representative/pilot evidence only.

## 11. Limitations

* One day (DOY 026), four stations, three references: sparse geometry
  fundamentally limits interpolation; planar fits are exact-through-points
  with no redundancy.
* GPS-only ionospheric proxies; no measured meteorology; first-order
  ionosphere only; broadcast (not precise) orbits.
* Stride-decimated arcs can hide small slips inside skipped epochs; the
  0.5 m GF-jump test only guards kept-epoch differences. A full-rate
  rerun must invalidate via fingerprint (enforced).
* Position-domain RMSE is never an atmospheric observable (fail-closed).

## 12. Phase 7 interface

Phase 7 consumes: per-epoch/satellite planar coefficients or IDW fields at
the target (`models/target-predictions.csv`), LOOCV winner and residuals
(`validation/loocv.json`), provenance fingerprints (`derive-status.json`),
and the BLOCKED/PARTIAL status contract. VRS synthesis itself is out of
scope here.

## 13. References

* Hofmann-Wellenhof, Lichtenegger & Wasle, *GNSS – Global Navigation
  Satellite Systems* (Springer, 2008) — observation equations, combinations.
* IS-GPS-200 (Navstar GPS Space Segment/Navigation User Segment Interfaces)
  — L1/L2 frequencies, broadcast orbit equations.
* Klobuchar, J.A. (1987), Ionospheric time-delay algorithm — first-order
  ionospheric treatment background.
* Saastamoinen, J. (1972), Atmospheric correction — zenith delay.
* Niell, A.E. (1996), Global mapping functions — tropospheric mapping.
* Berg, H. (1948), standard atmosphere pressure profile.
* Wanninger, L. (1995/2004); Dai et al. (2003); Landau et al. — network RTK,
  distance-dependent errors, VRS interpolation background.
* Hofmann-Wellenhof et al. (2008); Leick et al., *GPS Satellite Surveying*
  — double differencing and ambiguity handling.
