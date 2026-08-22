# 18. Security and Access Control Architecture

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Security objectives

Protect correction integrity, station/control configuration, credentials, user/device data, precise infrastructure details and the availability of the service.

## 2. Primary threats

- stolen/shared NTRIP credentials;
- unauthorised station stream injection;
- modification of station coordinates/metadata;
- malicious or accidental configuration change;
- denial of service against caster/API;
- compromise of CORS site/router;
- replay/stale stream accepted as live;
- exposed databases/brokers/metrics endpoints;
- supply-chain compromise of GNSS or platform software;
- excessive retention/exposure of user location data.

## 3. Network zones

1. Internet clients.
2. Public edge: load balancers, NTRIP caster frontends, API gateway.
3. Application zone: FastAPI, session/auth services.
4. GNSS processing zone: ingest, NATS, NRTK engine, correction publishers.
5. Data zone: PostgreSQL, object storage, Redis, secrets.
6. Administrative management zone: VPN/SSO-controlled operator access.

## 4. Identity and authorisation

Web identities and NTRIP/device credentials are separate. RBAC/ABAC may be combined: role controls administrative actions; service entitlement controls mountpoints/regions/devices.

## 5. Secrets

No secrets in source control, images, logs or research notebooks. Production uses a managed secret store or Kubernetes/host integration with encryption and rotation. CORS provider credentials are individually scoped.

## 6. Scientific integrity controls

Coordinate and equipment changes require privileged workflow and audit. The processing engine validates active metadata intervals. Correction configuration releases are signed/versioned through CI/CD and cannot be altered through anonymous runtime parameters.

## 7. Logging/privacy

Audit administrative access and correction entitlement events. Avoid storing exact rover tracks unless required for service/research; where collected, apply explicit purpose, access control and retention.

## 8. Security validation

Threat-model review, dependency scanning, container scanning, secret detection, authentication/authorisation tests, network exposure review, backup-restore test and incident exercises are release gates.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

