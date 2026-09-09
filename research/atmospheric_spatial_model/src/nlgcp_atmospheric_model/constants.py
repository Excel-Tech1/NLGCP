"""Physical and signal constants for Phase 6 (documented provenance).

Frequencies: IS-GPS-200 (GPS L1 1575.42 MHz, L2 1227.60 MHz).
Light speed: exact SI defining constant.
First-order ionospheric coefficient 40.308e16 m·Hz²/TECU: Hofmann-Wellenhof
et al., *GNSS — Global Navigation Satellite Systems* (2008), ch. on
ionospheric refraction; also Klobuchar (1987) and IS-GPS-200.
"""

from __future__ import annotations

SPEED_OF_LIGHT_M_S = 299_792_458.0
GPS_L1_HZ = 1_575_42e4
GPS_L2_HZ = 1_227_60e4
IONO_COEFF_M_HZ2_PER_TECU = 40.308e16
"""First-order coefficient: slant delay I(m) = 40.308 * TEC / f^2 with TEC in
electrons/m^2, i.e. I(m) = 40.308e16 * TECU / f^2. Gives ~0.162 m per TECU
on GPS L1."""
EARTH_GM_M3_S2 = 3.986005e14
EARTH_ROT_RATE_RAD_S = 7.2921151467e-05
"""Earth rotation rate (IS-GPS-200 Table 20-IV; RTKLIB rtklib.h OMGE).

Must be 7.2921151467e-05 rad/s. A previous value of 7.2921151467e-07
(factor-100 error) corrupted the broadcast-orbit node computation
``omega_k = omega0 + (omegadot - OMEGA_E)*tk - OMEGA_E*toe`` and every
downstream elevation/mapping term. Corrected in the Phase 6/7
scientific-validation sprint; verified against pinned RTKLIB
v2.4.2-p13 ``src/rtklib.h`` (``#define OMGE 7.2921151467E-5``).
"""
GPS_PI = 3.1415926535898  # circle constant; NOT a RINEX unit conversion
