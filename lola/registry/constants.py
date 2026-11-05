"""The short list of constants. Every registry number that can be derived is derived
from these, in catalog.py. Trusted; each constant is a premise.

Values are exact rationals (Fraction from decimal text). A constant whose standard gives
a tolerance is an Interval; a defined constant (beta of copper) is a point.

TODO (implementer): fill CONSTANTS with, at least:
  copper, IEC 60028 annealed:   rho20 = 1/58 ohm mm2/m -> 1/58e6 ohm m ; alpha20 = 0.00393 /K
                                volumetric heat capacity 3.45e6 J/(K m3) (IEC 60949)
                                beta = 234.5 K (IEC 60949)
  PVC insulation:               thermal resistivity 5.0 K m/W (IEC 60287-2-1)
                                max conductor temperature 70 degC continuous, 160 degC short circuit
  steel:                        E in [200, 210] GPa, nu = 0.3, density 7850 kg/m3
  aluminium 6061-T6:            E in [68, 70] GPa, nu = 0.33
  ISO 261 coarse pitches:       (d, P) for M6, M8, M10, M12, M16, M20, M24
  ISO 724 basic profile:        d2 = d - 0.649519 P, d3 = d - 1.226869 P (as exact rationals:
                                d2 = d - (3*sqrt(3)/8) P is irrational, so ISO 898-1's
                                rounded coefficients are the sanctioned constants)
  ISO 898-1 property classes:   8.8 (d <= 16): Rm_min 800 MPa, Rp02_min 640 MPa, Sp 580 MPa
                                10.9: Rm_min 1040, Rp02_min 940, Sp 830
  EN 10025-2 S355:              fy >= 355 MPa (t <= 16 mm), fu in [470, 630] MPa
  EN 10219 CHS series:          (D, t) pairs in mm
  IEC 60228 class 2 sizes:      1.5, 2.5, 4, 6, 10, 16 mm2
  IEC 60898-1:                  conventional non-tripping 1.13 In, tripping 1.45 In
  MIL-STD-889C anodic indices:  steel (zinc plated) 1.20 V, aluminium 6061 0.90 V, ...
  free-air convection, clipped direct: h in [5, 10] W/(m2 K)    (judged, owner named)
"""
from __future__ import annotations

from typing import Mapping

from .model import Constant

CONSTANTS: Mapping[str, Constant] = {}
