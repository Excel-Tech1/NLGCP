# 11. GNSS Quality Control and Station Health

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Objective

Convert raw stream availability into a scientifically meaningful answer: **may this station contribute to a correction right now?**

## 2. Health dimensions

- stream connectivity;
- observation freshness/data age;
- expected message/epoch rate;
- epoch completeness;
- satellite count and geometry indicators;
- signal C/N0 distribution;
- cycle-slip/event rate;
- receiver resets/time jumps;
- coordinate/equipment metadata validity;
- network residual consistency;
- communication latency/jitter;
- maintenance/administrative state.

## 3. State model

`INITIALISING -> HEALTHY -> DEGRADED -> UNAVAILABLE -> RECOVERING -> HEALTHY`

A station may also be `MAINTENANCE` by explicit operator action. `UNAVAILABLE` and `MAINTENANCE` stations are excluded from correction generation.

## 4. Health score

The MVP may expose a composite score for operator visibility, but service admission shall be driven by explicit gating checks, not by an opaque average. A station with invalid coordinates must be excluded even if all communications metrics are perfect.

## 5. QC events

Each anomaly generates a structured event with station, epoch/window, severity, evidence, affected signals/satellites and automatic action. Examples: `STALE_STREAM`, `EPOCH_GAP`, `CYCLE_SLIP_SPIKE`, `METADATA_INTERVAL_MISSING`, `RESIDUAL_OUTLIER`, `CLOCK_JUMP`.

## 6. Recovery

A station does not instantly become trusted after reconnect. A configurable recovery window verifies stable epochs and residual consistency before it re-enters the network solution.

## 7. Pilot-derived thresholds

Thresholds for C/N0, residual outliers, gap rates, recovery duration and latency are measured using Nigerian stations, receiver types and communications. Values are versioned in processing configuration so thesis experiments remain reproducible.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

