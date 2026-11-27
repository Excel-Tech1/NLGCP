"""Network-level Double-Difference Integer Ambiguity Resolution & LAMBDA engine (B-03).

Implements standard geodetic GNSS ambiguity resolution mathematics with strict
fail-closed false-fix prevention:

1. **Wide-Lane (WL) Resolution**: Elevation-weighted double-difference Melbourne-Wubbena
   combination over slip-free common arcs, canceling all satellite & receiver hardware
   code/phase biases.
2. **Ionosphere-Free Narrow-Lane (NL) Estimation**: Joint weighted least-squares / epoch
   stacking of differential zenith wet delay ``delta_ZWD`` and DD narrow-lane ambiguities
   ``DD_N1`` using known verified reference-station coordinates (``lambda_NL = c/(f1+f2)``).
3. **LAMBDA Integer Least Squares (Teunissen 1995; Chang et al. 2005)**:
   - ``L^T D L`` factorization;
   - Unimodular integer ``Z``-decorrelation (integer Gauss + adjacent pivot swaps);
   - Exact Schnorr-Euchner search for the two best integer candidates ``z_1, z_2``;
   - Exact Teunissen (1998) bootstrapped lower bound on ILS success rate ``P_B``;
   - Partial Ambiguity Resolution (PAR) subset search;
   - Multi-gate validation (ratio test, bootstrapped success rate, post-fix IF residual
     RMS, and network triangle loop-closure ``N_AB + N_BC - N_AC == 0``).
4. **Fail-Closed Guarantee**: If any validation gate fails, status remains ``FLOAT_ONLY``
   and no unverified integer fix is ever asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nlgcp_atmospheric_model.constants import GPS_L1_HZ, GPS_L2_HZ, SPEED_OF_LIGHT_M_S
from nlgcp_atmospheric_model.observations import GPS_L2_WAVELENGTH_M

LAMBDA_WL_M = SPEED_OF_LIGHT_M_S / (GPS_L1_HZ - GPS_L2_HZ)  # 0.8619184003 m
LAMBDA_NL_M = SPEED_OF_LIGHT_M_S / (GPS_L1_HZ + GPS_L2_HZ)  # 0.1069533781 m
IF_ALPHA1 = (GPS_L1_HZ**2) / (GPS_L1_HZ**2 - GPS_L2_HZ**2)  # 2.5457277802
IF_ALPHA2 = (GPS_L2_HZ**2) / (GPS_L1_HZ**2 - GPS_L2_HZ**2)  # 1.5457277802
# Exact coefficient of N_WL in L_IF = rho + T + LAMBDA_NL * N1 + IF_WL_COEFF * N_WL
IF_WL_COEFF_M = IF_ALPHA2 * GPS_L2_WAVELENGTH_M  # 0.3774821... m


class AmbiguityStatus(StrEnum):
    FIXED_VALIDATED = "FIXED_VALIDATED"
    PARTIAL_FIXED_VALIDATED = "PARTIAL_FIXED_VALIDATED"
    FLOAT_ONLY = "FLOAT_ONLY"
    REJECTED_FALSE_FIX = "REJECTED_FALSE_FIX"


@dataclass(frozen=True, slots=True)
class WideLaneResult:
    """Wide-lane DD ambiguity result for one (ref_sat, sat) pair over a common arc."""

    ref_sat: str
    sat: str
    n_epochs: int
    float_cycles: float
    sigma_cycles: float
    nearest_int: int
    fractional_offset: float
    bootstrapped_prob: float
    fixed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class LambdaResult:
    """Result of LAMBDA Z-decorrelation, Schnorr-Euchner ILS search, and validation."""

    dimension: int
    status: AmbiguityStatus
    z_fixed: tuple[int, ...] | None
    a_fixed: tuple[int, ...] | None
    a_second: tuple[int, ...] | None
    d1_sq: float
    d2_sq: float
    ratio: float
    bootstrapped_success_rate: float
    decorrelation_gain: float
    reasons: tuple[str, ...]


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bootstrapped_success_rate(d_diag: list[float]) -> float:
    """Teunissen (1998) exact bootstrapped success rate lower bound from conditional variances."""
    prob = 1.0
    for d in d_diag:
        if d <= 0.0:
            return 0.0
        p_i = 2.0 * normal_cdf(0.5 / math.sqrt(d)) - 1.0
        prob *= max(0.0, min(1.0, p_i))
    return prob


def resolve_dd_widelane(
    *,
    ref_sat: str,
    sat: str,
    dd_mw_cycles: list[float],
    weights: list[float],
    min_epochs: int = 10,
    max_frac_cycles: float = 0.20,
    max_sigma_cycles: float = 0.15,
    min_prob: float = 0.999,
) -> WideLaneResult:
    """Resolve one double-difference GPS wide-lane ambiguity from Melbourne-Wubbena."""
    n = len(dd_mw_cycles)
    if n == 0 or len(weights) != n:
        return WideLaneResult(
            ref_sat, sat, 0, math.nan, math.nan, 0, math.nan, 0.0, False, "empty_arc"
        )
    w_sum = sum(weights)
    if w_sum <= 0.0:
        return WideLaneResult(
            ref_sat, sat, n, math.nan, math.nan, 0, math.nan, 0.0, False, "zero_weight"
        )
    mean_wl = sum(w * v for w, v in zip(weights, dd_mw_cycles, strict=True)) / w_sum
    if n >= 2:
        var_sample = sum(
            w * (v - mean_wl) ** 2 for w, v in zip(weights, dd_mw_cycles, strict=True)
        ) / w_sum
        # Conservative sigma of the mean with 0.03-cycle floor against multipath correlation
        eff_n = (w_sum * w_sum) / max(1e-12, sum(w * w for w in weights))
        sigma_wl = max(0.03, math.sqrt(max(0.0, var_sample) / max(1.0, eff_n - 1.0)))
    else:
        sigma_wl = 1.0

    nearest = round(mean_wl)
    frac = abs(mean_wl - nearest)
    prob = 2.0 * normal_cdf(0.5 / max(1e-6, sigma_wl)) - 1.0

    reasons: list[str] = []
    if n < min_epochs:
        reasons.append(f"short_arc({n}<{min_epochs})")
    if frac > max_frac_cycles:
        reasons.append(f"frac({frac:.3f}>{max_frac_cycles})")
    if sigma_wl > max_sigma_cycles:
        reasons.append(f"sigma({sigma_wl:.3f}>{max_sigma_cycles})")
    if prob < min_prob:
        reasons.append(f"prob({prob:.5f}<{min_prob})")

    return WideLaneResult(
        ref_sat=ref_sat,
        sat=sat,
        n_epochs=n,
        float_cycles=mean_wl,
        sigma_cycles=sigma_wl,
        nearest_int=nearest,
        fractional_offset=frac,
        bootstrapped_prob=prob,
        fixed=len(reasons) == 0,
        reason="OK" if not reasons else ";".join(reasons),
    )


def _ltdl_factorize(q_mat: list[list[float]]) -> tuple[list[list[float]], list[float]]:
    """Compute Q = L^T D L factorization (L unit lower triangular, D positive diagonal).

    Follows Teunissen / Chang et al. (2005) backward factorization so Schnorr-Euchner
    search proceeds cleanly from index n-1 down to 0.
    """
    n = len(q_mat)
    a = [[float(q_mat[i][j]) for j in range(n)] for i in range(n)]
    l_mat = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    d_vec = [0.0] * n
    for k in range(n - 1, -1, -1):
        dk = a[k][k]
        if dk <= 1e-15 or not math.isfinite(dk):
            raise ValueError(f"Covariance matrix not positive definite at pivot {k}: {dk}")
        d_vec[k] = dk
        for i in range(k):
            l_mat[k][i] = a[k][i] / dk
        for i in range(k):
            for j in range(i + 1):
                a[i][j] -= l_mat[k][i] * l_mat[k][j] * dk
                a[j][i] = a[i][j]
    return l_mat, d_vec


def _z_reduction(
    l_mat: list[list[float]], d_vec: list[float]
) -> tuple[list[list[float]], list[float], list[list[int]]]:
    """Teunissen LAMBDA integer Z-transformation (size reduction + adjacent pivot swaps).

    Returns updated (L, D, Z) where ``Z`` is unimodular integer (|det Z| = 1) such that
    ``Z^T Q Z = L_new^T diag(D_new) L_new`` and ``z = Z^T a``.
    """
    n = len(d_vec)
    l_cur = [row[:] for row in l_mat]
    d_cur = d_vec[:]
    # Z stored as columns Z[:, j]; initialized to identity
    z_mat = [[1 if i == j else 0 for j in range(n)] for i in range(n)]

    def _gauss(i: int, j: int) -> None:
        mu = round(l_cur[i][j])
        if mu == 0:
            return
        for row in range(i, n):
            l_cur[row][j] -= mu * l_cur[row][i]
        # Z[:, j] <- Z[:, j] - mu * Z[:, i]
        for r in range(n):
            z_mat[r][j] -= mu * z_mat[r][i]

    def _perm(k: int, delta: float) -> None:
        # Swap pivots k and k+1 in L^T D L
        eta = d_cur[k] / delta
        lam = d_cur[k + 1] * l_cur[k + 1][k] / delta
        d_cur[k] = eta * d_cur[k + 1]
        d_cur[k + 1] = delta
        for j in range(k):
            t0 = l_cur[k][j]
            t1 = l_cur[k + 1][j]
            l_cur[k][j] = t1 - l_cur[k + 1][k] * t0
            l_cur[k + 1][j] = lam * t1 + eta * t0
        l_cur[k + 1][k] = lam
        for i in range(k + 2, n):
            l_cur[i][k], l_cur[i][k + 1] = l_cur[i][k + 1], l_cur[i][k]
        for r in range(n):
            z_mat[r][k], z_mat[r][k + 1] = z_mat[r][k + 1], z_mat[r][k]

    k = n - 2
    k1 = n - 2
    max_iter = 200 * max(1, n * n)
    iters = 0
    while k >= 0 and iters < max_iter:
        iters += 1
        if k <= k1:
            for i in range(k + 1, n):
                _gauss(i, k)
        delta = d_cur[k] + (l_cur[k + 1][k] ** 2) * d_cur[k + 1]
        if delta < d_cur[k + 1] - 1e-12:
            _perm(k, delta)
            k1 = k
            k = min(n - 2, k + 1)
        else:
            k -= 1
    return l_cur, d_cur, z_mat


def _schnorr_euchner_two_best(
    z_hat: list[float], l_mat: list[list[float]], d_vec: list[float], max_nodes: int = 200_000
) -> tuple[list[int], list[int], float, float]:
    """Exact Schnorr-Euchner enumeration finding the 2 best integer vectors in Z^n.

    Minimizes ``(z - z_hat)^T (L^T D L)^{-1} (z - z_hat) = sum_k (z_k - zb_k)^2 / D_k``
    where ``L^T u = z - z_hat``, ``u_k = z_k - zb_k``, and
    ``zb_k = z_hat_k + sum_{j=k+1}^{n-1} L_{j,k} * u_j``.
    """
    n = len(z_hat)
    dist = [0.0] * (n + 1)
    zb = [0.0] * n
    z = [0] * n
    step = [0] * n

    best: list[tuple[float, list[int]]] = []
    chi2 = float("inf")

    k = n - 1
    zb[k] = z_hat[k]
    z[k] = round(zb[k])
    y = zb[k] - z[k]
    step[k] = 1 if y >= 0.0 else -1

    nodes = 0
    while nodes < max_nodes:
        nodes += 1
        y = zb[k] - z[k]
        newdist = dist[k + 1] + (y * y) / d_vec[k]
        if newdist < chi2:
            if k > 0:
                k -= 1
                dist[k + 1] = newdist
                zb[k] = z_hat[k] + sum(
                    l_mat[j][k] * (z[j] - zb[j]) for j in range(k + 1, n)
                )
                z[k] = round(zb[k])
                y_k = zb[k] - z[k]
                step[k] = 1 if y_k >= 0.0 else -1
            else:
                # Reached leaf: record candidate
                best.append((newdist, z[:]))
                best.sort(key=lambda item: item[0])
                if len(best) > 2:
                    best = best[:2]
                if len(best) == 2:
                    chi2 = best[1][0]
                # Try next integer at k=0
                z[0] += step[0]
                step[0] = -step[0] - (1 if step[0] > 0 else -1)
        else:
            if k == n - 1:
                break
            k += 1
            z[k] += step[k]
            step[k] = -step[k] - (1 if step[k] > 0 else -1)

    if len(best) < 2:
        raise RuntimeError("Schnorr-Euchner search did not find two integer candidates")
    return best[0][1], best[1][1], best[0][0], best[1][0]


def _solve_linear_system(a_in: list[list[float]], b_in: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for small dense systems."""
    n = len(b_in)
    a = [row[:] + [b_in[i]] for i, row in enumerate(a_in)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-14:
            raise ValueError("Singular linear system")
        a[col], a[piv] = a[piv], a[col]
        diag = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= diag
        for r in range(n):
            if r != col and a[r][col] != 0.0:
                fac = a[r][col]
                for j in range(col, n + 1):
                    a[r][j] -= fac * a[col][j]
    return [a[i][n] for i in range(n)]


def _invert_matrix(m: list[list[float]]) -> list[list[float]]:
    n = len(m)
    inv_cols = []
    for j in range(n):
        e = [1.0 if i == j else 0.0 for i in range(n)]
        inv_cols.append(_solve_linear_system(m, e))
    return [[inv_cols[j][i] for j in range(n)] for i in range(n)]


def lambda_ils_resolve(
    a_hat: list[float],
    q_aa: list[list[float]],
    *,
    ratio_threshold: float = 3.0,
    min_success_rate: float = 0.995,
) -> LambdaResult:
    """Resolve float ambiguity vector ``a_hat`` with covariance ``q_aa`` via LAMBDA ILS."""
    n = len(a_hat)
    if n == 0:
        return LambdaResult(
            0, AmbiguityStatus.FLOAT_ONLY, None, None, None, math.nan, math.nan, 0.0, 0.0, 1.0,
            ("empty_ambiguity_vector",),
        )
    l0, d0 = _ltdl_factorize(q_aa)
    p_before = bootstrapped_success_rate(d0)
    l_red, d_red, z_mat = _z_reduction(l0, d0)
    p_after = bootstrapped_success_rate(d_red)

    # z_hat = Z^T a_hat
    z_hat = [sum(z_mat[r][c] * a_hat[r] for r in range(n)) for c in range(n)]
    z1, z2, d1_sq, d2_sq = _schnorr_euchner_two_best(z_hat, l_red, d_red)

    # Back-transform a = Z^{-T} z (solve Z^T a = z)
    zt_float = [[float(z_mat[r][c]) for r in range(n)] for c in range(n)]
    a1_f = _solve_linear_system(zt_float, [float(v) for v in z1])
    a2_f = _solve_linear_system(zt_float, [float(v) for v in z2])
    a1 = tuple(round(v) for v in a1_f)
    a2 = tuple(round(v) for v in a2_f)

    ratio = d2_sq / max(d1_sq, 1e-12)
    gain = (max(d0) / min(d0)) / max(1e-12, max(d_red) / min(d_red))

    reasons: list[str] = []
    if ratio < ratio_threshold:
        reasons.append(f"ratio({ratio:.3f}<{ratio_threshold})")
    if p_after < min_success_rate:
        reasons.append(f"success_rate({p_after:.5f}<{min_success_rate})")

    status = AmbiguityStatus.FIXED_VALIDATED if not reasons else AmbiguityStatus.FLOAT_ONLY
    return LambdaResult(
        dimension=n,
        status=status,
        z_fixed=tuple(z1) if status == AmbiguityStatus.FIXED_VALIDATED else None,
        a_fixed=a1 if status == AmbiguityStatus.FIXED_VALIDATED else None,
        a_second=a2,
        d1_sq=d1_sq,
        d2_sq=d2_sq,
        ratio=ratio,
        bootstrapped_success_rate=p_after,
        decorrelation_gain=max(1.0, gain) if p_after >= p_before - 1e-9 else gain,
        reasons=tuple(reasons) if reasons else ("OK",),
    )


def solve_if_narrowlane_with_zwd(
    *,
    sat_ids: list[str],
    epoch_obs: list[dict[str, tuple[float, float, float]]],
    fixed_wl_by_sat: dict[str, int],
    prior_zwd_sigma_m: float = 0.08,
    phase_if_sigma_m: float = 0.012,
    ratio_threshold: float = 3.0,
    min_success_rate: float = 0.995,
    max_postfix_rms_m: float = 0.025,
    min_par_sats: int = 4,
) -> dict[str, Any]:
    """Jointly estimate baseline delta_ZWD + DD N1 narrow-lane ambiguities, then run LAMBDA+PAR.

    Each element of ``epoch_obs`` maps ``sat -> (dd_l_if_minus_geom_m, dd_wet_mf, weight)``.
    State vector ``x = [delta_ZWD, N1_0, N1_1, ..., N1_{m-1}]``.
    Observation equation:
      ``dd_l_if_minus_geom_m - IF_WL_COEFF_M * N_WL[s] =
        dd_wet_mf * delta_ZWD + LAMBDA_NL_M * N1[s]``
    """
    m = len(sat_ids)
    if m < min_par_sats:
        return {
            "status": str(AmbiguityStatus.FLOAT_ONLY),
            "reason": f"insufficient_wl_fixed_sats({m}<{min_par_sats})",
            "n_sats": m,
        }
    dim = 1 + m
    sat_idx = {s: i for i, s in enumerate(sat_ids)}
    ata = [[0.0] * dim for _ in range(dim)]
    atb = [0.0] * dim
    # Prior constraint on delta_ZWD (m)
    ata[0][0] += 1.0 / (prior_zwd_sigma_m**2)
    inv_var = 1.0 / (phase_if_sigma_m**2)
    n_obs = 0
    obs_list: list[tuple[int, float, float, float]] = []

    for ep_map in epoch_obs:
        for s, (y_if, dm_w, w_el) in ep_map.items():
            if s not in sat_idx or s not in fixed_wl_by_sat:
                continue
            j = 1 + sat_idx[s]
            y = y_if - IF_WL_COEFF_M * fixed_wl_by_sat[s]
            wt = inv_var * w_el
            ata[0][0] += wt * dm_w * dm_w
            ata[0][j] += wt * dm_w * LAMBDA_NL_M
            ata[j][0] += wt * dm_w * LAMBDA_NL_M
            ata[j][j] += wt * LAMBDA_NL_M * LAMBDA_NL_M
            atb[0] += wt * dm_w * y
            atb[j] += wt * LAMBDA_NL_M * y
            n_obs += 1
            obs_list.append((sat_idx[s], y, dm_w, w_el))

    if n_obs < dim + 10:
        return {
            "status": str(AmbiguityStatus.FLOAT_ONLY),
            "reason": f"insufficient_observations({n_obs})",
            "n_sats": m,
            "n_obs": n_obs,
        }

    x_hat = _solve_linear_system(ata, atb)
    q_xx = _invert_matrix(ata)

    # Compute float residuals and empirical variance factor s0^2 (prevents overconfident Q_aa!)
    rss_float = 0.0
    for si, y, dm_w, w_el in obs_list:
        pred = dm_w * x_hat[0] + LAMBDA_NL_M * x_hat[1 + si]
        r = y - pred
        rss_float += w_el * r * r
    dof = max(1, n_obs - dim)
    rms_float_m = math.sqrt(rss_float / n_obs)
    s0_scale = max(1.0, (rss_float * inv_var) / dof)

    a_hat_all = [x_hat[1 + i] for i in range(m)]
    q_aa_all = [[q_xx[1 + i][1 + j] * s0_scale for j in range(m)] for i in range(m)]

    # Partial Ambiguity Resolution: drop worst variance until pass or < min_par_sats
    active = list(range(m))
    best_res: LambdaResult | None = None
    best_active: list[int] = active[:]
    best_postfix_rms = math.nan

    while len(active) >= min_par_sats:
        sub_a = [a_hat_all[i] for i in active]
        sub_q = [[q_aa_all[i][j] for j in active] for i in active]
        lres = lambda_ils_resolve(
            sub_a, sub_q, ratio_threshold=ratio_threshold, min_success_rate=min_success_rate
        )
        if best_res is None:
            best_res = lres
            best_active = active[:]
        if lres.status == AmbiguityStatus.FIXED_VALIDATED and lres.a_fixed is not None:
            # Verify post-fix ionosphere-free residual RMS on the fixed subset
            fixed_map = {active[k]: lres.a_fixed[k] for k in range(len(active))}
            # Re-solve delta_ZWD holding fixed N1 integers constant
            num_z = 0.0
            den_z = 1.0 / (prior_zwd_sigma_m**2)
            for si, y, dm_w, w_el in obs_list:
                if si in fixed_map:
                    wt = inv_var * w_el
                    den_z += wt * dm_w * dm_w
                    num_z += wt * dm_w * (y - LAMBDA_NL_M * fixed_map[si])
            zwd_fix = num_z / den_z
            sq_fix = [
                (y - dm_w * zwd_fix - LAMBDA_NL_M * fixed_map[si]) ** 2
                for si, y, dm_w, _ in obs_list
                if si in fixed_map
            ]
            postfix_rms = math.sqrt(sum(sq_fix) / max(1, len(sq_fix)))
            best_postfix_rms = postfix_rms
            if postfix_rms <= max_postfix_rms_m:
                st_out = (
                    AmbiguityStatus.FIXED_VALIDATED
                    if len(active) == m
                    else AmbiguityStatus.PARTIAL_FIXED_VALIDATED
                )
                return {
                    "status": str(st_out),
                    "n_sats_total": m,
                    "n_sats_fixed": len(active),
                    "fixed_sats": [sat_ids[i] for i in active],
                    "fixed_n1": {sat_ids[active[k]]: lres.a_fixed[k] for k in range(len(active))},
                    "delta_zwd_float_m": round(x_hat[0], 5),
                    "delta_zwd_fixed_m": round(zwd_fix, 5),
                    "float_if_rms_m": round(rms_float_m, 5),
                    "postfix_if_rms_m": round(postfix_rms, 5),
                    "variance_factor_s0_sq": round(s0_scale, 3),
                    "ratio": round(lres.ratio, 3),
                    "bootstrapped_success_rate": round(lres.bootstrapped_success_rate, 6),
                    "decorrelation_gain": round(lres.decorrelation_gain, 2),
                    "reasons": ["OK"],
                }
            # Post-fix residual exceeded gate -> reject as false fix and try dropping worst sat
            best_res = LambdaResult(
                lres.dimension,
                AmbiguityStatus.REJECTED_FALSE_FIX,
                None,
                None,
                lres.a_second,
                lres.d1_sq,
                lres.d2_sq,
                lres.ratio,
                lres.bootstrapped_success_rate,
                lres.decorrelation_gain,
                (f"postfix_rms({postfix_rms:.4f}m>{max_postfix_rms_m}m)",),
            )
            best_active = active[:]

        # Drop satellite with largest diagonal float variance
        worst = max(active, key=lambda idx: q_aa_all[idx][idx])
        active = [idx for idx in active if idx != worst]

    assert best_res is not None
    return {
        "status": str(
            AmbiguityStatus.REJECTED_FALSE_FIX
            if best_res.status == AmbiguityStatus.REJECTED_FALSE_FIX
            else AmbiguityStatus.FLOAT_ONLY
        ),
        "n_sats_total": m,
        "n_sats_fixed": 0,
        "fixed_sats": [],
        "fixed_n1": {},
        "float_n1": {sat_ids[i]: round(a_hat_all[i], 4) for i in range(m)},
        "delta_zwd_float_m": round(x_hat[0], 5),
        "float_if_rms_m": round(rms_float_m, 5),
        "postfix_if_rms_m": round(best_postfix_rms, 5) if math.isfinite(best_postfix_rms) else None,
        "variance_factor_s0_sq": round(s0_scale, 3),
        "ratio": round(best_res.ratio, 3),
        "bootstrapped_success_rate": round(best_res.bootstrapped_success_rate, 6),
        "decorrelation_gain": round(best_res.decorrelation_gain, 2),
        "reasons": list(best_res.reasons),
        "attempted_subset_size": len(best_active),
    }


def check_network_loop_closure(
    n_ab: dict[str, int], n_bc: dict[str, int], n_ac: dict[str, int]
) -> dict[str, Any]:
    """Verify exact integer triangle closure ``N_AB + N_BC - N_AC == 0`` across 3 baselines."""
    common = sorted(set(n_ab) & set(n_bc) & set(n_ac))
    closures = {sat: n_ab[sat] + n_bc[sat] - n_ac[sat] for sat in common}
    nonzero = {sat: c for sat, c in closures.items() if c != 0}
    return {
        "common_satellites": len(common),
        "closures": closures,
        "nonzero_closures": nonzero,
        "passed": len(common) > 0 and len(nonzero) == 0,
    }


def validate_wavelength_consistency(
    *,
    constellation: str,
    freq1_hz: float,
    freq2_hz: float,
    wavelength1_m: float,
    wavelength2_m: float,
    tol_m: float = 1e-6,
) -> tuple[bool, str]:
    """Fail closed if supplied wavelengths do not match physical c / f for the constellation."""
    if freq1_hz <= 0.0 or freq2_hz <= 0.0 or freq1_hz == freq2_hz:
        return False, "invalid_or_identical_frequencies"
    if constellation == "G" and (
        abs(freq1_hz - GPS_L1_HZ) > 1.0 or abs(freq2_hz - GPS_L2_HZ) > 1.0
    ):
        return False, f"unexpected_gps_frequencies({freq1_hz},{freq2_hz})"
    exp1 = SPEED_OF_LIGHT_M_S / freq1_hz
    exp2 = SPEED_OF_LIGHT_M_S / freq2_hz
    if abs(wavelength1_m - exp1) > tol_m or abs(wavelength2_m - exp2) > tol_m:
        return (
            False,
            f"wavelength_mismatch(obs={wavelength1_m:.6f}/{wavelength2_m:.6f},"
            f"exp={exp1:.6f}/{exp2:.6f})",
        )
    return True, "OK"


@dataclass(frozen=True, slots=True)
class FalseFixGuardConfig:
    """Conservative multi-gate validation thresholds to block wrong-integer Q=1 false fixes."""

    min_ratio: float = 5.0
    min_satellites: int = 6
    max_age_s: float = 30.0
    max_formal_sd_3d_m: float = 0.15
    max_jump_from_float_m: float = 0.50
    min_persistence_epochs: int = 3
    max_roti_tecu_per_min: float = 0.50
    max_uncorrected_baseline_km: float = 30.0


@dataclass(frozen=True, slots=True)
class RoverFixEpochAudit:
    """Per-epoch audit result classifying raw Q=1 flags into validated vs rejected fixes."""

    epoch_index: int
    raw_quality: int
    validated_status: AmbiguityStatus
    ratio: float
    ns: int
    age_s: float
    formal_sd_3d_m: float
    jump_from_float_m: float | None
    rejection_reasons: tuple[str, ...]


def audit_rover_fix_stream(
    epochs: list[dict[str, Any]],
    *,
    config: FalseFixGuardConfig | None = None,
    baseline_km: float = 0.0,
    ionosphere_corrected: bool = True,
) -> dict[str, Any]:
    """Independently screen solver Q=1 epochs to reject wrong-integer false fixes fail-closed.

    Each item in ``epochs`` provides ``quality`` (int, 1=FIX, 2=FLOAT), ``ratio`` (float),
    ``ns`` (int), ``age_s`` (float), ``sd_3d_m`` (float), ``ecef_or_enu_m`` (3-tuple),
    and optional ``roti_tecu_per_min`` (float | None), ``gap_s`` (float), ``ref_healthy`` (bool),
    ``cycle_slip`` (bool), ``dop`` (float | None).
    """
    cfg = config or FalseFixGuardConfig()
    audits: list[RoverFixEpochAudit] = []
    last_float_pos: tuple[float, float, float] | None = None
    consecutive_passing = 0
    tentative_indices: list[int] = []

    raw_q1_count = 0
    validated_indices: set[int] = set()
    rejected_reasons_hist: dict[str, int] = {}

    for idx, ep in enumerate(epochs):
        q = int(ep.get("quality", 0))
        ratio = float(ep.get("ratio", 0.0))
        ns = int(ep.get("ns", 0))
        age_s = float(ep.get("age_s", 999.0))
        sd_3d = float(ep.get("sd_3d_m", 999.0))
        pos = ep.get("pos_m")
        pos_t: tuple[float, float, float] | None = (
            (float(pos[0]), float(pos[1]), float(pos[2])) if pos is not None else None
        )
        roti = ep.get("roti_tecu_per_min")
        ref_healthy = bool(ep.get("ref_healthy", True))
        cycle_slip = bool(ep.get("cycle_slip", False))
        gap_s = float(ep.get("gap_s", 0.0))
        dop = ep.get("dop")

        if q == 2 and pos_t is not None and ref_healthy:
            last_float_pos = pos_t
        if q != 1:
            consecutive_passing = 0
            tentative_indices.clear()
            audits.append(
                RoverFixEpochAudit(
                    idx, q, AmbiguityStatus.FLOAT_ONLY, ratio, ns, age_s, sd_3d, None, ()
                )
            )
            continue

        raw_q1_count += 1
        reasons: list[str] = []
        if not ref_healthy:
            reasons.append("reference_station_unhealthy")
        if cycle_slip:
            reasons.append("active_cycle_slip")
        if gap_s > cfg.max_age_s:
            reasons.append(f"data_gap({gap_s:.1f}s>{cfg.max_age_s}s)")
        if ratio < cfg.min_ratio:
            reasons.append(f"low_ratio({ratio:.2f}<{cfg.min_ratio})")
        if ns < cfg.min_satellites:
            reasons.append(f"low_sats({ns}<{cfg.min_satellites})")
        if age_s > cfg.max_age_s:
            reasons.append(f"stale_age({age_s:.1f}s>{cfg.max_age_s}s)")
        if sd_3d > cfg.max_formal_sd_3d_m:
            reasons.append(f"large_formal_sd({sd_3d:.3f}m>{cfg.max_formal_sd_3d_m}m)")
        if dop is not None and float(dop) > 4.0:
            reasons.append(f"poor_geometry_dop({float(dop):.2f}>4.0)")
        if roti is not None and float(roti) > cfg.max_roti_tecu_per_min:
            reasons.append(f"disturbed_iono_roti({float(roti):.2f}>{cfg.max_roti_tecu_per_min})")
        if not ionosphere_corrected and baseline_km > cfg.max_uncorrected_baseline_km:
            reasons.append(
                f"uncorrected_long_baseline({baseline_km:.1f}km>{cfg.max_uncorrected_baseline_km}km)"
            )

        jump_m: float | None = None
        if pos_t is not None and last_float_pos is not None:
            jump_m = math.dist(pos_t, last_float_pos)
            if jump_m > cfg.max_jump_from_float_m:
                reasons.append(f"pos_jump_from_float({jump_m:.3f}m>{cfg.max_jump_from_float_m}m)")

        if reasons:
            consecutive_passing = 0
            tentative_indices.clear()
            for r in reasons:
                tag = r.split("(", 1)[0]
                rejected_reasons_hist[tag] = rejected_reasons_hist.get(tag, 0) + 1
            audits.append(
                RoverFixEpochAudit(
                    idx,
                    q,
                    AmbiguityStatus.REJECTED_FALSE_FIX,
                    ratio,
                    ns,
                    age_s,
                    sd_3d,
                    jump_m,
                    tuple(reasons),
                )
            )
        else:
            consecutive_passing += 1
            tentative_indices.append(idx)
            audits.append(
                RoverFixEpochAudit(
                    idx,
                    q,
                    AmbiguityStatus.FLOAT_ONLY,
                    ratio,
                    ns,
                    age_s,
                    sd_3d,
                    jump_m,
                    ("pending_persistence",),
                )
            )
            if consecutive_passing >= cfg.min_persistence_epochs:
                validated_indices.update(tentative_indices)

    # Finalize audits: promote persistent validated fixes, mark short unconfirmed spikes rejected
    final_audits: list[RoverFixEpochAudit] = []
    for a in audits:
        if a.raw_quality == 1 and a.epoch_index in validated_indices:
            final_audits.append(
                RoverFixEpochAudit(
                    a.epoch_index,
                    a.raw_quality,
                    AmbiguityStatus.FIXED_VALIDATED,
                    a.ratio,
                    a.ns,
                    a.age_s,
                    a.formal_sd_3d_m,
                    a.jump_from_float_m,
                    ("OK",),
                )
            )
        elif a.raw_quality == 1 and a.validated_status != AmbiguityStatus.REJECTED_FALSE_FIX:
            rejected_reasons_hist["insufficient_persistence"] = (
                rejected_reasons_hist.get("insufficient_persistence", 0) + 1
            )
            final_audits.append(
                RoverFixEpochAudit(
                    a.epoch_index,
                    a.raw_quality,
                    AmbiguityStatus.REJECTED_FALSE_FIX,
                    a.ratio,
                    a.ns,
                    a.age_s,
                    a.formal_sd_3d_m,
                    a.jump_from_float_m,
                    (f"insufficient_persistence(<{cfg.min_persistence_epochs})",),
                )
            )
        else:
            final_audits.append(a)

    n_total = len(epochs)
    n_val_fix = len(validated_indices)
    n_rej = raw_q1_count - n_val_fix
    return {
        "total_epochs": n_total,
        "raw_q1_epochs": raw_q1_count,
        "validated_fix_epochs": n_val_fix,
        "rejected_q1_epochs": n_rej,
        "validated_fix_pct": round(100.0 * n_val_fix / n_total, 3) if n_total else 0.0,
        "rejected_q1_pct_of_raw": (
            round(100.0 * n_rej / raw_q1_count, 2) if raw_q1_count else 0.0
        ),
        "rejection_reasons_histogram": rejected_reasons_hist,
        "audits": final_audits,
    }
