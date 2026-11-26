# NLGCP Dataset Catalogue

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)
**Machine-Readable Manifests:** [`research/archive/datasets/`](file:///home/excellence/NLGCP/research/archive/datasets/) (`21` registered datasets)
**External Research Data Root:** `/home/excellence/nlgcp-data` (~23 GiB; never duplicated into Git)
**Last Updated:** 2026-11-26

---

## 1. Governance & Immutability Policy

- Original GNSS datasets (`immutable_source = true`) are **never modified, overwritten, or copied into Git** (`ADR-009`).
- Every dataset carries a controlled `source_classification`, explicit `coordinate_reference_status`, `reference_frame`, and SHA-256 digest (`NOT_AVAILABLE` when an external dependency does not exist locally).
- `SYNTHETIC_TEST_DATA` is programmatically blocked from being referenced by any `AUTHENTIC` experiment (`nlgcp_research_archive.validator`).

---

## 2. Registered Datasets (`21` Total)

| Dataset ID | Name | Classification | Immutable | Storage | Size (B) | SHA-256 (prefix) | Coord / Frame Status |
|---|---|---|---|---|---:|---|---|
| `NLGCP-DATA-2011-001` | NIGNET 2011 Archive (`NIGNET2011.zip`, 3,018 RINEX, 11 stations) | `AUTHENTIC_RECORDED_CORS` | Yes | `EXTERNAL` | `5,820,369,120` | `8ccb004540c005a2` | `PROVISIONAL_OSGOF_2011_01_01` / `UNKNOWN_ITRF` |
| `NLGCP-DATA-2011-002` | BKG/IGS 2011 DOY 079 GPS Nav (`brdc0790.11n.Z`, part of 66/66) | `AUTHENTIC_RECORDED_CORS` | Yes | `EXTERNAL` | `56,968` | `52cc6c9b5a1864b1` | `WGS84_BROADCAST` |
| `NLGCP-DATA-2011-003` | OSGoF 2011 Provisional Coordinates (`coordinate_provenance.csv`) | `DERIVED_DATA` | No | `EXTERNAL` | `4,305` | `e48cd164c4524dcd` | `PROVISIONAL_OSGOF_2011_01_01` / `UNKNOWN_ITRF` |
| `NLGCP-DATA-2011-004` | B-02 Extracted `OSGF0790.11O` (2011-03-20 rover) | `DERIVED_DATA` | No | `EXTERNAL` | `6,478,287` | `c9f43c872cd8be76` | `PROVISIONAL_OSGOF_2011_01_01` / `UNKNOWN_ITRF` |
| `NLGCP-DATA-2011-005` | B-02 Extracted `CGGT0790.11O` (2011-03-20 anchor, 216.3 km) | `DERIVED_DATA` | No | `EXTERNAL` | `6,418,001` | `95f3bad2e2eb116b` | `PROVISIONAL_OSGOF_2011_01_01` / `UNKNOWN_ITRF` |
| `NLGCP-DATA-2011-006` | 2011 IGS/MGEX Precise `SP3`/`CLK`/`ERP`/`OSB` | `AUTHENTIC_RECORDED_CORS` | Yes | **`UNAVAILABLE`** | `NOT_AVAILABLE` | `NOT_AVAILABLE` | `NOT_AVAILABLE` (blocks B-01 offline PPP) |
| `NLGCP-DATA-2024-001` | Canonical 2024 NIGNET Raw Manifest (`1,290` station-days, 8 stations) | `AUTHENTIC_RECORDED_CORS` | Yes | `EXTERNAL` | `537,609` | `4f97149bcbf1349e` | `PARTIALLY_VERIFIED_DOY_026_ONLY` / `IGS20` |
| `NLGCP-DATA-2024-002` | BKG/IGS 2024 DOY 026 BRDC (`BRDC00IGS_R_20240260000_01D_MN.rnx.gz`) | `AUTHENTIC_RECORDED_CORS` | Yes | `EXTERNAL` | `1,306,845` | `a64183872be90e60` | `WGS84_BROADCAST` |
| `NLGCP-DATA-2024-003` | Verified IGS20 2024 DOY 026 Coords (`derived-coordinates.json`) | `DERIVED_DATA` | No | `EXTERNAL` | `3,665` | `f48411df72fc7871` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-004` | QC-Converted `PHRI0260.24O` (2024-01-26 rover) | `DERIVED_DATA` | No | `EXTERNAL` | `4,796,500` | `a2bae005e8973aed` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-005` | QC-Converted `EKAK0260.24O` (2024-01-26 anchor, 105.6 km) | `DERIVED_DATA` | No | `EXTERNAL` | `10,946,890` | `57e1917af8ad7842` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-006` | QC-Converted `ABFC0260.24O` (2024-01-26 ref, 470.9 km) | `DERIVED_DATA` | No | `EXTERNAL` | `12,743,833` | `953df3cdbab882c7` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-007` | QC-Converted `MGBO0260.24O` (2024-01-26 ref, 1,029 km) | `DERIVED_DATA` | No | `EXTERNAL` | `11,821,585` | `be679f146a5664f7` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-008` | PRIDE PPP-AR 3.2.8 PHRI Truth (`pos_2024026_phri`, 45 fixed amb) | `DERIVED_DATA` | No | `EXTERNAL` | `5,257` | `7f62d2466fe9cf2d` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-009` | WUM Rapid Precise Orbit (`WUM0MGXRAP_20240260000_01D_05M_ORB.SP3`) | `AUTHENTIC_RECORDED_CORS` | Yes | `EXTERNAL` | `1,932,216` | `33c5ce3e4a98cb31` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-010` | PRIDE PPP-AR ZTD (`ztd_2024026_ekak` + ABFC/MGBO set) | `DERIVED_DATA` | No | `EXTERNAL` | `217,498` | `2d10325ad2ac6239` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2024-011` | External 2024 IGS DCB / IONEX (`external-products/igs/2024/` empty) | `AUTHENTIC_RECORDED_CORS` | Yes | **`UNAVAILABLE`** | `NOT_AVAILABLE` | `NOT_AVAILABLE` | `NOT_AVAILABLE` |
| `NLGCP-DATA-2026-001` | Phase 7 Experimental VRS Stream (`vrs_2024_01_26_phri_exp.rtcm3`) | `DERIVED_DATA` | No | `EXTERNAL` | `3,914` | `d9eb20c31b3e740c` | `VERIFIED_IGS20_PPP_AR` / `IGS20` |
| `NLGCP-DATA-2026-002` | Phase 7 Experimental VRS Stream (`vrs_2011_03_20_osgf_exp.rtcm3`) | `DERIVED_DATA` | No | `EXTERNAL` | `4,045` | `e4f492655df99670` | `PROVISIONAL_OSGOF_2011_01_01` / `UNKNOWN_ITRF` |
| `NLGCP-DATA-2026-003` | **SYNTHETIC TEST DATA** — RTCM Replay Fixture (`valid.rtcm3`) | `SYNTHETIC_TEST_DATA` | No | `EXTERNAL` | `115` | `0402b7e8a364e9e0` | `SYNTHETIC_TEST_ONLY` |
| `NLGCP-DATA-2026-004` | Authorized Live Nigerian CORS / NTRIP Stream | `AUTHENTIC_LIVE_CORS` | Yes | **`UNAVAILABLE`** | `NOT_AVAILABLE` | `NOT_AVAILABLE` | `NOT_AVAILABLE` (blocks Phase 9/10 live ops) |

---

## 3. Verification Command

```bash
.venv/bin/nlgcp archive datasets list
.venv/bin/nlgcp archive datasets verify
```
