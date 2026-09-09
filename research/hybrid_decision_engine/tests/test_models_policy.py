"""Tests for request/policy models and provisional labelling.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import pytest
from nlgcp_hybrid_decision.models import (
    DecisionBlocked,
    DecisionRequest,
    DesiredMode,
    request_from_dict,
)
from nlgcp_hybrid_decision.policy import (
    POLICY_STATUS_PROVISIONAL,
    DecisionPolicy,
    DistancePolicy,
    policy_fingerprint,
    policy_from_dict,
)
from phase8_fixtures import policy


def test_valid_request_passes() -> None:
    request = request_from_dict({
        "request_id": "r1",
        "request_time": "2024-01-26T12:00:00Z",
        "target_ecef": [6308877.98, 772269.10, 530087.61],
        "desired_mode": "AUTO",
        "year": 2024,
        "day_of_year": 26,
    })
    assert request.validate() == []


def test_request_missing_target_blocked() -> None:
    request = DecisionRequest(request_id="r", request_time="t")
    assert any("target coordinate" in p for p in request.validate())
    with pytest.raises(DecisionBlocked):
        request.assert_valid()


def test_request_bad_latitude_blocked() -> None:
    request = DecisionRequest(
        request_id="r", request_time="t", target_latitude=999.0,
        target_longitude=0.0,
    )
    assert any("latitude" in p for p in request.validate())


def test_request_unknown_mode_blocked() -> None:
    with pytest.raises(DecisionBlocked):
        request_from_dict({
            "request_id": "r", "request_time": "t",
            "target_ecef": [1.0, 2.0, 3.0], "desired_mode": "MAGIC",
        })


def test_request_malformed_missing_id() -> None:
    with pytest.raises(DecisionBlocked):
        request_from_dict({"request_time": "t"})


def test_request_station_target_valid() -> None:
    request = request_from_dict({
        "request_id": "r", "request_time": "t",
        "target_station_id": "PHRI00NGA", "desired_mode": "SINGLE_BASE_ONLY",
    })
    assert request.validate() == []
    assert request.desired_mode == DesiredMode.SINGLE_BASE_ONLY


def test_distance_bands_provisional() -> None:
    assert DistancePolicy().calibration == POLICY_STATUS_PROVISIONAL
    assert policy().distance.calibration == POLICY_STATUS_PROVISIONAL


def test_policy_band_ordering() -> None:
    pol = policy()
    assert pol.distance.band(1000.0) == "preferred"
    assert pol.distance.band(200000.0) == "degraded"
    assert pol.distance.band(600000.0) == "maximum"
    assert pol.distance.band(5_000_000.0) == "beyond_maximum"
    assert pol.distance.band(None) == "unknown"


def test_policy_rejects_below_floor() -> None:
    pol = DecisionPolicy(minimum_network_reference_count=1)
    assert any("floor" in p for p in pol.validate())


def test_policy_rejects_unordered_bands() -> None:
    pol = DecisionPolicy(distance=DistancePolicy(
        preferred_max_m=500000.0, degraded_max_m=100000.0,
        maximum_allowed_m=1100000.0,
    ))
    assert any("preferred <=" in p for p in pol.validate())


def test_policy_malformed_raises() -> None:
    with pytest.raises(ValueError):
        policy_from_dict({"distance": "not-a-mapping"})


def test_policy_fingerprint_stable() -> None:
    assert policy_fingerprint(policy()) == policy_fingerprint(policy())


def test_policy_change_invalidates_fingerprint() -> None:
    altered = policy_from_dict({**policy().as_dict(), "allow_extrapolation": True})
    assert policy_fingerprint(altered) != policy_fingerprint(policy())
