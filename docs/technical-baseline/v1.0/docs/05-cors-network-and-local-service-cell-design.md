# 05. CORS Network and Local Service Cell Design

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Purpose

Define the physical/geometric requirements for local NRTK cells and the process used to densify around NIGNET or partner infrastructure.

## 2. Cell model

A cell is a group of physical reference stations with validated geometry, common processing policy and an explicit service polygon. The polygon is not simply a fixed radius; it is derived from station geometry, atmospheric performance and field validation.

## 3. Minimum topology

Three stations are the geometric minimum for spatial modelling, but production design should prefer redundancy. The pilot target is **at least four stations where practical**, with five or more preferred for operational resilience. Exact deployment depends on available infrastructure and cost.

## 4. Site requirements

A candidate CORS site shall be evaluated for:

- stable monumentation and documented reference mark;
- unobstructed sky view and low multipath environment;
- RF interference risk;
- secure equipment accommodation;
- stable power, UPS and backup power;
- primary and secondary communications where feasible;
- environmental resilience and access control;
- antenna calibration information and repeatable antenna-height reference;
- ability to preserve raw observations locally during network outages.

## 5. Station spacing

No national fixed spacing is hard-coded before research validation. The pilot shall test multiple effective geometries (including deliberately sparse configurations) and derive the relationship between inter-station distance, residual interpolation error, ionospheric activity, ambiguity performance and service reliability.

## 6. Edge and outside-cell behaviour

A rover near or outside the convex hull of the reference stations is higher risk for interpolation. Cell routing shall therefore consider:

- rover inside/outside network hull;
- distance to nearest stations;
- angular distribution/geometry;
- number of healthy stations;
- residual quality and atmospheric gradient indicators.

## 7. Cell overlap

Adjacent production cells may overlap. The national control plane shall choose between them based on integrity and service policy, not merely nearest centroid. Overlap permits maintenance and gradual network expansion.

## 8. Commissioning sequence

1. reconnaissance and interference survey;
2. monument/site construction;
3. receiver/antenna installation;
4. station metadata creation;
5. static observations for precise coordinate determination;
6. PRIDE PPP-AR/other accepted geodetic solution and network check;
7. live RTCM/NTRIP commissioning;
8. multi-day QC baseline;
9. inclusion in offline NRTK replay;
10. controlled field validation;
11. operational admission.

## 9. Proposed pilot design

FCT/Abuja remains an appropriate research candidate, but the final station set shall be chosen only after source audit and field reconnaissance. Existing distant stations can intentionally serve the **sparse network experiment**, while additional local stations form the **densified network experiment**.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

