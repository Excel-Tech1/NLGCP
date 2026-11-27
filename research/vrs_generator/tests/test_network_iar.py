"""Unit tests for B-03 Network Integer Ambiguity Resolution & LAMBDA ILS engine."""

from __future__ import annotations

import pytest
from nlgcp_vrs.network_iar import (
    IF_WL_COEFF_M,
    LAMBDA_NL_M,
    AmbiguityStatus,
    check_network_loop_closure,
    lambda_ils_resolve,
    resolve_dd_widelane,
    solve_if_narrowlane_with_zwd,
)

# SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS


def test_dd_widelane_resolution_and_rejection() -> None:
    good = resolve_dd_widelane(
        ref_sat="G01",
        sat="G05",
        dd_mw_cycles=[12.04, 11.97, 12.02, 11.98, 12.01, 11.99, 12.03, 11.96, 12.00, 12.02],
        weights=[1.0] * 10,
    )
    assert good.fixed is True
    assert good.nearest_int == 12
    assert good.bootstrapped_prob > 0.999

    noisy = resolve_dd_widelane(
        ref_sat="G01",
        sat="G05",
        dd_mw_cycles=[12.35, 12.40, 12.38, 12.32, 12.41, 12.39, 12.36, 12.34, 12.37, 12.33],
        weights=[1.0] * 10,
    )
    assert noisy.fixed is False
    assert "frac" in noisy.reason


def test_lambda_decorrelation_and_exact_ils_recovery() -> None:
    """Highly correlated 4D covariance: Z-decorrelation recovers exact integers."""
    from nlgcp_vrs.network_iar import _ltdl_factorize, _z_reduction

    true_int = [5, -3, 12, 7]
    # Construct Q_aa = U^T diag(d) U with unimodular integer shear U (|det U| = 1)
    # -> strongly correlated float ambiguities with small true determinant
    u_mat = [
        [1, 3, 2, 1],
        [0, 1, 2, 1],
        [0, 0, 1, 2],
        [0, 0, 0, 1],
    ]
    d_true = [0.008, 0.009, 0.010, 0.011]
    q_aa = [
        [sum(u_mat[k][i] * d_true[k] * u_mat[k][j] for k in range(4)) for j in range(4)]
        for i in range(4)
    ]
    # Verify exact Z^T Q Z == L_red^T D_red L_red invariant
    l0, d0 = _ltdl_factorize(q_aa)
    l_red, d_red, z_mat = _z_reduction(l0, d0)
    # Compute Z^T Q Z
    zt_q = [[sum(z_mat[r][i] * q_aa[r][c] for r in range(4)) for c in range(4)] for i in range(4)]
    zt_q_z = [[sum(zt_q[i][r] * z_mat[r][j] for r in range(4)) for j in range(4)] for i in range(4)]
    lt_d_l = [
        [sum(l_red[k][i] * d_red[k] * l_red[k][j] for k in range(4)) for j in range(4)]
        for i in range(4)
    ]
    for i in range(4):
        for j in range(4):
            assert zt_q_z[i][j] == pytest.approx(lt_d_l[i][j], abs=1e-10)

    # Draw a_hat from the actual correlated covariance Q_aa = U^T diag(d) U:
    # a_hat = true_int + U^T * eps with small eps (~0.8 sigma along each eigenmode).
    eps = [0.06, -0.07, 0.05, -0.06]
    a_hat = [true_int[i] + sum(u_mat[k][i] * eps[k] for k in range(4)) for i in range(4)]
    res = lambda_ils_resolve(a_hat, q_aa, ratio_threshold=3.0, min_success_rate=0.99)
    assert res.decorrelation_gain > 10.0
    assert res.a_fixed == tuple(true_int)
    assert res.status == AmbiguityStatus.FIXED_VALIDATED
    assert res.ratio >= 3.0
    assert res.bootstrapped_success_rate > 0.99


def test_lambda_matches_bruteforce_with_nonidentity_reduced_l() -> None:
    """Verify exact ILS distances & candidates when L_red has nonzero off-diagonals."""
    import itertools

    from nlgcp_vrs.network_iar import _invert_matrix

    # Non-unimodular correlated 3D covariance so Z-reduced L still has nonzero off-diagonals
    q_aa = [
        [0.45, 0.31, 0.22],
        [0.31, 0.36, 0.25],
        [0.22, 0.25, 0.29],
    ]
    a_hat = [1.32, -2.18, 0.74]
    q_inv = _invert_matrix(q_aa)

    scored: list[tuple[float, tuple[int, int, int]]] = []
    for cand in itertools.product(range(-2, 5), range(-5, 2), range(-2, 4)):
        diff = [cand[i] - a_hat[i] for i in range(3)]
        d2 = sum(diff[i] * q_inv[i][j] * diff[j] for i in range(3) for j in range(3))
        scored.append((d2, cand))
    scored.sort(key=lambda item: item[0])

    res = lambda_ils_resolve(a_hat, q_aa, ratio_threshold=1.0, min_success_rate=0.0)
    assert res.a_fixed == scored[0][1]
    assert res.a_second == scored[1][1]
    assert res.d1_sq == pytest.approx(scored[0][0], abs=1e-9)
    assert res.d2_sq == pytest.approx(scored[1][0], abs=1e-9)


def test_lambda_fails_closed_on_ambiguous_covariance() -> None:
    """Large uncertainty / near-half-integer float MUST remain FLOAT_ONLY (zero false fix)."""
    a_hat = [5.48, -3.49, 12.47, 7.51]
    q_aa = [
        [1.5, 0.2, 0.1, 0.0],
        [0.2, 1.5, 0.2, 0.1],
        [0.1, 0.2, 1.5, 0.2],
        [0.0, 0.1, 0.2, 1.5],
    ]
    res = lambda_ils_resolve(a_hat, q_aa, ratio_threshold=3.0, min_success_rate=0.995)
    assert res.status == AmbiguityStatus.FLOAT_ONLY
    assert res.a_fixed is None
    assert res.ratio < 3.0


def test_joint_if_narrowlane_with_zwd_fixes_clean_and_rejects_corrupted() -> None:
    sats = ["G02", "G05", "G07", "G12", "G15"]
    true_wl = {"G02": 3, "G05": -2, "G07": 4, "G12": -1, "G15": 2}
    true_n1 = {"G02": 14, "G05": -9, "G07": 21, "G12": 6, "G15": -11}
    true_zwd = 0.035
    epoch_obs = []
    for k in range(30):
        ep: dict[str, tuple[float, float, float]] = {}
        for idx, s in enumerate(sats):
            dm_w = 0.4 + 0.15 * idx + 0.01 * k
            y_if = dm_w * true_zwd + LAMBDA_NL_M * true_n1[s] + IF_WL_COEFF_M * true_wl[s]
            ep[s] = (y_if, dm_w, 1.0)
        epoch_obs.append(ep)

    clean = solve_if_narrowlane_with_zwd(sat_ids=sats, epoch_obs=epoch_obs, fixed_wl_by_sat=true_wl)
    assert clean["status"] == str(AmbiguityStatus.FIXED_VALIDATED)
    assert clean["fixed_n1"] == true_n1
    assert clean["delta_zwd_fixed_m"] == pytest.approx(true_zwd, abs=1e-3)

    # Inject gross 6 cm bias on G15 -> PAR drops G15 and fixes remaining 4 OR stays FLOAT_ONLY
    corrupt_obs = [dict(ep) for ep in epoch_obs]
    for k in range(30):
        y, dm, w = corrupt_obs[k]["G15"]
        # Varying bias prevents absorption into constant integer N1
        corrupt_obs[k]["G15"] = (y + 0.08 * ((-1) ** k), dm, w)
    corrupt = solve_if_narrowlane_with_zwd(
        sat_ids=sats, epoch_obs=corrupt_obs, fixed_wl_by_sat=true_wl, max_postfix_rms_m=0.025
    )
    assert corrupt["status"] in (
        str(AmbiguityStatus.FLOAT_ONLY),
        str(AmbiguityStatus.REJECTED_FALSE_FIX),
        str(AmbiguityStatus.PARTIAL_FIXED_VALIDATED),
    )
    assert "G15" not in corrupt.get("fixed_n1", {})


def test_network_loop_closure_check() -> None:
    ok = check_network_loop_closure(
        {"G02": 10, "G05": -4}, {"G02": -3, "G05": 7}, {"G02": 7, "G05": 3}
    )
    assert ok["passed"] is True
    bad = check_network_loop_closure(
        {"G02": 10, "G05": -4}, {"G02": -3, "G05": 7}, {"G02": 8, "G05": 3}
    )
    assert bad["passed"] is False
    assert bad["nonzero_closures"] == {"G02": -1}


def test_false_fix_prevention_all_nine_failure_modes() -> None:
    """Section 7.4 false-fix suite: covers all 9 required fail-closed scenarios."""
    from nlgcp_vrs.network_iar import (
        FalseFixGuardConfig,
        audit_rover_fix_stream,
        validate_wavelength_consistency,
    )

    cfg = FalseFixGuardConfig(min_ratio=5.0, min_persistence_epochs=3)

    # 1. Wrong wavelength / wrong signal combination rejected fail-closed
    ok_gps, _ = validate_wavelength_consistency(
        constellation="G",
        freq1_hz=1575.42e6,
        freq2_hz=1227.60e6,
        wavelength1_m=299_792_458.0 / 1575.42e6,
        wavelength2_m=299_792_458.0 / 1227.60e6,
    )
    assert ok_gps is True
    bad_wl, reason_wl = validate_wavelength_consistency(
        constellation="G",
        freq1_hz=1575.42e6,
        freq2_hz=1227.60e6,
        wavelength1_m=0.187,  # Wrong GLONASS-like wavelength on GPS
        wavelength2_m=299_792_458.0 / 1227.60e6,
    )
    assert bad_wl is False
    assert "wavelength_mismatch" in reason_wl

    bad_sig, reason_sig = validate_wavelength_consistency(
        constellation="G",
        freq1_hz=1575.42e6,
        freq2_hz=1575.42e6,  # Identical signal frequencies
        wavelength1_m=299_792_458.0 / 1575.42e6,
        wavelength2_m=299_792_458.0 / 1575.42e6,
    )
    assert bad_sig is False
    assert "invalid_or_identical_frequencies" in reason_sig

    # 2. Multipath-corrupted MW wide-lane arc fails closed
    mp_wl = resolve_dd_widelane(
        ref_sat="G01",
        sat="G09",
        dd_mw_cycles=[5.0 + 0.9 * ((-1) ** k) for k in range(15)],
        weights=[1.0] * 15,
    )
    assert mp_wl.fixed is False
    assert "sigma" in mp_wl.reason

    # 3-9. Stream false-fix guard: poor geometry, cycle slips, data gaps, atmo/ROTI error,
    #      ref station failure, B-02-like 2-epoch wrong-integer jump, and genuine persistent FIX
    stream = [
        # Float baseline reference
        {"quality": 2, "ratio": 1.2, "ns": 8, "age_s": 0.0, "sd_3d_m": 0.25, "pos_m": (0, 0, 0)},
        # Poor satellite geometry (DOP > 4.0)
        {
            "quality": 1,
            "ratio": 8.0,
            "ns": 7,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.01, 0, 0),
            "dop": 6.5,
        },
        # Active cycle slip
        {
            "quality": 1,
            "ratio": 8.0,
            "ns": 7,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.01, 0, 0),
            "cycle_slip": True,
        },
        # Data gap > 30s
        {
            "quality": 1,
            "ratio": 8.0,
            "ns": 7,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.01, 0, 0),
            "gap_s": 90.0,
        },
        # Disturbed ionosphere (post-sunset ROTI > 0.5, like B-02 19:53 UTC false fix)
        {
            "quality": 1,
            "ratio": 6.0,
            "ns": 6,
            "age_s": 0.0,
            "sd_3d_m": 0.04,
            "pos_m": (2.35, 0.38, -2.90),
            "roti_tecu_per_min": 1.2,
        },
        # Reference station failure
        {
            "quality": 1,
            "ratio": 8.0,
            "ns": 8,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.01, 0, 0),
            "ref_healthy": False,
        },
        # Transient 2-epoch spike with low ratio (like B-02 vrs_zero_geom_only)
        {
            "quality": 1,
            "ratio": 3.5,
            "ns": 6,
            "age_s": 0.0,
            "sd_3d_m": 0.03,
            "pos_m": (0.02, 0.01, 0),
        },
        {
            "quality": 1,
            "ratio": 3.6,
            "ns": 6,
            "age_s": 0.0,
            "sd_3d_m": 0.03,
            "pos_m": (0.02, 0.01, 0),
        },
        # Genuine 3-epoch persistent validated FIX consistent with float
        {
            "quality": 1,
            "ratio": 8.5,
            "ns": 8,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.03, -0.02, 0.04),
        },
        {
            "quality": 1,
            "ratio": 9.1,
            "ns": 8,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.03, -0.02, 0.04),
        },
        {
            "quality": 1,
            "ratio": 9.4,
            "ns": 8,
            "age_s": 0.0,
            "sd_3d_m": 0.02,
            "pos_m": (0.03, -0.02, 0.04),
        },
    ]
    res = audit_rover_fix_stream(stream, config=cfg, baseline_km=216.0, ionosphere_corrected=True)
    assert res["raw_q1_epochs"] == 10
    assert res["validated_fix_epochs"] == 3
    assert res["rejected_q1_epochs"] == 7
    hist = res["rejection_reasons_histogram"]
    assert hist["poor_geometry_dop"] == 1
    assert hist["active_cycle_slip"] == 1
    assert hist["data_gap"] == 1
    assert hist["disturbed_iono_roti"] == 1
    assert hist["pos_jump_from_float"] == 1
    assert hist["reference_station_unhealthy"] == 1
    assert hist["low_ratio"] == 2

    # Uncorrected 216 km baseline (like B-02 vrs_tropo_unb3m_only) blocks all Q=1
    res_uncorr = audit_rover_fix_stream(
        stream[8:], config=cfg, baseline_km=216.0, ionosphere_corrected=False
    )
    assert res_uncorr["validated_fix_epochs"] == 0
    assert res_uncorr["rejection_reasons_histogram"]["uncorrected_long_baseline"] == 3
