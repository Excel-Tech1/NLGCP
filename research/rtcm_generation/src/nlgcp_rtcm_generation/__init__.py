"""Phase 11 correction-generation research package.

This package defines the boundary between scientifically admitted GNSS
content and binary RTCM framing.  It contains synthetic-fixture encoders
for RTCM 1005, GPS MSM4 1074, GLONASS MSM4 1084, and the lab-only 4095
test frame.  Operational correction output remains fail-closed.
"""

from __future__ import annotations

ENGINE_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"
ENCODER_VERSION = "synthetic-test-1.0"
ENCODER_VERSION_1005 = "rtcm1005-1.0"
ENCODER_VERSION_1006 = "rtcm1006-1.0"
ENCODER_VERSION_1007 = "rtcm1007-1.0"
ENCODER_VERSION_1008 = "rtcm1008-1.0"
ENCODER_VERSION_1020 = "rtcm1020-1.0"
ENCODER_VERSION_1033 = "rtcm1033-1.0"
ENCODER_VERSION_1230 = "rtcm1230-1.0"
ENCODER_VERSION_MSM4 = "msm4-1.0"
SYNTHETIC_LABEL = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"
