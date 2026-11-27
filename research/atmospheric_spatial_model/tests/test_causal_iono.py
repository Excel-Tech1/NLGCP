"""Unit tests for B-05 causal ionospheric filter, DCB/SINEX BIAS, and IONEX parsers.

Includes strict prefix-invariance causality proofs verifying that epoch ``k`` outputs
are bit-identical whether computed on prefix ``0..k`` or full stream ``0..N``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_atmospheric_model.causal_iono import (
    NS_TO_TECU,
    CausalIonoFilter,
    CausalNetworkDiffIonoTracker,
    combine_code_p1p2_p1c1_to_c1p2,
    parse_code_monthly_dcb,
    parse_ionex,
    parse_sinex_dsb,
    parse_sinex_osb_pair_diff,
)
from nlgcp_atmospheric_model.ionosphere_estimation import GF_M_PER_TECU
from nlgcp_atmospheric_model.observations import (
    GPS_L1_WAVELENGTH_M,
    GPS_L2_WAVELENGTH_M,
    SatObs,
)

# SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS
_OSGF_SYNTH_ECEF = (6246471.25, 820848.75, 994267.94)


def _synth_obs(
    stec_tecu: float,
    *,
    sat_dsb_c1_p2_ns: float = 0.0,
    rx_bias_tecu: float = 0.0,
    n1_amb: float = 1000.0,
    n2_amb: float = 800.0,
    lli1: int = 0,
) -> SatObs:
    """Build synthetic dual-frequency GPS observation with exact known STEC & DCB."""
    rho = 22_000_000.0
    i1 = stec_tecu * (40.308e16 / (1575.42e6**2))
    i2 = stec_tecu * (40.308e16 / (1227.60e6**2))
    # GF_code = P2 - C1 = (i2 - i1) - sat_dsb_c1_p2_m + rx_bias_m
    sat_bias_m = sat_dsb_c1_p2_ns * 1e-9 * 299_792_458.0
    rx_bias_m = rx_bias_tecu * GF_M_PER_TECU
    c1 = rho + i1 + sat_bias_m
    p2 = rho + i2 + rx_bias_m
    l1 = (rho - i1) / GPS_L1_WAVELENGTH_M + n1_amb
    l2 = (rho - i2) / GPS_L2_WAVELENGTH_M + n2_amb
    return SatObs(
        values={"C1": c1, "P2": p2, "L1": l1, "L2": l2},
        lli={"L1": lli1, "L2": 0},
        epoch_flag=0,
    )


def test_parse_code_dcb_and_combine(tmp_path: Path) -> None:
    p1p2 = tmp_path / "P1P2.DCB"
    p1p2.write_text(
        "CODE'S MONTHLY GNSS P1-P2 DCB\n"
        "***   ****************    *****.***   *****.***\n"
        "G01                           2.155       0.026\n"
        "G02                           5.426       0.005\n"
        "G     ABUZ                    1.200       0.050\n",
        encoding="ascii",
    )
    p1c1 = tmp_path / "P1C1.DCB"
    p1c1.write_text(
        "CODE'S MONTHLY GPS P1-C1 DCB\n"
        "***   ****************    *****.***   *****.***\n"
        "G01                           2.128       0.295\n"
        "G02                          -0.266       0.002\n",
        encoding="ascii",
    )
    t_p1p2 = parse_code_monthly_dcb(p1p2, "P1P2")
    t_p1c1 = parse_code_monthly_dcb(p1c1, "P1C1")
    assert set(t_p1p2.sat_bias_ns) == {"G01", "G02"}  # Station row ignored
    comb = combine_code_p1p2_p1c1_to_c1p2(t_p1p2, t_p1c1)
    assert comb["G01"] == pytest.approx(2.155 - 2.128, abs=1e-6)
    assert comb["G02"] == pytest.approx(5.426 - (-0.266), abs=1e-6)


def test_parse_sinex_dsb_and_osb(tmp_path: Path) -> None:
    bia = tmp_path / "test.BIA"
    bia.write_text(
        "+BIAS/SOLUTION\n"
        "*BIAS SVN_ PRN STATION__ OBS1 OBS2 BIAS_START____ BIAS_END______ UNIT VALUE STD\n"
        " DSB  G063 G01           C1C  C2W  2024:026:00000 2024:027:00000 ns -7.8750 0.0240\n"
        " OSB  G063 G01           C1C       2024:026:00000 2024:027:00000 ns -2.0000 0.0100\n"
        " OSB  G063 G01           C2W       2024:026:00000 2024:027:00000 ns  5.8750 0.0200\n"
        "-BIAS/SOLUTION\n",
        encoding="ascii",
    )
    dsb = parse_sinex_dsb(bia, obs1="C1C", obs2="C2W")
    assert dsb.sat_bias_ns["G01"] == pytest.approx(-7.875, abs=1e-6)
    osb_diff = parse_sinex_osb_pair_diff(bia, obs1="C1C", obs2="C2W")
    assert osb_diff.sat_bias_ns["G01"] == pytest.approx(-7.875, abs=1e-6)


def test_parse_ionex_and_sun_fixed_interpolation(tmp_path: Path) -> None:
    # Minimal 2x2 lat/lon grid (2 epochs) with exact linear values
    inx = tmp_path / "mini.11I"
    inx.write_text(
        "     1.0            IONOSPHERE MAPS     GNSS                IONEX VERSION / TYPE\n"
        "  6371.0                                                    BASE RADIUS         \n"
        "   450.0 450.0   0.0                                        HGT1 / HGT2 / DHGT  \n"
        "    10.0   5.0  -5.0                                        LAT1 / LAT2 / DLAT  \n"
        "     0.0  10.0  10.0                                        LON1 / LON2 / DLON  \n"
        "    -1                                                      EXPONENT            \n"
        "                                                            END OF HEADER       \n"
        "     1                                                      START OF TEC MAP    \n"
        "  2011     3    20     0     0     0                        EPOCH OF CURRENT MAP\n"
        "    10.0   0.0  10.0  10.0 450.0                            LAT/LON1/LON2/DLON/H\n"
        "   200   300\n"
        "     5.0   0.0  10.0  10.0 450.0                            LAT/LON1/LON2/DLON/H\n"
        "   200   300\n"
        "     1                                                      END OF TEC MAP      \n"
        "     2                                                      START OF TEC MAP    \n"
        "  2011     3    20     2     0     0                        EPOCH OF CURRENT MAP\n"
        "    10.0   0.0  10.0  10.0 450.0                            LAT/LON1/LON2/DLON/H\n"
        "   400   500\n"
        "     5.0   0.0  10.0  10.0 450.0                            LAT/LON1/LON2/DLON/H\n"
        "   400   500\n"
        "     2                                                      END OF TEC MAP      \n",
        encoding="ascii",
    )
    grid = parse_ionex(inx)
    v0, _ = grid.interpolate_vtec(7.5, 5.0, "2011-03-20T00:00:00")
    assert v0 == pytest.approx(25.0, abs=1e-6)
    v1, _ = grid.interpolate_vtec(7.5, 5.0, "2011-03-20T02:00:00")
    assert v1 == pytest.approx(45.0, abs=1e-6)


def test_causal_filter_strict_prefix_invariance_and_dcb_sign() -> None:
    """Prove mathematically zero future leakage and exact satellite DCB sign recovery."""
    sat_dsb_ns = -5.0  # DSB(C1, P2) = -5.0 ns
    true_stecs = [20.0 + 0.5 * k for k in range(12)]
    epochs = [f"2011-03-20T00:{k // 2:02d}:{(k % 2) * 30:02d}" for k in range(12)]
    stream = [
        (
            ep,
            {"G01": _synth_obs(stec, sat_dsb_c1_p2_ns=sat_dsb_ns, rx_bias_tecu=0.0)},
            {"G01": (45.0, 120.0)},
        )
        for ep, stec in zip(epochs, true_stecs, strict=True)
    ]

    full_filter = CausalIonoFilter(
        station_id="OSGF",
        station_ecef_m=_OSGF_SYNTH_ECEF,
        sat_dsb_c1_p2_ns={"G01": sat_dsb_ns},
    )
    full_outputs = [full_filter.process_epoch(ep, obs, topo) for ep, obs, topo in stream]

    # Check exact recovery of true STEC after satellite DCB correction
    for k, out_k in enumerate(full_outputs):
        assert len(out_k) == 1
        est = out_k[0]
        assert est.causal_sat_debiased_stec_tecu == pytest.approx(true_stecs[k], abs=1e-6)
        assert est.causal_raw_stec_tecu == pytest.approx(
            true_stecs[k] - sat_dsb_ns * NS_TO_TECU, abs=1e-6
        )

    # Prefix invariance proof: truncating at k=5 produces bit-identical results for 0..5
    prefix_filter = CausalIonoFilter(
        station_id="OSGF",
        station_ecef_m=_OSGF_SYNTH_ECEF,
        sat_dsb_c1_p2_ns={"G01": sat_dsb_ns},
    )
    for k in range(6):
        ep, obs, topo = stream[k]
        p_out = prefix_filter.process_epoch(ep, obs, topo)
        assert p_out == full_outputs[k]


def test_causal_network_diff_tracker_cancels_sat_dcb_and_is_causal() -> None:
    tracker_full = CausalNetworkDiffIonoTracker(datum_station="CGGT", min_pair_epochs=2)
    tracker_pref = CausalNetworkDiffIonoTracker(datum_station="CGGT", min_pair_epochs=2)
    f_cggt = CausalIonoFilter(station_id="CGGT", station_ecef_m=_OSGF_SYNTH_ECEF)
    f_osgf = CausalIonoFilter(station_id="OSGF", station_ecef_m=_OSGF_SYNTH_ECEF)
    f_cggt_p = CausalIonoFilter(station_id="CGGT", station_ecef_m=_OSGF_SYNTH_ECEF)
    f_osgf_p = CausalIonoFilter(station_id="OSGF", station_ecef_m=_OSGF_SYNTH_ECEF)

    full_sd = []
    for k in range(8):
        ep = f"2011-03-20T00:{k // 2:02d}:{(k % 2) * 30:02d}"
        o_c = {"G01": _synth_obs(20.0 + 0.2 * k, sat_dsb_c1_p2_ns=3.5, rx_bias_tecu=4.0)}
        o_o = {"G01": _synth_obs(22.0 + 0.4 * k, sat_dsb_c1_p2_ns=3.5, rx_bias_tecu=-2.0)}
        topo = {"G01": (50.0, 90.0)}
        sd_l, sd_p = tracker_full.process_epoch(
            ep,
            {
                "CGGT": f_cggt.process_epoch(ep, o_c, topo),
                "OSGF": f_osgf.process_epoch(ep, o_o, topo),
            },
        )
        full_sd.append((sd_l, sd_p))
        if k < 4:
            p_l, p_p = tracker_pref.process_epoch(
                ep,
                {
                    "CGGT": f_cggt_p.process_epoch(ep, o_c, topo),
                    "OSGF": f_osgf_p.process_epoch(ep, o_o, topo),
                },
            )
            assert p_l == sd_l
            assert p_p == sd_p
    assert len(full_sd) == 8
