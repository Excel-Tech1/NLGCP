"""NLGCP Phase 8 hybrid correction decision engine.

Phase 8 decides WHICH correction strategy is permitted for a rover
(VRS, single-base fallback, or no correction).  It does NOT manufacture
a correction, promote a spatial model, or generate RTCM/NTRIP output.

All automatic VRS selection is fail-closed until reviewed Phase 6/7
scientific evidence marks the upstream assessments APPROVED.
"""

ENGINE_VERSION = "0.1.0"
DECISION_SCHEMA_VERSION = "1.0"
POLICY_SCHEMA_VERSION = "1.0"
REQUEST_SCHEMA_VERSION = "1.0"

# Minimum admitted reference stations for an automatic VRS network
# candidate.  Mirrors the Phase 5 scientifically justified triangle floor.
MIN_NETWORK_REFERENCES = 3
