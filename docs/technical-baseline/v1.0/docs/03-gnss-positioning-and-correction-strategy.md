# 03. GNSS Positioning and Correction Strategy

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Decision

The operational product shall use **localised network RTK/VRS as the preferred correction method**, **single-base RTK as an eligible fallback/alternative**, and **PRIDE PPP-AR as an offline geodetic validation and station-coordinate tool**. PPP-AR is not the primary live correction path for the MVP.

## 2. Rationale

Single-base RTK is simple and highly effective on short baselines, but residual ionospheric, tropospheric and orbit effects decorrelate as baseline length increases. VRS/NRTK uses multiple physical stations to estimate spatially dependent errors and construct a virtual reference close to the rover. The method therefore addresses the specific thesis problem more directly than replacing the research with PPP.

PRIDE PPP-AR is retained because precise independent station coordinates and validation solutions strengthen the scientific quality of the network. RTKLIB is retained because its real-time stream, RTCM/NTRIP and RTK capabilities fit the operational path.

## 3. Processing modes

### Mode A - Single-base RTK

Input: one approved physical base + rover observations.  
Use: baseline benchmarking, local short-baseline service, fallback when the network is degraded but one suitable station remains.  
Constraint: maximum permissible baseline is pilot-derived and may vary by atmospheric conditions and receiver/signal capability.

### Mode B - VRS/NRTK

Input: a valid local network, rover approximate position and network metadata.  
Process: network ambiguity solution, spatial residual estimation, interpolation to the virtual location, RTCM generation.  
Use: primary local/regional service.

### Mode C - Degraded precision

If the network fails integrity and no suitable base exists, high-precision service is suppressed or clearly downgraded. The system shall not preserve a “green” RTK service status simply to maximise availability.

### Offline Mode D - PPP/PPP-AR

Use PRIDE PPP-AR for station coordinate determination, long-session validation, tropospheric analysis and an independent reference against which local RTK experiments can be checked.

## 4. Service-cell philosophy

Nigeria shall not be modelled as one monolithic VRS network. Each regional cell is a bounded network whose geometry and atmospheric representativeness have been validated. NIGNET provides national geodetic traceability where available; local/partner stations provide density.

## 5. Algorithmic boundary

RTKLIB supplies standard GNSS mechanics. The project-specific NRTK engine owns:

- station eligibility and topology;
- epoch synchronisation policy;
- network residual extraction;
- interpolation model selection;
- low-latitude atmospheric adaptation;
- VRS construction;
- hybrid mode decision;
- integrity state and quality indicators.

## 6. Future extensibility

The architecture may later add SSR/PPP-RTK style services, but this shall be a new service product with its own validation. It must not compromise the clarity or reproducibility of the initial RTK/VRS research objective.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

