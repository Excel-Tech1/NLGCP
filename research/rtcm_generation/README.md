# Phase 11 RTCM Generation Research Package

This is a Python reference boundary for future correction generation. It is
not an operational correction engine. It provides deterministic bit-level
encoders for:

- RTCM 1005 reference-station ARP metadata;
- RTCM 1074 GPS MSM4;
- RTCM 1084 GLONASS MSM4;
- the NLGCP lab-only `SYNTHETIC_TEST_FRAME` message 4095.

The 1005/1074/1084 layouts are derived from the pinned RTKLIB v2.4.2-p13
source. They are validated only against synthetic fixtures and independent
hardcoded payload/frame vectors. No proprietary RTCM standard text is copied.

`SYNTHETICALLY_VALIDATED` is a test status, not scientific or operational
validation. No independent decoder, authentic station observation, verified
coordinate, receiver compatibility test, or positioning evidence has been
admitted. The 1084 encoder does not transport GLONASS frequency-channel
numbers. `OPERATIONAL_APPROVED` output remains forbidden.

All fixtures are labelled:

```text
SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS
```

Run focused tests with the repository environment:

```bash
.venv/bin/python -m pytest research/rtcm_generation/tests -q
```
