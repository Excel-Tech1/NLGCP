# Future capture template (Phase 10 preparation — do NOT ingest live data in Phase 9)

A later authorised recording MUST be stored with all of the following
before Phase 9 admission will ACCEPT it as RECORDED_RTCM/NTRIP_CAPTURE:

```text
URL/mountpoint
capture start/end (UTC, ISO-8601)
SHA-256 of the byte-exact capture file
byte count
per-frame arrival timestamps (capture index sidecar)
source identity (caster, mountpoint, station)
station_id from the NLGCP registry
rtcm_version observed
capture operator + tool versions
```

Template fields (all required for non-synthetic admission):

```json
{
  "source_id": "<unique id>",
  "source_type": "NTRIP_CAPTURE",
  "source_path": "<immutable path outside Git>",
  "station_id": "<registry id, e.g. EKAK00NGA>",
  "mountpoint": "<caster mountpoint>",
  "start_time": "<ISO-8601 UTC>",
  "end_time": "<ISO-8601 UTC>",
  "byte_size": 0,
  "sha256": "<hex>",
  "capture_method": "<tool + version + command>",
  "capture_provenance": "<who/when/where authorised>",
  "rtcm_version": "3.x",
  "message_types": [],
  "timestamp_source": "capture",
  "verified": false
}
```

No live ingestion, NTRIP connection, or continuous capture loop is
authorised in Phase 9. This template only standardises the future
handoff so Phase 10 can reuse the admission path unchanged.
