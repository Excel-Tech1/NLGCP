# Runbook: High Correction Latency

1. Identify stage: upstream arrival, NATS lag, epoch wait, processing, encoding, caster or Internet edge.
2. Protect integrity: if correction age exceeds current threshold, mark service degraded.
3. Shed non-critical analytics/replay consumers if they contribute to resource pressure.
4. Scale/restart only the failing component if safe.
5. Verify scientific metrics after recovery, not just CPU/network health.
