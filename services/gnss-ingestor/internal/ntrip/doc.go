// Package ntrip implements fail-closed live NTRIP/CORS ingestion.
//
// Transport/acquisition only: NTRIP v2 handshakes (tolerant of v1
// casters), streaming RTCM 3.x framing with CRC-24Q integrity, arrival
// timestamps, bounded reconnection, stall detection, immutable capture
// writing, and credential redaction. It never invents RTCM messages,
// station coordinates, mountpoints, credentials, or accuracy claims.
// Without an authorized reachable source, REAL LIVE INGESTION = BLOCKED.
package ntrip
