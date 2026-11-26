"""Experimental observation-based Virtual Reference Station (VRS) engine (Phase 7 D).

Advances Phase 7 beyond geometry-only synthesis to physically signed,
observation-based experimental VRS generation while preserving ALL operational
gates:
- Operational VRS approval remains FORBIDDEN (``VRS_GENERATION = ZERO`` default).
- Every generated observation carries explicit maturity tier
  (``GEOMETRY_ONLY_VRS`` vs ``EXPERIMENTAL_OBSERVATION_VRS``), coordinate
  provenance (``VERIFIED_IGS20`` vs ``PROVISIONAL_OSGOF_EXPERIMENTAL``),
  atmospheric model ID, and anchor-relative float ambiguity policy.
- Twelve explicit quality-control failure gates fail closed with structured
  ``VrsOutcome`` and reason codes.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from statistics import fmean
from typing import Any

from nlgcp_atmospheric_model.combinations import GAMMA_GPS
from nlgcp_atmospheric_model.constants import EARTH_ROT_RATE_RAD_S, SPEED_OF_LIGHT_M_S
from nlgcp_atmospheric_model.dataset_audit import convex_hull_2d, point_in_convex_hull_2d
from nlgcp_atmospheric_model.metrics import prediction_metrics
from nlgcp_atmospheric_model.observations import (
    GPS_L1_WAVELENGTH_M,
    GPS_L2_WAVELENGTH_M,
    StationDataset,
)
from nlgcp_atmospheric_model.satellite_geometry import (
    BroadcastEphemeris,
    broadcast_position,
    elevation_azimuth_deg,
    gps_datetime_to_tow,
    select_ephemeris,
)
from nlgcp_atmospheric_model.spatial import baseline_length_m, ecef_to_local_enu
from nlgcp_atmospheric_model.spatial_estimation import predict_spatial
from nlgcp_atmospheric_model.troposphere import ecef_to_geodetic
from nlgcp_atmospheric_model.troposphere_estimation import (
    slant_tropo_from_ztd,
    unb3m_zenith_delays,
)

EXPERIMENTAL_VRS_VERSION = "phase7-experimental-vrs-v1.0"
EXPERIMENTAL_WATERMARK = (
    "EXPERIMENTAL OBSERVATION-BASED VRS RESEARCH OUTPUT — NOT OPERATIONALLY APPROVED"
)
# WGS84 ellipsoid constants for round-trip coordinate sanity verification
_WGS84_A = 6_378_137.0
_WGS84_F = 1.0 / 298.257223563
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)


class VrsOutcome(StrEnum):
    """Explicit fail-closed outcome states for experimental VRS generation."""

    EXPERIMENTAL_VRS_GENERATED = "EXPERIMENTAL_VRS_GENERATED"
    VRS_GENERATION_BLOCKED = "VRS_GENERATION_BLOCKED"
    INSUFFICIENT_NETWORK_GEOMETRY = "INSUFFICIENT_NETWORK_GEOMETRY"
    INSUFFICIENT_OBSERVATION_COVERAGE = "INSUFFICIENT_OBSERVATION_COVERAGE"
    ATMOSPHERIC_MODEL_UNAVAILABLE = "ATMOSPHERIC_MODEL_UNAVAILABLE"
    INVALID_STATION_COORDINATES = "INVALID_STATION_COORDINATES"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class VrsMaturity(StrEnum):
    """Strict separation between geometry-only, experimental, and operational VRS."""

    GEOMETRY_ONLY_VRS = "GEOMETRY_ONLY_VRS"
    EXPERIMENTAL_OBSERVATION_VRS = "EXPERIMENTAL_OBSERVATION_VRS"
    EXPERIMENTALLY_VALIDATED_VRS = "EXPERIMENTALLY_VALIDATED_VRS"
    OPERATIONALLY_APPROVED_VRS = "OPERATIONALLY_APPROVED_VRS"


@dataclass(frozen=True, slots=True)
class VrsCoordinateRecord:
    """Validated virtual or reference station coordinate with explicit provenance."""

    station_id: str
    ecef_xyz_m: tuple[float, float, float]
    latitude_deg: float
    longitude_deg: float
    ellipsoidal_height_m: float
    reference_frame: str
    coordinate_epoch: str
    provenance_status: str  # e.g. VERIFIED_IGS20 | PROVISIONAL_OSGOF_EXPERIMENTAL
    uncertainty_m: float | None = None
    roundtrip_error_m: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ecef_xyz_m"] = list(self.ecef_xyz_m)
        return payload


@dataclass(frozen=True, slots=True)
class ExperimentalVrsObs:
    """One dual-frequency GPS observation synthesized at the virtual station."""

    epoch_iso: str
    satellite_id: str
    anchor_station: str
    elevation_deg: float
    azimuth_deg: float
    geometric_delta_m: float
    satellite_clock_delta_m: float
    tropo_correction_m: float
    iono_l1_correction_m: float
    c1_m: float
    p2_m: float
    l1_cycles: float
    l2_cycles: float
    s1_dbhz: float | None
    s2_dbhz: float | None
    source_l1_lli: int
    source_l2_lli: int
    ambiguity_policy: str = "ANCHOR_RELATIVE_FLOAT"


@dataclass(frozen=True, slots=True)
class ExperimentalVrsResult:
    """Complete outcome of an experimental VRS generation run."""

    experiment_id: str
    virtual_station_id: str
    outcome: VrsOutcome
    maturity: VrsMaturity
    operational_approved: bool
    reason_codes: tuple[str, ...]
    target_coordinate: VrsCoordinateRecord | None
    anchor_station: str | None
    reference_stations: tuple[str, ...]
    inside_convex_hull: bool
    atmospheric_model: str
    spatial_model: str
    tropo_source: str
    observations: tuple[ExperimentalVrsObs, ...] = ()
    exclusions: dict[str, int] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    watermark: str = EXPERIMENTAL_WATERMARK

    def summary_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "virtual_station_id": self.virtual_station_id,
            "outcome": str(self.outcome),
            "maturity": str(self.maturity),
            "operational_approved": self.operational_approved,
            "reason_codes": list(self.reason_codes),
            "target_coordinate": (
                self.target_coordinate.as_dict() if self.target_coordinate else None
            ),
            "anchor_station": self.anchor_station,
            "reference_stations": list(self.reference_stations),
            "inside_convex_hull": self.inside_convex_hull,
            "atmospheric_model": self.atmospheric_model,
            "spatial_model": self.spatial_model,
            "tropo_source": self.tropo_source,
            "observation_count": len(self.observations),
            "epoch_count": len({o.epoch_iso for o in self.observations}),
            "satellite_count": len({o.satellite_id for o in self.observations}),
            "exclusions": dict(self.exclusions),
            "provenance": dict(self.provenance),
            "watermark": self.watermark,
        }


def geodetic_to_ecef(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, float, float]:
    """WGS84 geodetic (deg, deg, ellipsoidal m) to ECEF (m)."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_l, cos_l = math.sin(lat), math.cos(lat)
    n = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_l * sin_l)
    x = (n + height_m) * cos_l * math.cos(lon)
    y = (n + height_m) * cos_l * math.sin(lon)
    z = (n * (1.0 - _WGS84_E2) + height_m) * sin_l
    return x, y, z


def validate_vrs_coordinate(
    *,
    station_id: str,
    ecef_xyz_m: tuple[float, float, float],
    reference_frame: str,
    coordinate_epoch: str,
    provenance_status: str,
    uncertainty_m: float | None = None,
) -> tuple[VrsCoordinateRecord | None, str | None]:
    """Validate ECEF coordinate finiteness, Earth-surface radius, and WGS84 round-trip."""
    if not station_id or not reference_frame or not coordinate_epoch or not provenance_status:
        return None, "missing coordinate provenance metadata"
    if len(ecef_xyz_m) != 3 or not all(math.isfinite(v) for v in ecef_xyz_m):
        return None, "non-finite ECEF coordinate"
    radius = math.hypot(*ecef_xyz_m)
    if not (6_300_000.0 <= radius <= 6_450_000.0):
        return None, f"ECEF radius {radius:.1f} m outside Earth surface bounds [6300, 6450] km"
    lat_rad, lon_rad, h_m = ecef_to_geodetic(ecef_xyz_m)
    if not (-500.0 <= h_m <= 10_000.0):
        return None, f"ellipsoidal height {h_m:.1f} m outside terrestrial bounds [-500, 10000] m"
    lat_deg = math.degrees(lat_rad)
    lon_deg = math.degrees(lon_rad)
    rt_xyz = geodetic_to_ecef(lat_deg, lon_deg, h_m)
    rt_err = math.dist(ecef_xyz_m, rt_xyz)
    if rt_err > 1e-4:
        return None, f"ECEF/geodetic round-trip error {rt_err:.6f} m exceeds 0.1 mm"
    return (
        VrsCoordinateRecord(
            station_id=station_id,
            ecef_xyz_m=ecef_xyz_m,
            latitude_deg=lat_deg,
            longitude_deg=lon_deg,
            ellipsoidal_height_m=h_m,
            reference_frame=reference_frame,
            coordinate_epoch=coordinate_epoch,
            provenance_status=provenance_status,
            uncertainty_m=uncertainty_m,
            roundtrip_error_m=rt_err,
        ),
        None,
    )


def _sat_pos_and_range_at_rx(
    eph: BroadcastEphemeris,
    week: int,
    tow_rx: float,
    rx_ecef: tuple[float, float, float],
    approx_pr_m: float,
) -> tuple[float, float, float, float]:
    """Geometric range (m) with light-time & Sagnac Earth-rotation, plus sv clock (m)."""
    tau = approx_pr_m / SPEED_OF_LIGHT_M_S
    t_tx = tow_rx - tau
    sat_pos = broadcast_position(eph, week, t_tx)
    # 1-step light-time + Sagnac Earth-rotation refinement
    for _ in range(2):
        angle = EARTH_ROT_RATE_RAD_S * tau
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        sx = cos_a * sat_pos[0] + sin_a * sat_pos[1]
        sy = -sin_a * sat_pos[0] + cos_a * sat_pos[1]
        sz = sat_pos[2]
        rng = math.dist(rx_ecef, (sx, sy, sz))
        tau = rng / SPEED_OF_LIGHT_M_S
        t_tx = tow_rx - tau
        sat_pos = broadcast_position(eph, week, t_tx)
    angle = EARTH_ROT_RATE_RAD_S * tau
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    sx = cos_a * sat_pos[0] + sin_a * sat_pos[1]
    sy = -sin_a * sat_pos[0] + cos_a * sat_pos[1]
    sz = sat_pos[2]
    rng = math.dist(rx_ecef, (sx, sy, sz))
    el_deg, az_deg = elevation_azimuth_deg(rx_ecef, (sx, sy, sz))
    dt_clk = t_tx - eph.toc_tow_s + (week - eph.toc_week) * 604_800.0
    if dt_clk > 302_400.0:
        dt_clk -= 604_800.0
    elif dt_clk < -302_400.0:
        dt_clk += 604_800.0
    sv_clk_m = SPEED_OF_LIGHT_M_S * (eph.af0_s + eph.af1_s_s * dt_clk + eph.af2_s_s2 * dt_clk**2)
    return rng, sv_clk_m, el_deg, az_deg


def generate_experimental_vrs(
    *,
    experiment_id: str,
    target_station_id: str,
    target_ecef_m: tuple[float, float, float],
    reference_coords: dict[str, tuple[float, float, float]],
    reference_datasets: dict[str, StationDataset],
    nav_records: dict[str, list[BroadcastEphemeris]],
    doy: int,
    reference_frame: str,
    coordinate_epoch: str,
    coordinate_provenance: str,
    spatial_model: str = "idw2",
    iono_field_by_key: dict[tuple[str, str, str], float] | None = None,
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] | None = None,
    target_ipp_by_epoch_sat: dict[tuple[str, str], tuple[float, float]] | None = None,
    ztd_by_station_epoch: dict[tuple[str, str], tuple[float, float]] | None = None,
    tropo_mode: str = "unb3m",
    requested_maturity: VrsMaturity = VrsMaturity.EXPERIMENTAL_OBSERVATION_VRS,
    require_interior_hull: bool = True,
    min_elevation_deg: float = 15.0,
    max_correction_m: float = 50.0,
    max_epochs: int | None = None,
    supported_message_families: tuple[str, ...] = ("REFERENCE_STATION_1005", "MSM4_GPS_1074"),
) -> ExperimentalVrsResult:
    """Execute fail-closed observation-based experimental VRS generation.

    Synthesizes dual-frequency GPS (C1, P2, L1, L2) virtual observations from
    the nearest reference anchor using exact geometric range translation plus
    physically signed differential tropospheric (Niell) and spatially interpolated
    ionospheric corrections. Never approves operational use.
    """
    virtual_id = f"VRS_EXP_{experiment_id}"
    refs_sorted = tuple(sorted(reference_coords))

    def _blocked(
        outcome: VrsOutcome,
        reasons: tuple[str, ...],
        *,
        target_rec: VrsCoordinateRecord | None = None,
        anchor: str | None = None,
        inside: bool = False,
    ) -> ExperimentalVrsResult:
        return ExperimentalVrsResult(
            experiment_id=experiment_id,
            virtual_station_id=virtual_id,
            outcome=outcome,
            maturity=VrsMaturity.GEOMETRY_ONLY_VRS
            if spatial_model == "zero"
            else VrsMaturity.EXPERIMENTAL_OBSERVATION_VRS,
            operational_approved=False,
            reason_codes=reasons,
            target_coordinate=target_rec,
            anchor_station=anchor,
            reference_stations=refs_sorted,
            inside_convex_hull=inside,
            atmospheric_model=f"iono:{spatial_model}|tropo:{tropo_mode}",
            spatial_model=spatial_model,
            tropo_source=tropo_mode,
            provenance={
                "algorithm_version": EXPERIMENTAL_VRS_VERSION,
                "coordinate_provenance": coordinate_provenance,
            },
        )

    # Gate 1: Operational promotion is strictly forbidden.
    if requested_maturity == VrsMaturity.OPERATIONALLY_APPROVED_VRS:
        return _blocked(
            VrsOutcome.VRS_GENERATION_BLOCKED,
            ("OPERATIONAL_VRS_APPROVAL_FORBIDDEN",),
        )

    # Gate 2: Supported GNSS message family check.
    allowed_families = {"REFERENCE_STATION_1005", "MSM4_GPS_1074", "MSM4_GLONASS_1084"}
    if not supported_message_families or any(
        f not in allowed_families for f in supported_message_families
    ):
        return _blocked(
            VrsOutcome.VALIDATION_FAILED,
            ("UNSUPPORTED_GNSS_MESSAGE_FAMILY",),
        )

    # Gate 3: Target & reference coordinate validation.
    target_rec, coord_err = validate_vrs_coordinate(
        station_id=target_station_id,
        ecef_xyz_m=target_ecef_m,
        reference_frame=reference_frame,
        coordinate_epoch=coordinate_epoch,
        provenance_status=coordinate_provenance,
    )
    if target_rec is None:
        return _blocked(
            VrsOutcome.INVALID_STATION_COORDINATES,
            (f"INVALID_TARGET_COORDINATE:{coord_err}",),
        )

    if target_station_id in reference_coords or target_station_id in reference_datasets:
        return _blocked(
            VrsOutcome.VRS_GENERATION_BLOCKED,
            ("HELD_OUT_TARGET_LEAKAGE_IN_REFERENCES",),
            target_rec=target_rec,
        )

    for r_id, r_xyz in reference_coords.items():
        r_rec, r_err = validate_vrs_coordinate(
            station_id=r_id,
            ecef_xyz_m=r_xyz,
            reference_frame=reference_frame,
            coordinate_epoch=coordinate_epoch,
            provenance_status=coordinate_provenance,
        )
        if r_rec is None:
            return _blocked(
                VrsOutcome.INVALID_STATION_COORDINATES,
                (f"INVALID_REFERENCE_COORDINATE:{r_id}:{r_err}",),
                target_rec=target_rec,
            )

    # Gate 4: Minimum reference count & 2D ENU convex hull check.
    if len(reference_coords) < 3 or set(reference_coords) != set(reference_datasets):
        return _blocked(
            VrsOutcome.INSUFFICIENT_NETWORK_GEOMETRY,
            ("INSUFFICIENT_OR_MISMATCHED_REFERENCES_MIN_3_REQUIRED",),
            target_rec=target_rec,
        )

    centroid = (
        sum(p[0] for p in reference_coords.values()) / len(reference_coords),
        sum(p[1] for p in reference_coords.values()) / len(reference_coords),
        sum(p[2] for p in reference_coords.values()) / len(reference_coords),
    )
    ref_2d = [ecef_to_local_enu(reference_coords[r], centroid)[:2] for r in refs_sorted]
    tgt_2d = ecef_to_local_enu(target_ecef_m, centroid)[:2]
    inside_hull = point_in_convex_hull_2d(tgt_2d, convex_hull_2d(ref_2d))
    anchor = min(refs_sorted, key=lambda r: baseline_length_m(reference_coords[r], target_ecef_m))

    if require_interior_hull and not inside_hull:
        return _blocked(
            VrsOutcome.INSUFFICIENT_NETWORK_GEOMETRY,
            ("TARGET_OUTSIDE_REFERENCE_CONVEX_HULL_EXTRAPOLATION",),
            target_rec=target_rec,
            anchor=anchor,
            inside=False,
        )

    # Gate 5: Simultaneous observation & dual-frequency availability.
    common_ep = sorted(set.intersection(*(set(ds.data) for ds in reference_datasets.values())))
    if not common_ep:
        return _blocked(
            VrsOutcome.INSUFFICIENT_OBSERVATION_COVERAGE,
            ("NO_SIMULTANEOUS_EPOCHS_ACROSS_REFERENCES",),
            target_rec=target_rec,
            anchor=anchor,
            inside=inside_hull,
        )
    if max_epochs is not None and max_epochs > 0:
        common_ep = common_ep[:max_epochs]

    anchor_obs_types = set(reference_datasets[anchor].header.obs_types)
    if not ({"L1", "L2", "P2"} <= anchor_obs_types and ({"C1", "P1"} & anchor_obs_types)):
        return _blocked(
            VrsOutcome.INSUFFICIENT_OBSERVATION_COVERAGE,
            ("ANCHOR_MISSING_DUAL_FREQUENCY_GPS_OBSERVABLES",),
            target_rec=target_rec,
            anchor=anchor,
            inside=inside_hull,
        )

    # Gate 6: Atmospheric model availability when non-zero ionospheric model requested.
    if spatial_model != "zero" and (iono_field_by_key is None or not iono_field_by_key):
        return _blocked(
            VrsOutcome.ATMOSPHERIC_MODEL_UNAVAILABLE,
            ("IONOSPHERIC_FIELD_UNAVAILABLE_FOR_NONZERO_MODEL",),
            target_rec=target_rec,
            anchor=anchor,
            inside=inside_hull,
        )
    if tropo_mode == "network_ztd" and (ztd_by_station_epoch is None or not ztd_by_station_epoch):
        return _blocked(
            VrsOutcome.ATMOSPHERIC_MODEL_UNAVAILABLE,
            ("NETWORK_ZTD_UNAVAILABLE_FOR_TROPO_MODE",),
            target_rec=target_rec,
            anchor=anchor,
            inside=inside_hull,
        )

    # Precompute static UNB3m zenith terms for target & anchor
    unb_target = unb3m_zenith_delays(target_ecef_m, doy, station_id=target_station_id)
    unb_anchor = unb3m_zenith_delays(reference_coords[anchor], doy, station_id=anchor)

    synth: list[ExperimentalVrsObs] = []
    exclusions: Counter[str] = Counter()
    anchor_ds = reference_datasets[anchor]

    for ep in common_ep:
        moment = datetime.fromisoformat(ep)
        week, tow = gps_datetime_to_tow(moment)
        sats_anchor = anchor_ds.data.get(ep, {})
        for sat in sorted(sats_anchor):
            if not sat.startswith("G"):
                exclusions["non_gps_skipped"] += 1
                continue
            obs = sats_anchor[sat]
            c1 = obs.values.get("C1")
            if c1 is None:
                c1 = obs.values.get("P1")
            p2 = obs.values.get("P2")
            l1 = obs.values.get("L1")
            l2 = obs.values.get("L2")
            if c1 is None or p2 is None or l1 is None or l2 is None or c1 <= 0.0 or p2 <= 0.0:
                exclusions["missing_dual_freq_at_anchor"] += 1
                continue
            l1_lli = obs.lli.get("L1") or 0
            l2_lli = obs.lli.get("L2") or 0
            if (l1_lli & 2) or (l2_lli & 2):
                exclusions["half_cycle_ambiguity_excluded"] += 1
                continue

            eph = select_ephemeris(nav_records.get(sat, []), week, tow)
            if eph is None:
                exclusions["missing_or_unhealthy_ephemeris"] += 1
                continue

            rng_anc, clk_anc, el_anc, _az_anc = _sat_pos_and_range_at_rx(
                eph, week, tow, reference_coords[anchor], c1
            )
            rng_tgt, clk_tgt, el_tgt, az_tgt = _sat_pos_and_range_at_rx(
                eph, week, tow, target_ecef_m, c1
            )
            if min(el_anc, el_tgt) < min_elevation_deg:
                exclusions["below_elevation_mask"] += 1
                continue

            delta_rho = rng_tgt - rng_anc
            delta_sv_clk = -(clk_tgt - clk_anc)

            # Separated Tropospheric Differential Slant Correction (target - anchor)
            if tropo_mode == "zero":
                delta_tropo = 0.0
            elif tropo_mode == "network_ztd" and ztd_by_station_epoch is not None:
                ref_zwd_triples = [
                    (
                        r,
                        reference_coords[r],
                        ztd_by_station_epoch[(r, ep)][1]
                        if (r, ep) in ztd_by_station_epoch
                        else None,
                    )
                    for r in refs_sorted
                ]
                zwd_pred = predict_spatial(
                    model_name="idw2" if spatial_model in ("zero", "ipp_idw2") else spatial_model,
                    epoch_iso=ep,
                    satellite_id="ZENITH",
                    target_station=target_station_id,
                    target_xyz=target_ecef_m,
                    references=ref_zwd_triples,
                )
                anc_z = ztd_by_station_epoch.get((anchor, ep))
                if zwd_pred.predicted_m is None or anc_z is None:
                    exclusions["missing_network_ztd_at_epoch"] += 1
                    continue
                t_tgt = slant_tropo_from_ztd(
                    station_ecef_m=target_ecef_m,
                    elevation_deg=el_tgt,
                    doy=doy,
                    zhd_m=unb_target.zhd_m,
                    zwd_m=zwd_pred.predicted_m,
                )
                t_anc = slant_tropo_from_ztd(
                    station_ecef_m=reference_coords[anchor],
                    elevation_deg=el_anc,
                    doy=doy,
                    zhd_m=anc_z[0],
                    zwd_m=anc_z[1],
                )
                delta_tropo = t_tgt - t_anc
            else:
                # Default UNB3m climatological differential slant troposphere (target - anchor)
                t_tgt = slant_tropo_from_ztd(
                    station_ecef_m=target_ecef_m,
                    elevation_deg=el_tgt,
                    doy=doy,
                    zhd_m=unb_target.zhd_m,
                    zwd_m=unb_target.zwd_m,
                )
                t_anc = slant_tropo_from_ztd(
                    station_ecef_m=reference_coords[anchor],
                    elevation_deg=el_anc,
                    doy=doy,
                    zhd_m=unb_anchor.zhd_m,
                    zwd_m=unb_anchor.zwd_m,
                )
                delta_tropo = t_tgt - t_anc

            # Separated Ionospheric Differential L1 Slant Correction (target - anchor)
            if spatial_model == "zero" or iono_field_by_key is None:
                delta_iono_l1 = 0.0
            else:
                anc_val = iono_field_by_key.get((ep, sat, anchor))
                if anc_val is None:
                    exclusions["missing_anchor_iono_estimate"] += 1
                    continue
                ref_triples = [
                    (
                        r,
                        reference_coords[r],
                        (iono_field_by_key[(ep, sat, r)] - anc_val)
                        if (ep, sat, r) in iono_field_by_key
                        else None,
                    )
                    for r in refs_sorted
                ]
                ref_ipps = (
                    {
                        r: ipp_by_key[(ep, sat, r)]
                        for r in refs_sorted
                        if (ep, sat, r) in ipp_by_key
                    }
                    if ipp_by_key
                    else None
                )
                tgt_ipp = (
                    target_ipp_by_epoch_sat.get((ep, sat)) if target_ipp_by_epoch_sat else None
                )
                pred = predict_spatial(
                    model_name=spatial_model,
                    epoch_iso=ep,
                    satellite_id=sat,
                    target_station=target_station_id,
                    target_xyz=target_ecef_m,
                    references=ref_triples,
                    target_ipp=tgt_ipp,
                    reference_ipps=ref_ipps,
                )
                if pred.predicted_m is None or not math.isfinite(pred.predicted_m):
                    exclusions["iono_spatial_prediction_unavailable"] += 1
                    continue
                delta_iono_l1 = pred.predicted_m

            if abs(delta_iono_l1) > max_correction_m or abs(delta_tropo) > max_correction_m:
                exclusions["excessive_atmospheric_correction_rejected"] += 1
                continue

            # Physically signed observation synthesis (code delayed +I, phase advanced -I)
            geom_and_tropo = delta_rho + delta_sv_clk + delta_tropo
            c1_vrs = c1 + geom_and_tropo + delta_iono_l1
            p2_vrs = p2 + geom_and_tropo + GAMMA_GPS * delta_iono_l1
            l1_vrs = l1 + (geom_and_tropo - delta_iono_l1) / GPS_L1_WAVELENGTH_M
            l2_vrs = l2 + (geom_and_tropo - GAMMA_GPS * delta_iono_l1) / GPS_L2_WAVELENGTH_M

            synth.append(
                ExperimentalVrsObs(
                    epoch_iso=ep,
                    satellite_id=sat,
                    anchor_station=anchor,
                    elevation_deg=el_tgt,
                    azimuth_deg=az_tgt,
                    geometric_delta_m=delta_rho,
                    satellite_clock_delta_m=delta_sv_clk,
                    tropo_correction_m=delta_tropo,
                    iono_l1_correction_m=delta_iono_l1,
                    c1_m=c1_vrs,
                    p2_m=p2_vrs,
                    l1_cycles=l1_vrs,
                    l2_cycles=l2_vrs,
                    s1_dbhz=obs.values.get("S1"),
                    s2_dbhz=obs.values.get("S2"),
                    source_l1_lli=l1_lli,
                    source_l2_lli=l2_lli,
                )
            )

    if not synth:
        return _blocked(
            VrsOutcome.INSUFFICIENT_OBSERVATION_COVERAGE,
            ("NO_VIRTUAL_OBSERVATIONS_PASSED_QUALITY_GATES",),
            target_rec=target_rec,
            anchor=anchor,
            inside=inside_hull,
        )

    maturity = (
        VrsMaturity.GEOMETRY_ONLY_VRS
        if (spatial_model == "zero" and tropo_mode == "zero")
        else VrsMaturity.EXPERIMENTAL_OBSERVATION_VRS
    )
    reasons = () if inside_hull else ("EXPERIMENTAL_EXTRAPOLATION_WARNING",)
    return ExperimentalVrsResult(
        experiment_id=experiment_id,
        virtual_station_id=virtual_id,
        outcome=VrsOutcome.EXPERIMENTAL_VRS_GENERATED,
        maturity=maturity,
        operational_approved=False,
        reason_codes=reasons,
        target_coordinate=target_rec,
        anchor_station=anchor,
        reference_stations=refs_sorted,
        inside_convex_hull=inside_hull,
        atmospheric_model=f"iono:{spatial_model}|tropo:{tropo_mode}",
        spatial_model=spatial_model,
        tropo_source=tropo_mode,
        observations=tuple(synth),
        exclusions=dict(sorted(exclusions.items())),
        provenance={
            "algorithm_version": EXPERIMENTAL_VRS_VERSION,
            "coordinate_provenance": coordinate_provenance,
            "reference_frame": reference_frame,
            "coordinate_epoch": coordinate_epoch,
            "anchor_baseline_km": round(
                baseline_length_m(reference_coords[anchor], target_ecef_m) / 1000.0, 3
            ),
            "held_out_target_observations_used_in_synthesis": False,
            "ambiguity_note": (
                "Carrier phases inherit anchor-relative float ambiguity; "
                "no integer ambiguity resolution is claimed."
            ),
        },
    )


def validate_experimental_vrs_against_target(
    vrs: ExperimentalVrsResult,
    target_dataset: StationDataset,
    *,
    effective_interval_s: float,
) -> dict[str, Any]:
    """Compare synthesized VRS observables against withheld real target observations."""
    if vrs.outcome != VrsOutcome.EXPERIMENTAL_VRS_GENERATED or not vrs.observations:
        return {"status": "BLOCKED", "reason": f"vrs outcome={vrs.outcome}"}

    # Group by (code, epoch) -> sat -> (diff_m, lli)
    paired: dict[tuple[str, str], dict[str, tuple[float, int]]] = defaultdict(dict)
    gf_diff_by_sat: dict[str, list[tuple[str, float]]] = defaultdict(list)
    matched = 0

    for obs in vrs.observations:
        real = target_dataset.data.get(obs.epoch_iso, {}).get(obs.satellite_id)
        if real is None:
            continue
        r_c1 = real.values.get("C1") if real.values.get("C1") is not None else real.values.get("P1")
        r_p2 = real.values.get("P2")
        r_l1 = real.values.get("L1")
        r_l2 = real.values.get("L2")
        if r_c1 is not None:
            paired[("C1", obs.epoch_iso)][obs.satellite_id] = (obs.c1_m - r_c1, 0)
        if r_p2 is not None:
            paired[("P2", obs.epoch_iso)][obs.satellite_id] = (obs.p2_m - r_p2, 0)
        if r_l1 is not None and not ((real.lli.get("L1") or 0) & 2):
            paired[("L1", obs.epoch_iso)][obs.satellite_id] = (
                (obs.l1_cycles - r_l1) * GPS_L1_WAVELENGTH_M,
                obs.source_l1_lli | (real.lli.get("L1") or 0),
            )
        if r_l2 is not None and not ((real.lli.get("L2") or 0) & 2):
            paired[("L2", obs.epoch_iso)][obs.satellite_id] = (
                (obs.l2_cycles - r_l2) * GPS_L2_WAVELENGTH_M,
                obs.source_l2_lli | (real.lli.get("L2") or 0),
            )
        if r_l1 is not None and r_l2 is not None:
            matched += 1
            gf_vrs = obs.l1_cycles * GPS_L1_WAVELENGTH_M - obs.l2_cycles * GPS_L2_WAVELENGTH_M
            gf_real = r_l1 * GPS_L1_WAVELENGTH_M - r_l2 * GPS_L2_WAVELENGTH_M
            gf_diff_by_sat[obs.satellite_id].append((obs.epoch_iso, gf_vrs - gf_real))

    metrics_by_code: dict[str, Any] = {}
    for code in ("C1", "P2", "L1", "L2"):
        epochs = sorted(e for c, e in paired if c == code)
        vals: list[float] = []
        prev_ep: str | None = None
        for ep in epochs:
            cur = paired[(code, ep)]
            if code in ("C1", "P2"):
                if len(cur) >= 2:
                    mean_bias = fmean(v[0] for v in cur.values())
                    vals.extend(v[0] - mean_bias for v in cur.values())
            elif (
                prev_ep is not None
                and abs(
                    (datetime.fromisoformat(ep) - datetime.fromisoformat(prev_ep)).total_seconds()
                    - effective_interval_s
                )
                <= 1.0
            ):
                old = paired[(code, prev_ep)]
                common = sorted(
                    s
                    for s in set(cur) & set(old)
                    if not (cur[s][1] & 1) and not (old[s][1] & 1)
                )
                if len(common) >= 2:
                    piv = common[0]
                    dpiv = cur[piv][0] - old[piv][0]
                    for s in common[1:]:
                        vals.append((cur[s][0] - old[s][0]) - dpiv)
            prev_ep = ep
        metrics_by_code[code] = {
            **prediction_metrics(vals),
            "method": (
                "CODE_SD_EPOCH_MEAN_REMOVED"
                if code in ("C1", "P2")
                else "PHASE_TIME_DIFFERENCED_DOUBLE_DIFFERENCE"
            ),
        }

    # Geometry-free time-differenced residual (directly isolates ionospheric tracking error)
    gf_td_vals: list[float] = []
    for _sat, seq in gf_diff_by_sat.items():
        seq.sort()
        for idx in range(1, len(seq)):
            dt = (
                datetime.fromisoformat(seq[idx][0]) - datetime.fromisoformat(seq[idx - 1][0])
            ).total_seconds()
            if abs(dt - effective_interval_s) <= 1.0:
                delta = seq[idx][1] - seq[idx - 1][1]
                if abs(delta) < 1.0:  # exclude raw target cycle slips
                    gf_td_vals.append(delta)

    return {
        "status": "COMPLETE" if matched > 0 else "BLOCKED",
        "experiment_id": vrs.experiment_id,
        "atmospheric_model": vrs.atmospheric_model,
        "matched_dual_freq_obs": matched,
        "metrics_by_code": metrics_by_code,
        "gf_time_differenced_m": prediction_metrics(gf_td_vals),
        "note": (
            "Held-out observation residuals are diagnostic physical checks, not RTK FIX "
            "positioning accuracy claims."
        ),
    }
