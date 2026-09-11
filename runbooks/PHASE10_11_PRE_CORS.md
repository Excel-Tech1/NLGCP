# Pre-CORS Phase 10/11 Runbook

All commands are bounded and use environment-only credentials. Never put a
password on a command line or in a pasted log.

```bash
export NLGCP_DATA_ROOT=/home/excellence/nlgcp-data
cd /home/excellence/NLGCP-pre-cors
```

## Configure and inspect

Set `NLGCP_NTRIP_HOST`, `NLGCP_NTRIP_PORT`, `NLGCP_NTRIP_MOUNTPOINT`, TLS,
and, only when authorized, `NLGCP_NTRIP_USERNAME` and
`NLGCP_NTRIP_PASSWORD` in the environment. Use the dry run before any dial:

```bash
python scripts/run_ntrip_ingest.py probe --dry-run
python scripts/run_ntrip_ingest.py sourcetable --dry-run
```

`/health`/`/live` mean process liveness. `/ready` means service/configuration
readiness, not correction validity. `/status` reports stream state and reason
codes.

## Source table, probe, and bounded capture

```bash
python scripts/run_ntrip_ingest.py sourcetable
python scripts/run_ntrip_ingest.py probe --duration 5 --max-bytes 65536
python scripts/run_ntrip_ingest.py capture --capture-id AUTHORIZED-ID \
  --output-root "$NLGCP_DATA_ROOT/raw/rtcm-captures" --duration 60
python scripts/run_ntrip_ingest.py validate-capture --capture-dir PATH
python scripts/run_ntrip_ingest.py summarize --capture-dir PATH
```

A `PARTIAL` capture is evidence, not a failed observation. Preserve the
directory, recover an interrupted manifest with
`nlgcp_ntrip_ingest.capture.recover_incomplete_capture`, then use Phase 9
admission and validation. Do not delete or edit `stream.rtcm3`.

## Diagnosing failures

- `AUTH_REQUIRED`, `401`, or `403`: stop and verify authorization; do not
  retry indefinitely or guess credentials.
- `404`/invalid mountpoint: verify the source table and explicit station
  mapping.
- `CRC_FAIL`: frames are quarantined and counted; preserve the capture for
  audit and do not forward failed frames.
- `STALLED`/timeouts: inspect last-byte age, reconnect count and buffer waits;
  bounded reconnects eventually produce `PARTIAL` or `FAILED`.
- Disk limit: stop capture, preserve evidence, free or provision approved
  storage, and start a new capture ID. Raw evidence is never silently
  rotated away or deleted.
- NATS unavailable: the capture path remains independently auditable; the
  optional publisher reports failure/overflow and must not be treated as a
  scientific failure or silently substituted.

## CORS-unblock handoff

After authentic capture, follow the sequence in
`docs/phase11-correction-generation-scaffold.md`. Do not enable a VRS output
or call a frame operationally approved until the scientific review and
positioning validation gates pass.
