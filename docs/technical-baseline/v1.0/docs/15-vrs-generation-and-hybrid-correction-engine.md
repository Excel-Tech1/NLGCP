# 15. VRS Generation and Hybrid Correction Engine

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. VRS session lifecycle

1. rover authenticates to an authorised VRS service;
2. caster/session layer receives approximate rover position (normally via client GGA flow where supported);
3. service router selects a validated cell;
4. VRS engine chooses the physical station set and current network state;
5. network corrections are interpolated to a virtual location close to the rover;
6. virtual observations/corrections are encoded into the approved RTCM stream;
7. integrity/latency are continuously checked;
8. session ends, reroutes or downgrades when conditions change.

## 2. Virtual station policy

The virtual reference position shall be deterministic for a session/configuration and recorded for replay. Movement thresholds for regenerating/repositioning the VRS are pilot-derived and receiver-compatibility tested.

## 3. Hybrid decision

```text
if network_integrity == ACCEPTABLE:
    mode = VRS
elif eligible_single_base_exists(rover):
    mode = SINGLE_BASE
else:
    mode = DEGRADED_OR_UNAVAILABLE
```

The real implementation includes hysteresis/recovery logic to avoid rapid oscillation between modes.

## 4. Integrity inputs

- number/distribution of healthy stations;
- rover relative to network hull/service polygon;
- residual-model quality;
- ambiguity/network state;
- stream age and processing latency;
- reference-station coordinate validity;
- current operational/maintenance state.

## 5. Session record

Store session ID, organisation/device, mountpoint, approximate rover region (subject to privacy policy), cell, physical stations used over time, model/config version, service-mode transitions, latency summaries and integrity events.

## 6. Fail-closed behaviour

If model quality cannot be established, the engine must not fabricate a VRS stream. The platform may return a defined unavailable/degraded service response or disconnect according to receiver interoperability findings.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

