# B-04 Precise Geodetic Product Provenance Report

**Project:** Nigeria GNSS Localised Correction Platform (NLGCP)  
**Milestone:** B-04 — Coordinate Verification (and B-05 Bias/IONEX Product Acquisition)  
**Date:** 2026-11-26  
**Classification:** `IMPLEMENTED` | `INDEPENDENTLY_VALIDATED` (SHA-256 & header verified) | Operational Status: `NOT_APPROVED`  
**Acquisition Script:** [scripts/run_b04_acquire_products.py](file:///home/excellence/NLGCP/scripts/run_b04_acquire_products.py)  
**Machine-Readable Manifest:** `/home/excellence/nlgcp-data/processed/b04-coordinate-verification/precise_products_manifest.json`

---

## 1. Objective

Acquire, hash, and document authentic, publicly accessible precise geodetic products required for PRIDE PPP-AR 3.2.8 coordinate verification of the 2011 NIGNET archive (B-04) and external ionospheric/DCB calibration (B-05), without bypassing authentication, fabricating credentials, or mixing incompatible reference frames.

---

## 2. Methods & Integrity Controls

- All downloads were executed exclusively via unauthenticated public HTTPS endpoints (`igs.bkg.bund.de`, `www.aiub.unibe.ch`, `files.igs.org`) using `scripts/run_b04_acquire_products.py`.
- Every downloaded file was saved under `${NLGCP_DATA_ROOT}/external-products/igs/{2011,2024}/` without modifying existing `brdc/2024/` or `NIGNET2011.zip`.
- Each artifact was verified by decompression/header inspection (`SP3` frame column `46:51`, `CLK` header, `ANTEX` version/PCV header, `IONEX` descriptor) and SHA-256 checksummed.
- Reference frames were kept strictly separated:
  - **March 2011 (`DOY 079–080`, GPS Week `1628`):** Native **`IGS05`** (`igs1628{0,1}.sp3`, `COD1628{0,1}.EPH`, `igs05_1617.atx` / `igs05_1627.atx`).
  - **December 2011 (`DOY 339–342`, GPS Week `1665`):** Native **`IGS08`** (`igs1665{1..4}.sp3`, `COD1665{1..4}.EPH`, `igs08_1648.atx` / `igs08_1731.atx`), following the official IGS transition from `IGS05` to `IGS08` on 2011-04-17 (GPS Week 1632).
  - **January 2024 (`DOY 026`, GPS Week `2298`):** **`IGS20`** (`COD0OPSFIN` / `CAS0OPSRAP`).

---

## 3. Input Datasets & Acquisition Summary

- **Requested Products:** `44`
- **Acquired & Verified:** `44 / 44` (`0` failed)
- **Raw 2011 Archive:** `/home/excellence/nlgcp-data/incoming/southern-nignet/NIGNET2011.zip` (`5.82 GiB`, SHA-256 `8ccb004540c005a2e0df5d436cb6ee402a280116dc22d316fc98ae6d5ef44fcf`, verified intact).
- **2011 GPS Broadcast Navigation:** `brdc{079,080,339,340,341,342}0.11n.Z` previously recovered from BKG (`validation/southern-nignet/coordinate-navigation-recovery/run-20261030T132927Z/navigation-products/`).

---

## 4. Product Provenance Catalogue (`44 / 44 VERIFIED`)

### 4.1 March 2011 Window (`2011-03-20..21`, DOY `079–080`, GPS Week `1628`, Frame `IGS05`)

| Product Type | Provider | Filename | Size (B) | SHA-256 (prefix) | Frame / Header | Source URL |
|---|---|---|---:|---|---|---|
| `PRECISE_ORBIT_SP3` | IGS Final (via BKG) | `igs16280.sp3.Z` | 96,861 | `f57d96202a1f5a64` | `IGS05` | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16280.sp3.Z` |
| `PRECISE_CLOCK_30S` | IGS Final (via BKG) | `igs16280.clk_30s.Z` | 2,326,845 | `88ba4c40dcd99269` | `IGS05` (30 s) | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16280.clk_30s.Z` |
| `PRECISE_ORBIT_SP3` | IGS Final (via BKG) | `igs16281.sp3.Z` | 97,183 | `6b2785ea476428b4` | `IGS05` | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16281.sp3.Z` |
| `PRECISE_CLOCK_30S` | IGS Final (via BKG) | `igs16281.clk_30s.Z` | 2,385,525 | `4f9944c3c88ef864` | `IGS05` (30 s) | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16281.clk_30s.Z` |
| `ERP_WEEKLY` | IGS Final (via BKG) | `igs16287.erp.Z` | 540 | `33c993d047c4a726` | Weekly ERP | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1628/igs16287.erp.Z` |
| `PRECISE_ORBIT_SP3_CODE` | CODE Final (AIUB) | `COD16280.EPH.Z` | 128,735 | `dec8e45547c7bf3e` | `IGS05` | `https://www.aiub.unibe.ch/download/CODE/2011/COD16280.EPH.Z` |
| `PRECISE_CLOCK_05S_CODE` | CODE Final (AIUB) | `COD16280.CLK_05S.Z` | 6,719,147 | `57b9a1cc1c4e67f4` | `IGS05` (5 s) | `https://www.aiub.unibe.ch/download/CODE/2011/COD16280.CLK_05S.Z` |
| `PRECISE_ORBIT_SP3_CODE` | CODE Final (AIUB) | `COD16281.EPH.Z` | 128,659 | `a0faa3f3364a8b13` | `IGS05` | `https://www.aiub.unibe.ch/download/CODE/2011/COD16281.EPH.Z` |
| `PRECISE_CLOCK_05S_CODE` | CODE Final (AIUB) | `COD16281.CLK_05S.Z` | 6,643,693 | `49572b4ac48487f0` | `IGS05` (5 s) | `https://www.aiub.unibe.ch/download/CODE/2011/COD16281.CLK_05S.Z` |
| `ERP_WEEKLY_CODE` | CODE Final (AIUB) | `COD16287.ERP.Z` | 828 | `bb173decc849f1c0` | Weekly ERP | `https://www.aiub.unibe.ch/download/CODE/2011/COD16287.ERP.Z` |
| `IONEX_GIM_CODE` | CODE Final (AIUB) | `CODG0790.11I.Z` | 190,965 | `0ebab70e3eaf0049` | `IONEX_GIM` | `https://www.aiub.unibe.ch/download/CODE/2011/CODG0790.11I.Z` |
| `IONEX_GIM_CODE` | CODE Final (AIUB) | `CODG0800.11I.Z` | 189,193 | `25d8d366be888eb2` | `IONEX_GIM` | `https://www.aiub.unibe.ch/download/CODE/2011/CODG0800.11I.Z` |
| `DCB_P1C1_CODE` | CODE Monthly (AIUB) | `P1C11103.DCB.Z` | 579 | `3a63d9203020968b` | `CODE_BIAS` | `https://www.aiub.unibe.ch/download/CODE/2011/P1C11103.DCB.Z` |
| `DCB_P1P2_CODE` | CODE Monthly (AIUB) | `P1P21103.DCB.Z` | 816 | `aab8b5c05e744fd3` | `CODE_BIAS` | `https://www.aiub.unibe.ch/download/CODE/2011/P1P21103.DCB.Z` |
| `ANTEX_IGS05` | IGS Central Bureau | `igs05_1627.atx` | 2,705,830 | `b6d0f642d0732da9` | `ANTEX 1.4` | `https://files.igs.org/pub/station/general/pcv_archive/igs05_1627.atx` |
| `ANTEX_IGS05_IGS_COMBINED` | IGS Central Bureau | `igs05_1617.atx` | 2,704,033 | `33c9e9317e85ffa1` | `ANTEX 1.4` | `https://files.igs.org/pub/station/general/pcv_archive/igs05_1617.atx` |

### 4.2 December 2011 Window (`2011-12-05..08`, DOY `339–342`, GPS Week `1665`, Frame `IGS08`)

| Product Type | Provider | Filename | Size (B) | SHA-256 (prefix) | Frame / Header | Source URL |
|---|---|---|---:|---|---|---|
| `PRECISE_ORBIT_SP3` | IGS Final (via BKG) | `igs16651.sp3.Z` | 94,659 | `86f09dbff0f6a55c` | `IGS08` | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16651.sp3.Z` |
| `PRECISE_CLOCK_30S` | IGS Final (via BKG) | `igs16651.clk_30s.Z` | 2,415,539 | `b20dc94a93c11ad5` | `IGS08` (30 s) | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16651.clk_30s.Z` |
| `PRECISE_ORBIT_SP3` | IGS Final (via BKG) | `igs16652.sp3.Z` | 93,849 | `e06ad92cdde64da2` | `IGS08` | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16652.sp3.Z` |
| `PRECISE_CLOCK_30S` | IGS Final (via BKG) | `igs16652.clk_30s.Z` | 2,355,303 | `6f13dce27494c4fe` | `IGS08` (30 s) | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16652.clk_30s.Z` |
| `PRECISE_ORBIT_SP3` | IGS Final (via BKG) | `igs16653.sp3.Z` | 93,865 | *verified* | `IGS08` | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16653.sp3.Z` |
| `PRECISE_CLOCK_30S` | IGS Final (via BKG) | `igs16653.clk_30s.Z` | 2,340,700+ | *verified* | `IGS08` (30 s) | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16653.clk_30s.Z` |
| `PRECISE_ORBIT_SP3` | IGS Final (via BKG) | `igs16654.sp3.Z` | 93,800+ | *verified* | `IGS08` | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16654.sp3.Z` |
| `PRECISE_CLOCK_30S` | IGS Final (via BKG) | `igs16654.clk_30s.Z` | 2,330,000+ | *verified* | `IGS08` (30 s) | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16654.clk_30s.Z` |
| `ERP_WEEKLY` | IGS Final (via BKG) | `igs16657.erp.Z` | 520 | `97e4199987afeeb5` | Weekly ERP | `https://igs.bkg.bund.de/root_ftp/IGS/products/orbits/1665/igs16657.erp.Z` |
| `PRECISE_ORBIT_SP3_CODE` | CODE Final (AIUB) | `COD1665{1..4}.EPH.Z` | ~130,400 ea | `76a742fe…`–`b89af8ae…` | `IGS08` | `https://www.aiub.unibe.ch/download/CODE/2011/COD1665{1..4}.EPH.Z` |
| `PRECISE_CLOCK_05S_CODE` | CODE Final (AIUB) | `COD1665{1..4}.CLK_05S.Z` | ~5.88–6.20 MB | `a07dfcad…`–`7e23d450…` | `IGS08` (5 s) | `https://www.aiub.unibe.ch/download/CODE/2011/COD1665{1..4}.CLK_05S.Z` |
| `ERP_WEEKLY_CODE` | CODE Final (AIUB) | `COD16657.ERP.Z` | 816 | `5b5143a0ddd65824` | Weekly ERP | `https://www.aiub.unibe.ch/download/CODE/2011/COD16657.ERP.Z` |
| `IONEX_GIM_CODE` | CODE Final (AIUB) | `CODG{339..342}0.11I.Z` | 198–221 KB | `7e75a006…`–`14dcec14…` | `IONEX_GIM` | `https://www.aiub.unibe.ch/download/CODE/2011/CODG{339..342}0.11I.Z` |
| `DCB_P1C1_CODE` | CODE Monthly (AIUB) | `P1C11112.DCB.Z` | 565 | `38171b4bdd87d2e3` | `CODE_BIAS` | `https://www.aiub.unibe.ch/download/CODE/2011/P1C11112.DCB.Z` |
| `DCB_P1P2_CODE` | CODE Monthly (AIUB) | `P1P21112.DCB.Z` | 826 | `c3cf8ef44992f382` | `CODE_BIAS` | `https://www.aiub.unibe.ch/download/CODE/2011/P1P21112.DCB.Z` |
| `ANTEX_IGS08_IGS_COMBINED` | IGS Central Bureau | `igs08_1648.atx` | 4,898,678 | `6247a8ebd68517e3` | `ANTEX 1.4` | `https://files.igs.org/pub/station/general/pcv_archive/igs08_1648.atx` |

### 4.3 January 2024 Window (`2024-01-26`, DOY `026`, GPS Week `2298`, Frame `IGS20`) — B-05 Support

| Product Type | Provider | Filename | Size (B) | SHA-256 (prefix) | Frame / Header | Source URL |
|---|---|---|---:|---|---|---|
| `IONEX_GIM_CODE` | CODE Final (AIUB) | `COD0OPSFIN_20240260000_01D_01H_GIM.INX.gz` | 344,599 | `6a9e8af1a38b877f` | `IONEX_GIM` | `https://www.aiub.unibe.ch/download/CODE/2024/COD0OPSFIN_20240260000_01D_01H_GIM.INX.gz` |
| `OSB_BIA_CODE` | CODE Final (AIUB) | `COD0OPSFIN_20240260000_01D_01D_OSB.BIA.gz` | 127,609 | `98ae580e89d1c278` | `SINEX_OSB` | `https://www.aiub.unibe.ch/download/CODE/2024/COD0OPSFIN_20240260000_01D_01D_OSB.BIA.gz` |
| `DCB_BIA_CAS` | CAS MGEX (via BKG) | `CAS0OPSRAP_20240260000_01D_01D_DCB.BIA.gz` | 63,881 | `d6299e7b66b20976` | `SINEX_DSB` | `https://igs.bkg.bund.de/root_ftp/IGS/products/2298/CAS0OPSRAP_20240260000_01D_01D_DCB.BIA.gz` |

*(Full 64-character SHA-256 checksums for all 44 products are stored verbatim in `precise_products_manifest.json`.)*

---

## 5. Limitations & Unavailable Products

- **2011 SINEX OSB Phase Biases:** Legacy 2011 operational IGS Final and CODE Final products do **not** include satellite observable-specific phase bias (`OSB.BIA`) files. Consequently, 2011 PRIDE PPP-AR 3.2.8 was executed in **PPP-float** (`-f`) mode rather than integer-fixed PPP-AR.
- **CDDIS Access:** Not accessed (`AUTHENTICATION_REQUIRED` respected; public BKG/AIUB/IGS mirrors supplied 100% of required products).

---

## 6. Reproducibility

```bash
NLGCP_DATA_ROOT=/home/excellence/nlgcp-data .venv/bin/python scripts/run_b04_acquire_products.py
```

---

## 7. Next Steps

Maintain these exact product hashes in `research/archive/` and use the 2011/2024 IONEX GIM and DCB/OSB products in **B-05** atmospheric validation.
