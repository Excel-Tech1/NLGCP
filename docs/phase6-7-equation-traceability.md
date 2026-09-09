# Phase 6/7 equation traceability — 2026-09-09

This table covers the implemented scientific calculations, including helper
geometry and diagnostic statistics. It is an equation/source audit, not evidence
of positioning accuracy. Code locations are relative to the repository root;
`P6` means `research/atmospheric_spatial_model/src/nlgcp_atmospheric_model/`,
`P7` means `research/vrs_generator/`. Tests with constructed inputs are
**SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS**.

## Reviewed sources

- [ESA/UPC basic observables](https://gssc.esa.int/navipedia/index.php/GNSS_Basic_Observables): code has positive ionospheric delay; carrier has negative ionospheric delay.
- [ESA/UPC combinations](https://gssc.esa.int/navipedia/index.php/Combination_of_GNSS_Measurements): carrier geometry-free is L1 minus L2 in metres.
- [ESA/UPC ECEF–ENU](https://gssc.esa.int/navipedia/index.php/Transformations_between_ECEF_and_ENU_coordinates): rotation uses ellipsoidal latitude for an ellipsoidal normal.
- [IGS RINEX 3.04](https://files.igs.org/pub/data/format/rinex304.pdf), GPS navigation table A6: SI radians/radians per second, continuous GPS week, fixed-width fields and optional trailing spares.
- [IGS RINEX 2.11](https://files.igs.org/pub/data/format/rinex211.txt): observation calendar time system, phase cycles, LLI, continuation and event records.
- [ESA/UPC Niell mapping](https://gssc.esa.int/navipedia/index.php/Mapping_of_Niell): continued fraction, latitude interpolation, seasonality and height correction; identifies Niell (1996), *Global mapping functions for the atmosphere delay at radio wavelengths*.
- [Pinned RTKLIB source](https://github.com/tomojitakasu/RTKLIB/tree/71db0ffa0d9735697c6adfd06fdf766d0e5ce807/src): locally byte-verified `rtklib.h`, `rtkcmn.c`, `rinex.c`, `ephemeris.c`; GPS constants, Kepler propagation, coordinate conversion, Niell coefficients, Sagnac and satellite clock treatment.
- [PROJ geodesics](https://proj.org/en/stable/geodesic.html): ellipsoidal inverse via its GeographicLib geodesic implementation, exposed by the already installed `geod` command.

## Equations and implementation

| Calculation | Variables, units, convention and assumptions | Source / location | Evidence and status |
|---|---|---|---|
| `d = sqrt(dx²+dy²+dz²)` | Station ECEF in m; unsigned 3D chord, including height | Euclidean norm; P6 `spatial.baseline_length_m`; Phase 5 `geometry.baseline_length_m`; P7 `models.anchor_selection` | Six real pairs checked with `math.dist`, explicit historical norm and NumPy norm. VERIFIED, historical values unchanged |
| Ellipsoidal inverse distance | Geodetic latitude/longitude in degrees, WGS84 ellipsoid surface; heights excluded | PROJ `geod +ellps=WGS84 -I`; `research/scientific_validation/audit_geometry.py` | Six pairs, stored beside chord distances. VERIFIED; no reference-frame transformation implied |
| ECEF to geodetic | WGS84 `a=6378137 m`, `f=1/298.257223563`; output degrees and ellipsoidal height | Phase 3 `coordinates.ecef_to_geodetic`, reused by P6 and P7; independently checked against RTKLIB `ecef2pos` | Four PRIDE coordinates agree; synthetic equator, poles, nonfinite/centre rejection. VERIFIED; pole handling CORRECTED |
| `ENU = R(phi,lambda)*(XYZ-origin)` | Rows E,N,U; geodetic origin radians; m; shared reference ECEF centroid for a plane | ESA/UPC ENU; P6 `spatial.ecef_to_local_enu` | Cardinal vectors, norm preservation, common-origin tests. Geocentric latitude CORRECTED. Different origins do not yield componentwise antisymmetric ENU |
| `origin = mean(reference XYZ)` | Arithmetic ECEF centroid, converted to geodetic; held-out target excluded | Definition of centroid; P6 `interpolation._centroid` | Stored origin and all ENU coordinates for every rotation. VERIFIED |
| Triangle area and barycentric weights | Half absolute 2D determinant in m²; barycentric weights sum to one; negative weight means outside | Linear algebra, P6 `interpolation.reference_triangle_area_m2`, `barycentric_coordinates` | Determinant cross-check, boundary/degenerate tests, four real triangles. CORRECTED containment; Phase 5 Heron area remains valid 3D chord-triangle area |
| `w_i=(d_min/d_i)^p / sum_j((d_min/d_j)^p)` | ECEF chord m, `p=2`; equivalent normalized inverse-square weights without overflow at very small d; exact coincident point takes its value | Explicit candidate definition, P6 `interpolation.interpolate` | Deterministic exact and midpoint values, positivity, minimum reference count. VERIFIED/CORRECTED numerical scaling; no empirical gain assumed |
| `z = a E + b N + c` | z m, slopes m/m, common ENU frame; fit references only | Least squares via NumPy SVD, P6 `interpolation.plane_diagnostics` | Rank, scaled condition number and origin recorded. Singular and condition ≥ `1/sqrt(eps)` rejected (numerical precision safeguard, not scientific service threshold). CORRECTED normal-equation solver |
| `lambda=c/f`; `gamma=(f1/f2)²` | GPS L1 1575420000 Hz, L2 1227600000 Hz; c=299792458 m/s; positive wavelengths | RTKLIB/IS-GPS frequencies; P6 constants/observations; P7 observations | Existing wavelength tests and observation-equation sign test. VERIFIED |
| `GF=lambda1 L1-lambda2 L2=(gamma-1) I1 + ambiguity/bias` | Carrier cycles converted to m; phase ionosphere is **negative**, so subtracting phases gives positive `(gamma-1) I1` | ESA/UPC observables/combinations; P6 `combinations.gf_phase_m`, `gf_to_l1_iono_m` | Independent construction from `phase_i=rho-I_i`; old negative conversion factor CORRECTED |
| `g'_s(t)=GF_s(t)-median_arc(GF_s)` | Station/satellite arcs, retrospective whole-arc detrending in m; unresolved absolute offset | Explicit research preprocessing assumption; P6 `combinations.arc_detrend`, `ionosphere.station_gf_arcs` | Gap/stride/LLI regression tests. PROVISIONAL proxy, never absolute TEC or ambiguity resolution |
| `I'_A-I'_B` | Between-station single difference after separate station arc medians; sign A minus B | P6 `ionosphere.pair_sd_proxies` | Six real pair series; sign corrected, pair RMS unchanged. Legacy `DD_DETREND_METHOD` descriptive string is imprecise: this is **not** a between-satellite double difference, nor subtraction of a single pair median. This table defines the audited estimand |
| `TECU=I1*f1²/(40.308e16)` | First-order slant variation, electrons per square metre converted to TECU | P6 `combinations.gf_iono_to_tecu`, constants | Scaling tested; ESA source supports rounded 40.3. Exact 40.308 attribution to the old bibliography: **REFERENCE REVIEW REQUIRED**. Retained convention; not used to synthesize VRS |
| `gradient=SD/(baseline_m/1000)` | m/km; signed pair variation, not an estimated spatial derivative of a validated field | Definition; P6 `ionosphere.spatial_gradient_proxy` | Deterministic scale test and preserved real baseline matrix. PROVISIONAL interpretation |
| `P=1013.25*(1-2.2557e-5 h)^5.2559` | h nonnegative ellipsoidal metres in the pilot, P hPa, no measured meteorology | Repository standard-atmosphere approximation; P6 `troposphere.standard_pressure_hpa` | Sea-level value tested. Original “Berg 1948” attribution **REFERENCE REVIEW REQUIRED**; pinned RTKLIB uses a slightly different exponent 5.2568. PROVISIONAL a priori, not a measurement |
| `temperature=15-0.0065 h` | Celsius, lapse-rate assumption; unused by the current slant pipeline | P6 `troposphere.standard_temperature_c` | Explicit standard-atmosphere assumption, not observed temperature; no VRS contribution |
| `ZHD=.0022768 P/(1-.00266 cos(2 phi)-.00028 h_km)` | Zenith hydrostatic m; pressure hPa, latitude rad, height km in denominator | Saastamoinen treatment in RTKLIB `tropmodel`; P6 `troposphere.saastamoinen_zhd_m` | Numeric 45°/sea-level reference test. VERIFIED equation, PROVISIONAL meteorological inputs |
| `ZWD=.12 exp(-max(0,h)/2000)` | Zenith wet m; .12 m sea-level default and 2 km scale are research assumptions, not estimates | P6 `troposphere.standard_zwd_m` | Defaults explicitly documented/tested. PROVISIONAL; original value is not a constant .12 m at every station |
| `m(e)=(1+a/(1+b/(1+c)))/(sin(e)+a/(sin(e)+b/(sin(e)+c)))` | e converted degrees→radians; dimensionless mapping | Niell source and pinned RTKLIB `nmf`; P6 `troposphere.niell_mapping` | Zenith=1; 48 native cross-checks. VERIFIED |
| Niell latitude, season and height terms | Linear table interpolation; cosine season from DOY 28, southern half-year shift; hydro height correction `[csc(e)-m_height(e)]*h/1000` | Same sources; P6 hydrostatic/wet mapping | Incorrect table entries, stepwise bins, missing height/southern correction and fixed wet coefficients CORRECTED. 48 cross-checks <5e-15; pilot stations all below 15° |
| `T=ZHD*m_h+ZWD*m_w` | Slant m; pilot uses documented 10° mask; no measured met | P6 `troposphere.a_priori_slant` | Real term regeneration and model tests. PROVISIONAL atmosphere, verified calculation |
| GPS week/TOW from calendar labels | Calendar labels are GPS, no UTC leap offset; actual UTC coordinate epoch remains separate | RINEX; P6 `satellite_geometry.gps_datetime_to_tow`; P7 explicit GPS definition | Known DOY026 = week2298 TOW432000; nonzero offsets rejected. CORRECTED; new Phase 6 epoch labels omit misleading UTC suffix |
| Broadcast Kepler orbit | SI radians, eccentricity, semimajor axis, time since Toe; harmonic corrections; Earth rate `7.2921151467e-5 rad/s` | RTKLIB `eph2pos` / IS-GPS Table 20-IV; P6 `broadcast_position` | Radian scaling, factor-100 Earth rate, time, optional-field parsing and age/health selection CORRECTED. 16 real satellite/epoch comparisons <6.4e-8 m against separate native parse/propagation |
| Elevation `asin(U/r)`, azimuth `atan2(E,N)` | Degrees; geodetic station normal; azimuth [0,360) | ESA/UPC ENU; P6 `elevation_azimuth_deg` | Overhead/cardinal tests. CORRECTED geocentric normal. Phase 6 computes reception-epoch position for approximate mapping only, omitting flight time/Sagnac; no metre-level bound is claimed |
| Fold field `F_s=I'_s+T_s`; `D_s=F_s-F_d` | Complete I+T only in real pilot; datum d is lexical first remaining reference; independent station fields before subtraction | Explicit diagnostic estimand; P6 pipeline and `validation.run_loocv(reference_datum=True)` | All four folds; target perturbation cannot change its predictors. CORRECTED fixed datum leakage/artificial zero truth and partial-component mixing. Not a measured absolute atmosphere |
| Mean, MAE, RMSE, sample std, Pearson r | Signed residual observed-minus-predicted in Phase 6; finite samples; constant-series r undefined/null | Statistical definitions; P6 `metrics` | Analytic tests and identical-key comparison CSV. 0.05 m coverage is a pre-existing PROVISIONAL display threshold, not promotion or accuracy evidence |
| RMS vs distance OLS | Six pair RMS (m) regressed on chord length (km); slope m/km | P6 `metrics.decorrelation_fit` | Reproduced slope/correlation. PROVISIONAL six dependent pairs/one day, not a national law |
| `rho=norm(r_s-r_r)+omega/c*(x_s*y_r-y_s*x_r)` | Range m, satellite at signal emission; first-order Sagnac | RTKLIB `geodist`; P7 `native/geometry.c` | Existing analytic dynamic-orbit/Sagnac tests; implementation unchanged. VERIFIED calculation |
| `Delta_g=(rho_v-rho_a)-c*(dt_s,v-dt_s,a)` | Anchor→virtual displacement, satellite clock seconds; separate virtual transmit time iterated | Code observation equation and RTKLIB `satposs`; P7 native adapter | Native inclined-orbit/GPST/clock/range tests. 8 iterations, 1e-5 m numerical convergence bound, not accuracy threshold |
| `P_v=P_a+Delta_g`; `L_v=L_a+Delta_g/lambda` | Existing code m or phase cycles; anchor clock, atmospheric, bias and ambiguity datum inherited | P7 `src/nlgcp_vrs/observations.transform`; documented geometry-only control | Positive/negative displacement and identity tests; ZERO gate cannot promote a candidate. VERIFIED only as geometry-only translation |
| Code SD minus epoch/code mean | VRS-minus-actual code m, one nuisance mean removed per epoch/code | P7 `validation.residuals` | In-sample clock/code datum fitting; ≥2 satellites. Diagnostic residuals, not independent positioning accuracy |
| Carrier TD-DD | `[SD_s(t)-SD_s(t0)]-[SD_p(t)-SD_p(t0)]` in m; lexical pivot, consecutive 180 s, LLI/epoch-state screening | P7 `validation.residuals`; basic differencing algebra | Clock/constant ambiguity cancellation tests and all held-out rotations. Undetected slips may remain; no fixed ambiguities claimed |

## Scope of verification

The reviewed executable geometry and signal transformations have reproducible
numerical checks. Pressure/TEC bibliographic precision, standard wet atmosphere,
cycle-slip heuristic calibration and spatial proxy interpretation remain
provisional. None supplies a nonzero VRS correction. The two unresolved legacy
attributions above must be resolved before publication as sourced physical
models; they are not silently treated as verified citations.
