# 04. NIGNET and Data Source Assessment

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Objective

Define how national, partner, scientific and platform-owned GNSS stations are evaluated before they are admitted into an operational correction cell.

## 2. Source classes

1. **NIGNET** - strategic national geodetic anchor and potential real-time/archival source.
2. **Partner/private Nigerian CORS** - potential densification and archive sources, subject to technical and legal agreements.
3. **IGS/AFREF scientific stations/products** - external frame/precise-product/reference support.
4. **Platform-owned research/permanent CORS** - controlled densification where existing geometry is inadequate.
5. **Temporary campaign stations** - research-only or pre-deployment assessment.

## 3. Admission criteria

Every candidate source is assessed against:

| Area | Questions |
|---|---|
| Geodetic | Are coordinates traceable, current and epoch-defined? |
| Equipment | Receiver/antenna model, calibration, firmware, antenna-height history? |
| Signals | Which constellations, frequencies and RTCM MSM messages are available? |
| Sampling | Is the rate suitable for the intended RTK experiment/service? |
| Availability | Live uptime, archive completeness, planned maintenance? |
| Communications | latency, jitter, loss, backup path? |
| Metadata | machine-readable station log and equipment intervals? |
| Rights | permission to ingest, archive, redistribute and/or derive corrections? |
| Security | authenticated stream, credential management, operational contact? |

## 4. NIGNET position in the architecture

NIGNET is not treated as “just another private stream”. It is the preferred national reference tie where its stations, coordinates and access are suitable. However, the processing software is source-independent so that local density is not constrained by the physical NIGNET layout.

## 5. Suitability statuses

- **A - Operational NRTK eligible:** live, low-latency, correct metadata, validated coordinates/signals.
- **B - Single-base/research eligible:** useful but does not satisfy one or more NRTK cell criteria.
- **C - Archive/validation only:** historical RINEX or scientific reference, no live operational stream.
- **D - Rejected pending remediation:** metadata, reliability, rights or data-quality issue.

## 6. Data-source audit register

The project shall maintain `station_source_audit.csv` with fields:

`station_id, provider, coordinates_source, reference_frame, epoch, receiver, antenna, constellations, sampling_rate, live_protocol, archive_format, archive_start, uptime_window, latency_p50, latency_p95, data_gaps, redistribution_rights, suitability_class, last_verified`.

## 7. Current-state caveat

Portal availability and operational station count change over time. Documentation shall date every operational assertion and distinguish **installed**, **configured**, **visible**, and **scientifically usable** stations.

## 8. Exit criterion

A service cell cannot be commissioned until every contributing reference station has completed the source audit and is linked to a valid metadata/equipment interval.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

