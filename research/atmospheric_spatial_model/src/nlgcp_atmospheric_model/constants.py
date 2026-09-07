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
EARTH_ROT_RATE_RAD_S = 7.2921151467e-07
GPS_PI = 3.1415926535898  # IS-GPS-200 semicircle convention
