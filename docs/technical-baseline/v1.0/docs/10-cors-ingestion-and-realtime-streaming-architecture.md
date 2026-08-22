# 10. CORS Ingestion and Real-Time Streaming Architecture

**Project:** Nigeria Localised GNSS Correction Platform (NLGCP)  
**Document status:** BASELINE v1.0  
**Baseline date:** 2026-08-21  
**Owner:** GNSS Systems Engineering / Research Team  
**Change control:** Material changes require an Architecture Decision Record (ADR) and validation impact review.

> **Design rule:** Parameters that depend on Nigerian field measurements are deliberately marked **Pilot-derived**. This is not missing design; it prevents the architecture from hard-coding unvalidated thresholds.

## 1. Responsibilities

The ingestion tier connects to upstream reference streams, authenticates, timestamps, records connection state, preserves raw messages where configured and publishes station-scoped events. It does not perform geodetic solving.

## 2. Go ingestor process

For each endpoint:

1. resolve configured station and credential reference;
2. open authenticated NTRIP/TCP connection;
3. record connection-start event;
4. receive RTCM bytes continuously;
5. parse enough framing to identify message boundaries/types while retaining original payload;
6. add `arrival_time`, `station_id`, `endpoint_id`, `sequence` and stream diagnostics;
7. publish to NATS;
8. independently enqueue archival chunks;
9. update health heartbeat;
10. reconnect with bounded exponential backoff after failure.

## 3. NATS subject convention

```text
gnss.obs.<region>.<station>
gnss.raw.<region>.<station>
gnss.health.<region>.<station>
gnss.event.<region>.<station>
network.residual.<region>
network.integrity.<region>
correction.vrs.<region>.<session>
correction.base.<region>.<station>
```

## 4. Backpressure

Real-time correctness must not depend on unbounded queues. If consumers fall behind, the system shall measure lag, shed non-critical analytics if necessary, preserve raw data through archive paths, and mark correction service degraded if processing latency threatens scientific validity.

## 5. Ordering and time

GNSS observation time, sender time and platform arrival time are distinct. Cross-station epoch alignment is performed downstream using GNSS epoch, not simply network arrival order.

## 6. Stream security

Upstream credentials are stored in a secrets system or protected environment, never source control. Each endpoint has the minimum rights necessary. Internal NATS requires authenticated private-network access and subject permissions by service role.

## 7. Replay

Recorded RTCM can be republished to a replay namespace with controlled timing. Production and replay subjects must never collide.

## 8. Acceptance tests

- concurrent station streams;
- forced socket resets;
- malformed RTCM fragments;
- delayed station;
- clock/epoch discontinuity;
- broker restart;
- archive storage unavailable;
- reconnect storms.
## Standards and authoritative references

- International GNSS Service (IGS), *Formats and Standards*: https://igs.org/formats-and-standards/ (RINEX 4.02, SINEX, SP3, IONEX, Bias-SINEX and related formats).
- IGS, *Real-Time Service Formats*: https://igs.org/rts/formats/ (IGS SSR and real-time correction context).
- RTKLIB official repository: https://github.com/tomojitakasu/RTKLIB
- PRIDE PPP-AR official repository: https://github.com/PrideLab/PRIDE-PPPAR
- BKG Ntrip information and caster resources: https://igs.bkg.bund.de/ntrip/

