# 02. System Requirements Specification

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Requirement conventions

Requirements use `DOMAIN-REQ-NNN`. “Shall” means mandatory. A requirement is not complete until it has a verification method: inspection (I), analysis (A), laboratory test (L), replay test (R), or field test (F).

## 2. Functional requirements

### 2.1 CORS and ingestion

- **ING-REQ-001 (L):** The system shall maintain persistent authenticated connections to configured live reference-station streams.
- **ING-REQ-002 (L):** The system shall accept RTCM 3.x observation streams and preserve original byte streams when archiving is enabled.
- **ING-REQ-003 (I/L):** Every received stream shall be associated with a registered station identity and active equipment/coordinate metadata interval.
- **ING-REQ-004 (L):** The ingestor shall timestamp arrival time independently of GNSS observation time.
- **ING-REQ-005 (R):** Connection loss shall produce a station-state transition without blocking unrelated stations.

### 2.2 Offline/replay data

- **DAT-REQ-001 (L):** The system shall ingest RINEX observations and navigation files for reproducible offline processing.
- **DAT-REQ-002 (I):** Raw source files shall be immutable after archival; corrections or reprocessing shall create derived artefacts.
- **DAT-REQ-003 (A):** File metadata shall include checksum, source, station, observation interval, sampling rate, format version and ingestion time.

### 2.3 Epoch alignment and QC

- **QC-REQ-001 (R/L):** Observations from multiple stations shall be aligned by GNSS epoch within a configured tolerance.
- **QC-REQ-002 (L):** The pipeline shall detect missing epochs, stale streams, malformed messages and unsupported message types.
- **QC-REQ-003 (R/F):** GNSS QC shall expose cycle-slip, signal-quality, satellite-availability and residual indicators used by station health.
- **QC-REQ-004 (F):** A station shall not contribute to network corrections when its health state is `UNAVAILABLE`.

### 2.4 GNSS processing

- **RTK-REQ-001 (R/F):** The system shall compute a conventional single-base solution for reference experiments and approved operational service.
- **NRTK-REQ-001 (R/F):** The system shall form and process a local network from eligible healthy stations.
- **NRTK-REQ-002 (R/F):** The network processor shall estimate spatially correlated residual errors and expose them by satellite/signal/epoch as required by the chosen model.
- **AMB-REQ-001 (R/F):** Integer ambiguities shall be estimated and validated before they are used as fixed ambiguities.
- **ATM-REQ-001 (A/R):** Ionospheric and tropospheric effects shall be modelled or estimated consistently with the processing strategy.

### 2.5 VRS and hybrid service

- **VRS-REQ-001 (L/F):** A VRS session shall use the rover's approximate position supplied through the supported client mechanism.
- **VRS-REQ-002 (R/F):** The system shall select the appropriate service cell and eligible reference stations for the rover position.
- **VRS-REQ-003 (R/F):** The engine shall generate virtual observations/corrections consistent with the selected physical network model.
- **HYB-REQ-001 (F):** When VRS integrity is not satisfied, the system may offer an eligible single-base mode if the physical base satisfies the pilot-derived constraints.
- **HYB-REQ-002 (F):** When neither network nor single-base criteria are satisfied, the service shall declare degraded/unavailable precision rather than silently streaming an invalid high-precision product.

### 2.6 Distribution

- **NTRIP-REQ-001 (L/F):** Corrections shall be distributed to standard rover clients using NTRIP.
- **NTRIP-REQ-002 (L):** The platform shall maintain mountpoint metadata, service mode, region, coordinate context and operational state.
- **NTRIP-REQ-003 (L):** Authentication and entitlement shall be checked without exposing internal processing services.
- **NTRIP-REQ-004 (F):** A caster instance failure shall be recoverable through the production HA architecture without scientific reconfiguration of the rover session where feasible.

### 2.7 User/control platform

- **PLAT-REQ-001 (L):** Users shall be able to register authorised GNSS devices and obtain scoped service credentials.
- **PLAT-REQ-002 (L):** Organisations shall manage members, devices and service entitlements according to RBAC.
- **PLAT-REQ-003 (L):** Operators shall view station status, cell status, correction service state and incident history.
- **PLAT-REQ-004 (L):** API and dashboard failure shall not terminate already-authorised correction streams solely because the web control plane is unavailable.

## 3. Non-functional requirements

### Reliability and integrity

- **NFR-INT-001:** Correction integrity has priority over nominal uptime.
- **NFR-HA-001:** Production correction delivery shall have no single application-server dependency.
- **NFR-OBS-001:** Every critical component shall expose health/metrics sufficient for operational diagnosis.

### Performance

A latency budget shall be measured end-to-end: station observation -> ingest -> alignment -> processing -> encode -> caster -> rover. Numeric SLOs are **pilot-derived** and must be validated against ambiguity/fix performance and mobile-network conditions rather than copied from another country.

### Security

- Least privilege and network segmentation are mandatory.
- Database, message broker, cache and processing control ports shall not be Internet-exposed.
- NTRIP and web credentials shall be distinct security domains.
- Administrative configuration changes shall be audited.

### Interoperability

The platform shall use standards-based interfaces where practicable: RINEX for archival observation exchange, RTCM for real-time GNSS streams, NTRIP for streaming transport, and established IGS products/formats for precise-product workflows.

## 4. Verification matrix

| Domain | Minimum verification |
|---|---|
| Ingestion | recorded RTCM replay + forced disconnect/reconnect |
| RINEX | known sample datasets from at least two source networks |
| Single-base | control-point field test at multiple baseline lengths |
| NRTK/VRS | sparse vs densified network replay and field test |
| Integrity | injected stale station, bad metadata, station loss and residual anomalies |
| NTRIP | multi-vendor rover interoperability test |
| HA | process/caster/broker node failure exercise |
| Security | threat-model review + authenticated/unauthorised access tests |

## 5. Acceptance principle

No requirement whose evidence depends on Nigerian operating conditions is accepted by design review alone. It must be closed with Nigerian observation data and/or field measurements.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

