# 16. RTCM and NTRIP Correction Distribution

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Purpose

Expose the scientific correction engine to commercial/standard GNSS rovers without requiring custom client software.

## 2. Protocol boundary

- **RTCM 3.x/MSM** is the real-time GNSS observation/correction encoding family used at the platform boundary where supported.
- **NTRIP** provides transport between sources/casters/clients.
- **NMEA GGA** or the chosen supported rover-position mechanism provides approximate location for VRS sessions.

The exact RTCM message profile is a product compatibility decision and shall be captured in a message matrix by receiver vendor/model.

## 3. Mountpoint catalogue

Example logical names:

- `NG-FCT-VRS`
- `NG-FCT-BASE-<station>`
- `NG-JOS-VRS`
- `NG-LAG-VRS`

Production names shall be stable, documented and not expose internal hostnames.

## 4. Caster architecture

The public caster tier is horizontally redundant. Correction publishers authenticate to caster backends; rover users authenticate through scoped credentials/entitlements. Internal GNSS processors are not directly Internet reachable.

## 5. User session controls

- account/device entitlement;
- connection/session limits;
- mountpoint permissions;
- abuse/rate controls;
- credential revocation;
- audit events.

## 6. Interoperability testing

The test matrix shall cover representative Leica, Trimble, Topcon, Emlid, CHCNAV, South, Hi-Target and software NTRIP clients where access is available. Brand support is claimed only after verified testing.

## 7. Service status

The source table/mountpoint state must reflect scientific availability. A mountpoint should not advertise a healthy high-precision service when its correction engine is degraded.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

