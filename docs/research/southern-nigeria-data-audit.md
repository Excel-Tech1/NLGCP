# Southern Nigeria NIGNET data audit and VRS geometry assessment

**Audit state: `AUDIT_BLOCKED_COORDINATE_PROVENANCE`.** The archive was
inventoried and exploratory geometry was calculated, but no station has
independently verified coordinates and no matching 2011 navigation products
were available. No positioning or correction experiment was run.

## Executive summary

The local `NIGNET2011.zip` contains 3,018 readable RINEX observation files
from 11 stations across 2011-01-01 through 2011-12-31. All members passed the
pipeline's integrity and header checks, and no exact duplicate was found.
The archive was read in place, not extracted. The archive SHA-256 is
`8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf`.

Using an explicitly configured latitude screen of 8.5°N for exploratory
Southern Nigeria geometry selects CLBR, GEMB, RUST, ULAG, and UNEC. Their
header coordinates produce a few contained held-out geometries, unlike the
four extrapolative folds in the historical Phase 6 network. However, all five
coordinates remain provisional. The best contained three-reference case has
only two common observation-window dates; the best contained four-reference
case has no common observation window. A four-station southern group has 33
common window dates, but each tested held-out target is outside its reference
triangle. No date has matching 2011 navigation evidence. This is not enough to
justify a controlled VRS or network-RTK experiment yet.

## Dataset and integrity

### Observed

- Incoming archive: `/home/excellence/nlgcp-data/incoming/southern-nignet/NIGNET2011.zip`
- Archive size: 5,820,369,120 bytes; 3,018 file members; 18,859,982,918 declared
  uncompressed bytes.
- Date labels: 2011-01-01 through 2011-12-31.
- 3,018/3,018 observation files were parsed, hashed, and marked integrity
  `OK`; no navigation file was present in the archive.
- No exact-content duplicate or conflicting basename was reported.
- Epoch records were scanned in all observation files: 8,484,486 in total.
  2,848 files had 2,880 scanned epochs; the other 170 had fewer. These are
  inspected records, not positioning-quality admission.
- The data directory had the ZIP only; no station coordinate files, SINEX,
  station logs, or acquisition README were present. No Hatanaka conversion was
  needed for the discovered observation files.

### Station coverage observed

| Station | Observation files | Observed days | Header coordinate (approx. lat, lon) |
|---|---:|---:|---:|
| ABUZ | 365 | 365 | 11.1517°, 7.6487° |
| BKFP | 365 | 365 | 12.4686°, 4.2292° |
| CGGT | 365 | 365 | 10.1231°, 9.1183° |
| CLBR | 36 | 36 | 4.9503°, 8.3516° |
| FUTY | 360 | 360 | 9.3497°, 12.4978° |
| GEMB | 2 | 2 | 6.9172°, 11.1839° |
| MDGR | 261 | 261 | 11.8381°, 13.1310° |
| OSGF | 299 | 299 | 9.0277°, 7.4863° |
| RUST | 304 | 304 | 4.8018°, 6.9785° |
| ULAG | 301 | 301 | 6.5173°, 3.3976° |
| UNEC | 360 | 360 | 6.4248°, 7.5050° |

RINEX versions and headers were inspected per file. The observations are
legacy RINEX 2.11. The common declared interval is 30 seconds. The pipeline
preserves each header's declared time system; it does not convert GPS/UTC or
other scales. Epoch counts and intersections describe file records and header
windows, not signal completeness or equal-epoch positioning input.

## Coordinate provenance

### Observed

- 0 stations are `VERIFIED`, 11 are `PROVISIONAL`, and 0 are `MISSING`.
- The coordinates used for geometry came from RINEX `APPROX POSITION XYZ`.
  No authoritative frame, coordinate epoch, or source record was available.
- Four comparisons to the 2024 RINEX header registry differ by 1.93–5.59 m.
  Those values are diagnostic only because the two epochs and reference frames
  are undocumented; they do not verify either coordinate set.

### Interpretation

All reported baseline and containment results are exploratory calculations
from provisional coordinates. They cannot support authoritative interpolation
claims or replace the coordinates used in existing NLGCP experiments.

## Simultaneous observations and navigation

### Observed and calculated

- Header-window intersections exist on 365 calendar dates for at least one
  station pair. This is a pairwise network summary, not a 365-day full-network
  overlap.
- Among the five geographically screened stations, 241 dates have at least
  three stations with observation sessions and 35 dates have at least four;
  no date has all five. Exact common-window intersection is stricter than
  same-date file presence.
- The strongest reported held-out network overlap is CLBR + RUST + ULAG + UNEC:
  33 distinct common-window dates between 2011-03-20 and 2011-12-31, totaling
  2,617,890 seconds of header-window intersection. This is not a continuous
  33-day run and not an epoch-count guarantee. Each corresponding held-out
  triangle test places its target outside the reference hull.
- The contained three-reference configuration GEMB + RUST + ULAG → UNEC has
  two common-window dates (2011-09-09 and 2011-10-14), totaling 21,540 seconds.
- The contained four-reference configuration CLBR + GEMB + RUST + ULAG → UNEC
  has zero common-window dates. The five-station set has zero simultaneous
  calendar dates because GEMB has only two observed days and neither coincides
  with the other four stations' common calendar-day set.
- 220 BKG/IGS broadcast navigation products were found in the external vault,
  with 2024 date labels. There were zero matching navigation dates for the
  2011 observations; all 365 observation dates lack a matching product in the
  inspected inventory. No additional product was downloaded.

## Exploratory network geometry

The geographic selection was configured as latitude ≤8.5°N. This is a
reproducible screening bound for this assessment, not an official definition
of Southern Nigeria. The geometry pipeline converted ECEF positions to
geodetic coordinates and local ENU before computing hulls and areas.

### Configuration counts

The five selected stations yield 10 three-reference combinations, 5
four-reference combinations, and 1 five-reference combination. The 25
leave-one-out target rows comprise 2 `INSIDE` and 18 `OUTSIDE` results for
three-reference sets, plus 1 `INSIDE` and 4 `OUTSIDE` results for four-reference
sets. There is no held-out target when all five stations are references.

### Best exploratory candidates

| References → target / set | Geometric result | Temporal result | Limitation |
|---|---|---|---|
| 3 refs: GEMB + RUST + ULAG → UNEC | `INSIDE`; hull area ≈91,015 km²; longest reference baseline ≈861.5 km; longest target baseline ≈454.4 km | 2 dates; 21,540 s total | All coordinates provisional; no matching navigation |
| 4 refs: CLBR + GEMB + RUST + ULAG → UNEC | `INSIDE`; hull area ≈105,073 km²; longest reference baseline ≈861.4 km; longest target baseline ≈454.4 km | 0 common-window dates | All coordinates provisional; no matching navigation |
| 5 refs: CLBR + GEMB + RUST + ULAG + UNEC | Hull area ≈105,087 km²; longest baseline ≈861.4 km; minimum triangle angle indicator ≈4.43° | 0 common dates across all five | No held-out target; all coordinates provisional; no matching navigation |

The geometry ranking is a transparent evidence ordering, not an accuracy
ranking. It gives priority to coordinate provenance, containment, available
window dates, navigation, and then target distance. Since no coordinate is
verified, no candidate is `GEOMETRY_FEASIBLE`; the ranking state is
`COORDINATE_PROVENANCE_INSUFFICIENT`.

## Comparison with existing NLGCP results

The reviewed Phase 6/7 historical baseline remains unchanged: the 2024 DOY 026
held-out network folds were extrapolations, ZERO remained the best evaluated
spatial model, and VRS remained geometry-only and not operationally approved.
The Southern Nigeria provisional coordinates produce more contained
three-reference target cases (2 of 20) and one contained four-reference case
(1 of 5). They therefore suggest a potentially more favorable geometry for
some target/reference selections than the historical four-fold network.

That suggestion is not yet an authoritative improvement finding. The contained
candidate with overlap lasts only two dates; the candidate with 33 dates is
extrapolative in every tested rotation. The five-station network has no full
same-day overlap, and its largest reference baseline is about 861 km. No
matching 2011 broadcast navigation products or verified control coordinates
were found. Thus the evidence does not yet show a better basis for controlled
network RTK/VRS experiments.

## Scientific decision

**Inferred:** the southern station distribution may offer improved polygon
containment for selected held-out stations, but the signal is provisional and
temporally weak. Current evidence is insufficient to conclude that it supports
spatial interpolation experiments better than the 2024 baseline.

**Unknown:** authoritative station coordinates and their frames/epochs;
antenna reference-point consistency; exact usable common-epoch counts after
full observation parsing and scientific QC; 2011 navigation products; and any
positioning or correction accuracy. No RTK, network correction, or VRS run was
performed, and no accuracy or FIX-improvement claim is made.

## Recommended next experiment

First obtain authoritative coordinates with documented frame, epoch, monument
or antenna reference point, and station identity for the Southern Nigeria
sites. Acquire suitable 2011 broadcast navigation data through the documented
offline process. Then re-run coordinate-gated availability and QC; select a
held-out configuration only if verified coordinates preserve containment and
the station files have adequate same-time-scale common epochs. Freeze a
reviewed protocol before running a small controlled offline network/held-out
comparison. Do not generate operational corrections or promote a non-zero
model on the present evidence.

## Reproducibility and evidence

The reusable inventory/geometry code is in `research/southern_network_audit/`.
The corrected run is stored outside Git at
`/home/excellence/nlgcp-data/validation/southern-nignet/run-20261030T125136Z/`
and contains the raw archive manifest, per-file hashes, CSV/JSON inventories,
coordinate provenance/discrepancies, coverage and window matrices, geometry
tables/GeoJSON, navigation inventory, audit summary, and derived SHA-256
manifest. Its station/day availability matrix contains 3,018
`OBSERVED_WINDOW_SCANNED` station-days and 997 missing station-days. The earlier
run `run-20261030T122509Z` is marked superseded and must not be used for epoch
date/count conclusions; intermediate run `run-20261030T123832Z` has the
corrected epoch scan but predates the station/day date-key fix, so use the
final `run-20261030T125136Z` for the complete report.

No archive was extracted, no raw observation was modified, and no raw GNSS
data or credentials were added to Git.
