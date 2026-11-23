# Southern Nigeria Coordinate Provenance and Navigation Recovery

**Final state: `RECOVERY_COMPLETE_BUT_NO_ADMISSIBLE_NETWORK_CONFIGURATION`.**

This sprint recovered traceable coordinate publications and matching historical
broadcast navigation files for the candidate windows. It did not establish
station coordinates to the complete provenance standard, so scientific
geometry admission remains blocked. No positioning, network correction, or
VRS experiment was run.

## Executive summary

- Reviewed all 11 archive station codes against the published OSGoF NIGNET
  coordinate table. The exact four-character codes match, while monument
  continuity remains unknown.
- Found published ECEF and geodetic coordinates for all 11 stations at stated
  epoch **2011-01-01**. The presentation does not state the frame, coordinate
  reference point, antenna reference point, station-specific uncertainty, or
  monument IDs. Therefore **0 VERIFIED, 11 PROVISIONAL, 0 UNVERIFIED, 0
  MISSING**. No epoch/frame transformation was applied.
- Retrieved 70 public BKG/IGS daily RINEX 2 broadcast files: GPS and GLONASS
  files for the 33 CLBR+RUST+ULAG+UNEC candidate dates and for 2011-09-09 and
  2011-10-14. All 70 decompress and contain a matching RINEX navigation
  header and ephemeris records for the product date (54,366 records total).
  The inventory records
  PRNs and health fields; nonzero health values are present and were not
  filtered for positioning admission.
- Re-ran the workflow with a reusable, tested recovery utility on 2026-11-23.
  It independently validated 66/66 BKG GPS+GLONASS products and 33/33
  primary CLBR+RUST+ULAG+UNEC dates. CDDIS candidates remained
  `AUTHENTICATION_REQUIRED`; no CDDIS credentials were configured, used, or
  persisted. This confirms the primary-date navigation evidence and does not
  change the coordinate gate.
- Parsed exact observation epochs from the candidate files without converting
  their declared time system. All files declare GPS time. The four-station
  CLBR configuration has 85,946 exact common epochs across its 33 dates. The
  GEMB configuration has 720 across its two dates. These counts are
  timestamp intersections, not scientific observation QC.
- Recalculated southern held-out geometry from the published coordinates as
  explicitly provisional exploratory geometry: 3 inside and 22 outside among
  25 held-out rows. The coordinate gate blocks every station, so none of these
  results is an authoritative geometry ranking.

## Baseline and inputs

The previous audit commit was `b50230b963c5df412ed1204171ba89f33ad0c1d5` on
`research/southern-nigeria-data-audit`; its worktree was clean and the final
external audit run remained intact. The input archive remained at
`/home/excellence/nlgcp-data/incoming/southern-nignet/NIGNET2011.zip` and was
read in place. Its expected SHA-256 remains
`8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf`.
The previous audit’s 3,018-file, 11-station inventory and all Phase 6/7
conclusions are unchanged.

The original acquisition run is
`/home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery/run-20261030T132927Z/`.
The automated utility run is
`/home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery/run-20261123T163056Z/`.
Neither overwrites the previous audit run. Original source PDFs and
navigation files are stored there, outside Git, with SHA-256 values in the
acquisition manifests.

## Station identity and coordinate source

The OSGoF presentation, *The State and Utilization of the Nigeria CORS
Network* (Surv. A.A. Adebomehin, August 2016), prints ECEF and geodetic tables
for the 11 reviewed codes and labels both tables “Ref. Epoch: 01-01-2011”
(slides 39–40). This is direct published station-specific coordinate
evidence. It does not label the table’s reference frame or identify which
physical monument/reference point the values represent. Its station-holdings
slide documents a historical archive period but does not establish an
equipment interval for each coordinate epoch. [OSGoF presentation PDF](https://www.arcsstee.org.ng/download/GNSS%202016%20MATERIALS/day4/Surveyor%20Adebomehin.pdf)

Each archive code exactly matches a code in the OSGoF table. This is a code
match, not proof of monument continuity. No alias was applied. The public IGS
station-log directory was checked by exact code; none of these 11 codes
appeared in its listing. That negative result is scoped to the checked IGS
directory and does not establish that no other station logs exist.

| Station | OSGoF XYZ coordinate status | Stated coordinate epoch | IGS log code match | Monument / ARP |
|---|---|---|---|---|
| ABUZ | PROVISIONAL | 2011-01-01 | No | Unknown |
| BKFP | PROVISIONAL | 2011-01-01 | No | Unknown |
| CGGT | PROVISIONAL | 2011-01-01 | No | Unknown |
| CLBR | PROVISIONAL | 2011-01-01 | No | Unknown |
| FUTY | PROVISIONAL | 2011-01-01 | No | Unknown |
| GEMB | PROVISIONAL | 2011-01-01 | No | Unknown |
| MDGR | PROVISIONAL | 2011-01-01 | No | Unknown |
| OSGF | PROVISIONAL | 2011-01-01 | No | Unknown |
| RUST | PROVISIONAL | 2011-01-01 | No | Unknown |
| ULAG | PROVISIONAL | 2011-01-01 | No | Unknown |
| UNEC | PROVISIONAL | 2011-01-01 | No | Unknown |

The OSGoF XYZ values differ from the corresponding 2011 RINEX `APPROX
POSITION XYZ` values by 0.77–5.87 m (mean 3.44 m). These are raw coordinate
value differences only. Because frame, reference point, and coordinate epoch
compatibility are not established for the RINEX approximate values, these
differences are not displacement estimates, transformation residuals, or
evidence that either coordinate set is more accurate.

### Related reference-frame evidence

The OSGoF-authored NGD2012 overview states that NIGNET coordinates were
derived from two years of continuous GPS data and that the NGD2012 coordinate
set is referred to ITRF2008 at epoch 2012-01-01. The overview does not provide
station-level coordinates, reference points, equipment intervals, or
uncertainties. It cannot be used to silently assign ITRF2008/2012.0 to the
separate 2011 OSGoF table. [NGD2012 overview](https://ggim.un.org/ggim_20171012/docs/meetings/2ndHighLevelForum/Session%201/Mr%20Nwilo_The%20Nigerian%20Geocentric%20Datum.pdf)

Dodo et al. (2011) describe a preliminary ITRF2008-linked processing effort
and report approximate location/equipment data for nine stations. The paper
lists Trimble receivers, choke-ring antennas, and 0.171 m antenna heights, but
does not identify receiver/antenna models or station-specific ARP definitions
and uncertainties. Its stated future work includes reprocessing for final
coordinates and determining a Nigerian velocity model and transformation
parameters. It is useful context for nine codes, not a sufficient station
coordinate solution for this audit. [Dodo et al. 2011 paper](https://www.scholarlinkinstitute.org/jeteas/articles/ITRF%202008%20Realization%20of%20the%20Nigerian%20Geocentric%20Datum.pdf)

**Frame and epoch established:** the OSGoF coordinate table’s stated epoch is
2011-01-01; no frame is stated for that table. ITRF2008 at 2012-01-01 is
stated for NGD2012 as a datum-level description, not tied station-by-station
to the table above. No transformation was attempted because station
velocities and a traceable transformation/reference-point chain are
unavailable.

## Navigation source investigation and validation

The IGS product-access guidance documents RINEX 2 daily merged GPS
`brdcDDD0.YYn.Z` and GLONASS `brdcDDD0.YYg.Z` names. It also points to CDDIS,
IGN, GSSC, and SIO archives. CDDIS now requires Earthdata Login for archive
access; no credentials were requested or used. An unauthenticated access
check returned a redirect to Earthdata Login, so no CDDIS product was
downloaded. BKG’s public HTTP archive served the actual 2011 GPS and GLONASS
files directly. The download source was
`https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy}/`.
[IGS products access](https://www.igs.org/products-access/), [IGS archive data
description](https://connect.igs.org/data/), [BKG public archive access](https://igs.bkg.bund.de/access)

The acquisition was restricted to 35 unique dates: the 33 dates from the
previous CLBR+RUST+ULAG+UNEC header-window candidate and 2011-09-09 and
2011-10-14 from the GEMB candidate. No year-wide acquisition was made.

All 70 products passed these checks: downloaded byte count and SHA-256
recorded; Unix-compress decoding succeeded; RINEX version-2 navigation header
and system matched the filename/product; and at least one ephemeris record
was present on the expected date. GPS files include 31–32 distinct PRNs per
product; GLONASS files include 22–24 distinct PRNs per product.
Every satellite ID observed in the candidate station/day files is represented
in the same-date products. Product date/PRN coverage is not itself a guarantee
of a healthy ephemeris at every observation epoch. Health fields were
inspected and retained; nonzero values occur, and no health filtering or
positioning admission was done.

The 2026-11-23 automated rerun independently downloaded and validated 66
products for the 33 primary dates, GPS and GLONASS on every date, all from
BKG. It recorded 31–32 GPS PRNs and 23–24 GLONASS PRNs per product and
satisfied the 52–55 observed-satellite requirements per date. It retained
`ADJACENT_DAY_EPHEMERIDES_PRESENT` for all 33 dates and
`NONZERO_HEALTH_FLAGS_PRESENT` for 48 products; no record was filtered.

The inventory uses `VALIDATED` to mean decompression, header/system, and
expected-date ephemeris checks passed. It does not mean the broadcast message
set has been independently reprocessed or that all records are healthy.

## Automated recovery utility

The reusable workflow is implemented in
`research/southern_network_audit/src/nlgcp_southern_audit/archive_access.py`,
`navigation_recovery.py`, and `recovery_cli.py`, with offline tests in
`research/southern_network_audit/tests/test_navigation_recovery.py`. It
selects targets from audit evidence, generates a deterministic provider
priority list, downloads through an injectable transport with retry/resume and
explicit failure statuses, validates compression and RINEX content, and writes
target/candidate manifests, attempt inventory, per-date coverage, recovery
manifest, Markdown report, and SHA-256 manifest. HTML/login pages, wrong-date
files, corrupt compression, size mismatches, and incomplete satellite coverage
are rejected or recorded as partial; they are never promoted to success.

The recorded 2026-11-23 run was:

```bash
PYTHONPATH=research/southern_network_audit/src .venv/bin/python -m \
  nlgcp_southern_audit.recovery_cli \
  --audit-run /home/excellence/nlgcp-data/validation/southern-nignet/run-20261030T125136Z \
  --constellation-evidence /home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery/run-20261030T132927Z/candidate_observation_constellations.csv \
  --run-id run-20261123T163056Z --workers 8 --execute
```

Its overall result was `VALIDATED` for 33/33 dates and 66/66 products. CDDIS
candidate attempts (132) were recorded as `AUTHENTICATION_REQUIRED`; BKG
supplied every validated product. This is navigation recovery, not positioning
validation or scientific admission.

## Exact observation overlap and constellation evidence

RINEX 2.11 epoch lines were parsed directly from selected ZIP members in
read-only mode. Only observation epoch flags 0 and 1 were counted. The
declared time systems were preserved; all candidate files declare GPS. No
GPS-to-UTC conversion was made.

| Candidate | Header-window dates | Dates with exact common epochs | Exact common epochs | Constellations observed |
|---|---:|---:|---:|---|
| CLBR + RUST + ULAG + UNEC | 33 | 33 | 85,946 | GPS (G), GLONASS (R) |
| GEMB + RUST + ULAG + UNEC | 2 | 2 | 720 | GPS (G), GLONASS (R) |

These are exact timestamp intersections. They do not test usable code/carrier
observations, cycle slips, continuity, geometry per epoch, signal completeness,
or health-screened satellite availability. They therefore do not satisfy the
“scientifically usable simultaneous observations” admission condition.

## Coordinate-gated geometry and candidate admission

The official coordinate values were used only in a provisional exploratory
recalculation. The existing local geometry code converts ECEF to local
coordinates using its configured WGS84 ellipsoid constants; the source
coordinate frame remains unknown, so this operation is not a datum
assignment. Among the five latitude-screened southern stations, the 25
three- and four-reference held-out rows contain 3 `INSIDE` and 22 `OUTSIDE`
cases. The contained cases are CLBR+GEMB+ULAG → UNEC,
GEMB+RUST+ULAG → UNEC, and CLBR+GEMB+RUST+ULAG → UNEC. Results are
exploratory and not an authoritative geometry ranking.

The coordinate gate returns `BLOCKED_COORDINATES_NOT_VERIFIED` for all 11
stations. Candidate admission is therefore **BLOCKED** even where navigation
files and exact timestamp overlaps are present. The record lacks a verified
frame, reference point/ARP linkage, monument continuity, and uncertainty.
No coordinate transformation or positioning experiment was performed.

## Reproducibility, evidence, and next experiment

The modules added to `research/southern_network_audit/` provide fail-closed
coordinate provenance, exact station-code reconciliation, authenticated/bounded
archive access, deterministic navigation recovery and validation,
Unix-compress/gzip corruption handling, exact epoch intersection,
coordinate/reference-point geometry gates, and scientific admission. The
focused tests use only labelled synthetic fixtures. Reproduction requires
Python project dependencies and the system `uncompress` utility for `.Z`
products. Network access is isolated behind an injectable transport, so the
offline tests do not contact any archive.

External evidence is under
`/home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery/run-20261030T132927Z/`:

- `coordinate_source_register.csv`, `coordinate_provenance.csv`,
  `station_identity_reconciliation.csv`, and `coordinate_discrepancy_report.csv`;
- `navigation_acquisition_manifest.json`,
  `navigation_product_inventory.csv`, `navigation_date_coverage.csv`, and
  `navigation_validation_report.md`;
- `exact_observation_epoch_overlap.csv`, `exact_common_epochs.csv`, and
  `candidate_observation_constellations.csv`;
- `candidate_scientific_admission.csv`, `provisional_osgof_network_geometry.csv`,
  `provisional_osgof_held_out_geometry_all.csv`, `provisional_osgof_geometry_rankings.csv`,
  `provisional_osgof_geometry.csv`, `coordinate_gated_geometry_summary.json`,
  downloaded source documents, and `sha256_manifest.txt`.

The automated utility evidence is under
`/home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery/run-20261123T163056Z/`:

- `recovery_targets.json`, `recovery_targets.csv`, `archive_candidates.json`,
  and `archive_candidates.csv`;
- `navigation_product_inventory.csv`, `navigation_recovery_records.csv`,
  `navigation_date_coverage.csv`, and `navigation_recovery_manifest.json`;
- `navigation_recovery_report.md`, `navigation-products/`, and
  `sha256_manifest.txt`.

The recommended next step is to obtain or derive a station-specific coordinate
solution that explicitly binds each physical monument and antenna reference
point to a frame, coordinate epoch, uncertainty, and equipment interval. Any
frame/epoch transformation also needs documented parameters and station
velocities. After those records pass review, use the recovered 2011 navigation
files for observation-level QC and health-aware checks on one candidate day
before proposing a controlled offline positioning experiment.

No RTKLIB experiment, network-RTK run, VRS generation, RTCM generation, or
accuracy claim was made.
