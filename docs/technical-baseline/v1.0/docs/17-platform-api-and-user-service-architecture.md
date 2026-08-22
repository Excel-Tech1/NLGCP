# 17. Platform API and User Service Architecture

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Control-plane responsibilities

The web/API platform manages customer and operator workflows; it does not calculate per-epoch RTK positions.

## 2. Domains

- identity and authentication;
- organisations and memberships;
- devices/receivers;
- service plans and entitlements;
- NTRIP credential lifecycle;
- coverage/service catalogue;
- correction session summaries;
- network status;
- support/incidents;
- administration and audit;
- billing integration boundary.

## 3. API baseline

FastAPI services use versioned REST endpoints under `/api/v1`. OpenAPI is generated from typed schemas. Example resources:

`/stations`, `/cells`, `/coverage`, `/devices`, `/mountpoints`, `/sessions`, `/network-status`, `/incidents`, `/entitlements`, `/admin/configurations`.

No API endpoint shall accept arbitrary processing code or raw configuration text from untrusted users.

## 4. Frontend

Next.js + TypeScript consumes the API. MapLibre renders service cells/stations with role-appropriate detail. Public users may see coverage and high-level service status; precise infrastructure details may be restricted.

## 5. Roles

- platform super administrator;
- GNSS network operator;
- CORS partner operator;
- support/operations analyst;
- organisation administrator;
- surveyor/end user;
- research/data user (optional separate entitlement).

## 6. Data-plane independence

Existing valid NTRIP sessions use cached/replicated authorisation state with bounded TTL so a transient web API failure does not immediately collapse correction service. Revocation must still propagate within the security-defined maximum window.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

