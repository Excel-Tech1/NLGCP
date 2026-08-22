# Runbook: Station Offline

1. Confirm stream/endpoint failure in monitoring.
2. Verify whether upstream provider or local communications are responsible.
3. Ensure station state is `UNAVAILABLE` and excluded from processing.
4. Check remaining cell geometry/integrity.
5. If cell cannot meet integrity, degrade/stop VRS; evaluate eligible single-base service.
6. Notify provider/site operator.
7. On recovery, enforce recovery/QC window before re-admission.
8. Close incident with outage period and correction-service impact.
