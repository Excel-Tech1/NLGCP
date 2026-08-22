# 22. Deployment, Operations and Runbooks

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Deployment pipeline

Source -> review -> automated tests -> algorithm replay regression -> container build -> vulnerability scan -> staging -> controlled field/stream verification -> production canary/region deployment -> monitoring -> rollback if required.

## 2. Configuration

Processing configuration is version-controlled. Environment-specific secrets/endpoints are externalised. Scientific parameters never live only in a dashboard field; the effective configuration for every session must be reconstructable.

## 3. Required runbooks

Separate concise runbooks are included in `/runbooks` for:

- station offline;
- high correction latency;
- residual/integrity alarm;
- caster outage;
- database degradation;
- NATS/broker degradation;
- planned station equipment change;
- correction rollback.

## 4. CORS maintenance change

Before replacing receiver/antenna/firmware:

1. create maintenance window;
2. remove station from eligible network processing;
3. preserve pre-change metadata end time;
4. record new serial/model/firmware/antenna height;
5. collect post-change observations;
6. determine/check coordinates if required;
7. pass QC/recovery interval;
8. re-admit.

## 5. Incident severity

- **SEV-1:** widespread incorrect/high-risk corrections or multi-region outage.
- **SEV-2:** one operational cell unavailable or scientifically degraded.
- **SEV-3:** partial station/provider degradation with redundancy preserved.
- **SEV-4:** non-user-impacting defect/maintenance issue.

Correction-integrity incidents may be SEV-1 even if servers are technically “up”.

## 6. Rollback

Any scientific algorithm/config release must have a tested previous version and an explicit schema compatibility plan. Rollback is preferred to live manual parameter editing during an integrity incident.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

