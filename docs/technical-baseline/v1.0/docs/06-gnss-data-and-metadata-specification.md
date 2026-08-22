# 06. GNSS Data and Metadata Specification

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Canonical observation model

All sources shall map into a source-independent internal model.

```yaml
GNSSObservation:
  station_id: string
  epoch_gnss: timestamp
  arrival_time_utc: timestamp
  constellation: enum[GPS,GLO,GAL,BDS,QZSS,SBAS,NAVIC]
  satellite: string
  signal: string
  pseudorange_m: float?
  carrier_phase_cycles: float?
  doppler_hz: float?
  cn0_dbhz: float?
  lli: integer?
  lock_time_s: float?
  elevation_deg: float?
  azimuth_deg: float?
  source_message_type: string
  quality_flags: [string]
```

## 2. Station metadata

A station record shall include identity, provider, physical location, ECEF/geodetic coordinates, reference frame, coordinate epoch, monument, receiver, antenna, radome, firmware, antenna reference point/height, supported signals, sample rate, communications endpoints and operational contacts.

Equipment and coordinates are **effective-dated**. Historical records are never overwritten.

## 3. Coordinate record

```yaml
StationCoordinate:
  station_id: string
  frame: string
  epoch: decimal_year
  x_m: float
  y_m: float
  z_m: float
  latitude_deg: float
  longitude_deg: float
  ellipsoidal_height_m: float
  solution_method: string
  covariance: optional
  valid_from: timestamp
  valid_to: timestamp?
```

## 4. Supported archival formats

- RINEX 4 is the preferred long-term standard for new platform-controlled archives where equipment/software permit it.
- RINEX 3.x shall remain supported for interoperability with existing CORS and GNSS software.
- SP3, CLK, SINEX/Bias-SINEX, IONEX and relevant IGS products are stored with provenance.
- Raw RTCM stream recordings may be preserved to support exact replay of live sessions.

IGS currently lists RINEX 4.02 as the current RINEX specification and encourages RINEX 4 for station submissions.

## 5. Validation rules

- station ID must exist and be active for the observation interval;
- GNSS time and arrival time must be distinguishable;
- unknown signal/message codes must be retained in raw archives even if the normaliser rejects them;
- coordinate/equipment interval must cover the processed epoch;
- malformed values shall generate data-quality events rather than silent coercion.

## 6. Naming and checksums

Object storage keys shall include provider/station/date/source type. Each immutable object shall store SHA-256, byte size, original filename, acquisition endpoint and ingestion software version.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

