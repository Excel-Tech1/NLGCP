# Phase 11 RTCM Generation Scaffold

This is a Python reference boundary for future correction generation. It is
not an operational correction engine. The only encoder in this package is a
deterministic `SYNTHETIC_TEST_FRAME` payload used to prove the request →
encoder → Phase 9 framing → local-consumer interfaces.

The registry entries for reference-station metadata and MSM observation
families are scaffolds only. They do not copy proprietary RTCM standard text,
claim message support, or provide a production bit layout. Authentic station
observations, GNSS epochs, verified coordinates, an approved correction model,
and independent decoder/positioning validation are required before any real
generation can be considered.

All fixtures are labelled:

```text
SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS
```

Run focused tests with the repository environment:

```bash
.venv/bin/python -m pytest research/rtcm_generation/tests -q
```
