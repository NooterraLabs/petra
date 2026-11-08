"""Limit-state equations of AISC 360-22 and the AISC Manual, as pure functions of exact inputs.

Each function returns a nominal strength (kips or kip-in.). The resistance and safety factors
sit beside the clause that sets them in FACTORS, and a Check pairs a nominal strength with its
factor, clause and demand.
"""

import math
from dataclasses import dataclass
from fractions import Fraction as F

from twin.data import E

FACTORS = {
    "J2.4": (F(3, 4), F(2)),
    "J3.6": (F(3, 4), F(2)),  # bolt tension and shear, J3.7's phi and Omega
    "J3.11": (F(3, 4), F(2)),
    "J4.1a": (F(9, 10), F(167, 100)),
    "J4.1b": (F(3, 4), F(2)),
    "J4.2a": (F(1), F(3, 2)),
    "J4.2b": (F(3, 4), F(2)),
    "J4.3": (F(3, 4), F(2)),
    "J4.4": (F(9, 10), F(167, 100)),
    "J10.2": (F(1), F(3, 2)),
    "J10.3": (F(3, 4), F(2)),
    "flexure": (F(9, 10), F(167, 100)),  # F1(1) and the Manual's flexural yielding, phi_b, Omega_b
    "flexural_rupture": (F(3, 4), F(2)),  # Manual Part 9 and Part 15, Eqs. 9-8 and 15-3
    "slip_std": (F(1), F(3, 2)),  # J3.9(a)
    "slip_ovs": (F(85, 100), F(176, 100)),  # J3.9(b)
    "slip_lsl": (F(7, 10), F(214, 100)),  # J3.9(c)
    "ratio": (F(1), F(1)),
}


def sqrt(x):
    return F(math.sqrt(x))


@dataclass(frozen=True)
class Check:
    name: str
    mode: str
    element: str
    clause: str
    nominal: F
    factor: str
    demand: F
    unit: str = "kip"
    note: str = ""

    def available(self, lrfd):
        phi, omega = FACTORS[self.factor]
        return self.nominal * phi if lrfd else self.nominal / omega


# Bolts, J3.7 and J3.11a


def bolt_area(d):
    return F(math.pi) * d * d / 4


def bolt_shear(fnv, d, planes=1):
    """J3.7, Eq. J3-1 with Fn = Fnv and Ab the nominal body area."""
    return fnv * bolt_area(d) * planes


def bolt_tension(fnt, d):
    """J3.7, Eq. J3-1 with Fn = Fnt."""
    return fnt * bolt_area(d)


def bearing(d, t, fu, deformation_considered=True, long_slot_across=False):
    """J3.11a(1)(a) Eqs. J3-6a and J3-6b, or J3.11a(2)(a) Eq. J3-6e for a long slot across the force."""
    if long_slot_across:
        return 2 * d * t * fu
    return (F(12, 5) if deformation_considered else 3) * d * t * fu


def tearout(lc, t, fu, deformation_considered=True, long_slot_across=False):
    """J3.11a(1)(b) Eqs. J3-6c and J3-6d, or J3.11a(2)(b) Eq. J3-6f."""
    if long_slot_across:
        return lc * t * fu
    return (F(6, 5) if deformation_considered else F(3, 2)) * lc * t * fu


def slip(mu, tb, planes, fillers):
    """J3.9, Eq. J3-4, Du = 1.13 and hf from the fillers."""
    hf = F(85, 100) if fillers == "two" else F(1)
    return mu * F(113, 100) * hf * tb * planes


# Elements, J4


def tension_yield(fy, ag):
    return fy * ag


def tension_rupture(fu, ae):
    return fu * ae


def shear_yield(fy, agv):
    return F(3, 5) * fy * agv


def shear_rupture(fu, anv):
    return F(3, 5) * fu * anv


def block_shear(fy, fu, agv, anv, ant, ubs=F(1)):
    """J4.3, Eq. J4-5."""
    return min(F(3, 5) * fu * anv + ubs * fu * ant, F(3, 5) * fy * agv + ubs * fu * ant)


# Welds, J2.4


def fillet_weld(fexx, w, length, kds=F(1)):
    """J2.4 Eq. J2-4 with Fnw = 0.60 FEXX from Table J2.5 and the throat w / sqrt(2)."""
    return F(3, 5) * fexx * (w * F(math.sqrt(2)) / 2) * length * kds


# Flexure of plates and stems


def plastic_modulus(t, depth):
    return t * depth * depth / 4


def net_plastic_modulus(t, depth, hole_width, offsets):
    """Z of a rectangle about its mid-depth less its holes, each centred at an offset from the
    mid-depth (Manual Eq. 9-8). A hole removes t times the integral of |y| over its width, which
    is hole_width |y| clear of the axis and y^2 + hole_width^2 / 4 where it spans the axis."""
    def removed(y):
        y = abs(y)
        return hole_width * y if y >= hole_width / 2 else y * y + hole_width * hole_width / 4

    return t * depth * depth / 4 - t * sum(removed(y) for y in offsets)


# Concentrated forces on the beam web, J10.2 and J10.3, at a beam end


def web_local_yielding(fy, tw, k, lb, d, distance=F(0)):
    """J10.2: Eq. J10-3 within d of the member end, Eq. J10-2 otherwise."""
    if distance > d:
        return fy * tw * (5 * k + lb)
    return fy * tw * (F(5, 2) * k + lb)


def web_crippling(fy, tw, tf, lb, d, distance=F(0), qf=F(1)):
    """J10.3: Eq. J10-4 at least d/2 from the end, Eqs. J10-5a and J10-5b nearer the end."""
    root = sqrt(E * fy * tf / tw)
    ratio = (tw / tf) ** 3
    slender = sqrt(ratio)
    if distance >= d / 2:
        return F(4, 5) * tw * tw * (1 + 3 * (lb / d) * slender) * root * qf
    if lb / d <= F(1, 5):
        return F(2, 5) * tw * tw * (1 + 3 * (lb / d) * slender) * root * qf
    return F(2, 5) * tw * tw * (1 + (4 * lb / d - F(1, 5)) * slender) * root * qf
