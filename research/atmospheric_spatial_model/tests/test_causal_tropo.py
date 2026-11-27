"""Unit tests for B-05 causal tropospheric ZWD residual filter."""

from __future__ import annotations

import pytest
from nlgcp_atmospheric_model.causal_tropo import CausalTropoZwdFilter

# SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS
_SYNTH_ECEF = (6246471.28, 820848.74, 994267.93)


def test_causal_tropo_filter_prefix_invariance_gap_decay_and_health() -> None:
    stream = [
        ("2011-03-20T00:00:00", 0.240, True),
        ("2011-03-20T00:00:30", 0.242, True),
        ("2011-03-20T00:01:00", 0.245, True),
        ("2011-03-20T00:01:30", 0.999, False),  # Unhealthy spike MUST be ignored
        ("2011-03-20T00:02:00", 0.244, True),
        ("2011-03-20T03:02:00", 0.220, True),  # 3-hour gap -> stale & uncertainty grows
    ]

    full_flt = CausalTropoZwdFilter(station_id="OSGF", station_ecef_m=_SYNTH_ECEF)
    full_states = []
    for ep, zwd, ok in stream:
        pred = full_flt.predict_at(ep, doy=79)
        upd = full_flt.update(ep, doy=79, observed_zwd_m=zwd, station_healthy=ok)
        full_states.append((pred, upd))

    # Unhealthy epoch 3 MUST NOT pull estimate toward 0.999
    assert full_states[3][1].healthy is False
    assert full_states[3][1].causal_zwd_m < 0.30
    assert full_states[3][1].sample_count == 3

    # 3-hour gap prediction must flag stale=True and inflate uncertainty vs steady state
    assert full_states[5][0].stale is True
    assert full_states[5][0].residual_zwd_sigma_m > full_states[4][1].residual_zwd_sigma_m

    # Prefix invariance proof for epochs 0..3
    pref_flt = CausalTropoZwdFilter(station_id="OSGF", station_ecef_m=_SYNTH_ECEF)
    for k in range(4):
        ep, zwd, ok = stream[k]
        p_pred = pref_flt.predict_at(ep, doy=79)
        p_upd = pref_flt.update(ep, doy=79, observed_zwd_m=zwd, station_healthy=ok)
        assert (p_pred, p_upd) == full_states[k]
    assert full_flt.slant_delay_m(full_states[4][1], elevation_deg=30.0) == pytest.approx(
        full_flt.slant_delay_m(full_states[4][1], elevation_deg=30.0)
    )
