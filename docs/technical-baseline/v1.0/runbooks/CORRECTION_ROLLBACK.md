# Runbook: Correction Engine Rollback

1. Freeze new deployment.
2. Identify affected algorithm/config build.
3. Restore previously validated image/configuration.
4. Replay benchmark corpus and recent incident window.
5. Re-enable production cell gradually.
6. Open ADR/change review before reattempting release.
