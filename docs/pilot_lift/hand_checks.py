"""The lift pilot's hand checks (docs/pilot_lift/hand_checks.md), independent of Petra.

    python docs/pilot_lift/hand_checks.py

Every number comes from AISC 360-22 and the Manual's methods, written out here. Nothing is
imported from petra/. Shape dimensions are from the AISC Shapes Database v16.0. The
instantaneous-centre solvers use the Manual's load-deformation relations:

    bolts (Part 7):  R = Rult (1 - exp(-10 D))^0.55, D_max = 0.34 in
    welds (Part 8):  R = Rult (1 + 0.5 sin^1.5 th) [p (1.9 - 0.9 p)]^0.3, p = D / Dm,
                     Dm = 0.209 (th + 2)^-0.32 w, Du = min(1.087 (th + 6)^-0.65 w, 0.17 w)

Each solver is checked against a Manual value the Companion quotes: Table 7-6 gives
C = 3.54 for one column of four bolts at 3 in with e = 1.5 in (Example II.A-17), and
Table 8-4 gives C = 3.61 for k = 0, a = 0.170 (Example II.A-2A).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

E = 29000.0
BOLT_AREA = math.pi * 0.75 ** 2 / 4          # 3/4 in bolt, in^2
FNV = {"120": 54.0, "150": 68.0}             # Table J3.2, threads included (N)
FNT = {"120": 90.0, "150": 113.0}


def bolt_C(n: int, s: float, e: float) -> float:
    """Manual Table 7-6 coefficient for one column of n bolts at pitch s, load at e."""
    ys = np.arange(n) * s
    ys = ys - ys.mean()

    def balance(r0: float) -> tuple[float, float]:
        r = np.hypot(r0, ys)
        R = (1 - np.exp(-10 * 0.34 * r / r.max())) ** 0.55
        return float(np.sum(R * r0 / r)), float(np.sum(R * r))

    r0 = brentq(lambda r0: balance(r0)[1] / (r0 + e) - balance(r0)[0], 1e-6, 1e4)
    return balance(r0)[1] / (r0 + e)


def weld_ic(a: float, l: float = 1.0, n: int = 400) -> tuple[float, np.ndarray, np.ndarray]:
    """Two fillet lines of length l that coincide (Manual Table 8-4, angle 0, k = 0), load
    at e = a l. Returns the Manual's C, in kip/in per sixteenth of leg for both lines
    together, and each element's longitudinal and transverse share of Rult at that load."""
    ys = (np.arange(n) + 0.5) / n * l - l / 2
    e = a * l

    def elements(r0: float) -> tuple[np.ndarray, np.ndarray]:
        r = np.hypot(r0, ys)
        th = np.degrees(np.arctan2(np.abs(ys), r0))
        du = np.minimum(1.087 * (th + 6) ** -0.65, 0.17)
        dm = 0.209 * (th + 2) ** -0.32
        k = np.argmin(du / r)
        p = r * du[k] / r[k] / dm
        return (1 + 0.5 * np.sin(np.radians(th)) ** 1.5) * (p * (1.9 - 0.9 * p)) ** 0.3, r

    def balance(r0: float) -> tuple[float, float]:
        R, r = elements(r0)
        return float(np.sum(R * r0 / r)) * l / n, float(np.sum(R * r)) * l / n

    r0 = brentq(lambda r0: balance(r0)[1] / (r0 + e) - balance(r0)[0], 1e-3 * l, 1e3 * l)
    R, r = elements(r0)
    ratio = balance(r0)[1] / (r0 + e) / l
    return ratio * 2 * 0.6 * 70 * (math.sqrt(2) / 2) / 16, R * r0 / r, R * np.abs(ys) / r


def weld_C(a: float, l: float = 1.0) -> float:
    return weld_ic(a, l)[0]


def line(label: str, demand: float, capacity: float, unit: str = "kip") -> float:
    u = demand / capacity
    print(f"  {label:58} {demand:8.3f} / {capacity:8.3f} {unit:6} = {u:.3f}")
    return u


def solvers() -> None:
    print("Solver checks against the Manual")
    print(f"  Table 7-6, n = 4, s = 3 in, e = 1.5 in: C = {bolt_C(4, 3, 1.5):.3f} (Manual 3.54)")
    print(f"  Table 8-4, k = 0, a = 0.170:            C = {weld_C(0.170):.3f} (Manual 3.61)")


def seated(name: str, angle_t: float, fy: float, seat_len: float, setback: float, kdes: float,
           tw: float, tf: float, d: float, bolts: int, R: float, group: str = "120") -> None:
    """Unstiffened seat, ASD, Manual Part 10. The 1/4 in underrun is added to the setback, as
    the Manual recommends. Required bearing length is at least kdes."""
    print(f"{name}: unstiffened seat, ASD, R = {R} kip")
    lb_wly = 1.5 * R / (50 * tw) - 2.5 * kdes                        # J10-3, Omega 1.50
    crip0 = 0.40 * tw ** 2 * math.sqrt(E * 50 * tf / tw) / 2.00     # J10-5a at lb = 0
    lb = max(kdes, lb_wly)
    print(f"  bearing length: web yielding needs {lb_wly:.3f} in, crippling holds at lb = 0 "
          f"({crip0:.2f} kip), so lb = kdes = {lb:.3f} in")
    a = setback + 0.25
    e_f = a + lb / 2 - angle_t - 0.375
    Mn = fy * seat_len * angle_t ** 2 / 4 / 1.67
    line("seat leg flexure at t + 3/8 in from the back (Manual Part 10)", R * e_f, Mn, "kip-in")
    line("seat leg flexure without the underrun", R * max(e_f - 0.25, 0.0), Mn, "kip-in")
    rv = FNV[group] * BOLT_AREA / 2.00
    line(f"bolt shear, {bolts} bolts, single shear (J3.7)", R, bolts * rv)


def shear_tab(name: str, n: int, s: float, a: float, t: float, lev: float, group: str,
              bolt_cap: float, R: float) -> None:
    """Conventional single plate, ASD, Manual Table 10-9: e = a/2 for n = 2 to 5 with
    standard holes. bolt_cap is the weakest per-bolt strength (shear, bearing or tearout)."""
    print(f"{name}: conventional single plate, ASD, R = {R} kip")
    L = 2 * lev + (n - 1) * s
    C_half, C_full = bolt_C(n, s, a / 2), bolt_C(n, s, a)
    print(f"  per bolt: shear {FNV[group] * BOLT_AREA / 2:.3f}, weakest {bolt_cap:.3f} kip")
    line(f"bolt group, IC, e = a/2 = {a / 2} in, C = {C_half:.3f} (Table 10-9)", R, C_half * bolt_cap)
    line(f"bolt group, IC, e = a = {a} in, C = {C_full:.3f}", R, C_full * bolt_cap)
    rupture = 0.6 * 65 * (L - n * 0.875) * t / 2.00
    line(f"plate shear rupture, L = {L} in (J4.2b)", R, rupture)


def tearout(lc: float, t: float, fu: float = 65.0) -> float:
    return 1.2 * lc * t * fu / 2.00


def main() -> None:
    solvers()
    print()

    # with_petra/303-003: L5x3-1/2x3/8 A572 Gr 50, outstanding 3-1/2 in leg, 6 in long, four A325-N
    seated("with_petra/303-003", angle_t=0.375, fy=50, seat_len=6, setback=0.5, kdes=0.747,
           tw=0.25, tf=0.345, d=15.7, bolts=4, R=15.843)
    # without_petra/303-003: L4x4x1/2 A36, 6 in long, two A325-N in one row at 3-1/2 in gauge
    seated("without_petra/303-003", angle_t=0.5, fy=36, seat_len=6, setback=0.5, kdes=0.747,
           tw=0.25, tf=0.345, d=15.7, bolts=2, R=15.843)
    print("  J3.5 maximum spacing: 3.5 in against 24 t = 24(0.34 in) = 8.16 in (column web), holds")
    print()

    # with_petra/303-006: 1/4 in plate, five A325-N at 3 in, Lev 1-5/8 in, a = 2-1/4 in.
    # Weakest bolt: tearout of the plate at the bottom bolt, lc = 1.625 - 13/32.
    weakest = min(FNV["120"] * BOLT_AREA / 2, 2.4 * 0.75 * 0.25 * 65 / 2, tearout(1.625 - 13 / 32, 0.25))
    shear_tab("with_petra/303-006", n=5, s=3, a=2.25, t=0.25, lev=1.625, group="120", bolt_cap=weakest, R=45.988)
    # without_petra/303-006: 5/16 in plate, four Group 150-N at 3 in, Lev 1-3/4 in, a = 2-1/2 in.
    # Bolt shear governs: plate tearout at the bottom bolt and beam web tearout at the 1-3/4 in
    # edge (after underrun) both exceed it.
    print(f"  (303-006 without: plate tearout {tearout(1.75 - 13 / 32, 0.3125):.2f}, "
          f"beam web tearout {tearout(1.75 - 13 / 32, 0.300):.2f} kip)")
    shear_tab("without_petra/303-006", n=4, s=3, a=2.5, t=0.3125, lev=1.75, group="150",
              bolt_cap=FNV["150"] * BOLT_AREA / 2, R=45.988)
    print()

    # without_petra/303-005: WT8x15.5 hanger to a W16x31 flange, six A325 at 3-1/2 in gauge,
    # 3 rows at 2-1/2 in, 1-1/4 in end distance. Both flanges: bf 5.53, tf 0.44, tw 0.275.
    print("without_petra/303-005: tee hanger, ASD, T = 34.745 kip, prying (Manual Part 9)")
    bf, tf, tw, g, d = 5.53, 0.44, 0.275, 3.5, 0.75
    b = (g - tw) / 2
    a = min((bf - g) / 2, 1.25 * b)
    b1, a1 = b - d / 2, a + d / 2
    rho = b1 / a1
    p = 7.5 / 3
    delta = 1 - (d + 1 / 16) / p
    B = FNT["120"] * BOLT_AREA / 2.00
    tc = math.sqrt(1.67 * 4 * B * b1 / (p * 65))
    alpha1 = ((tc / tf) ** 2 - 1) / (delta * (1 + rho))
    Q = (tf / tc) ** 2 * (1 + delta) if alpha1 > 1 else (tf / tc) ** 2 * (1 + delta * alpha1)
    line(f"bolt tension with prying, Q = {Q:.3f}", 34.745 / 6, B * Q)
    line("tee stem tensile yield, 7.5 in x 0.275 in (J4.1a)", 34.745, 50 * 7.5 * tw / 1.67)
    print()

    # without_petra/303-019: 1/4 in end plate A572 Gr 50, 7-1/2 in wide, 14-1/2 in long, eight
    # A325-N, 1/4 in E70 fillets both sides to a W21x44 web (tw 0.35). LRFD.
    print("without_petra/303-019: shear end plate, LRFD, R = 139.063 kip")
    R, L, t, tw = 139.063, 14.5, 0.25, 0.35
    line("bolt shear, 8 bolts (J3.7)", R, 8 * 0.75 * FNV["120"] * BOLT_AREA)
    lw = L - 2 * 0.25
    line("weld, 2 lines of 1/4 in E70 (J2.4)", R, 0.75 * 0.6 * 70 * 0.707 * 0.25 * 2 * lw)
    line(f"beam web at the weld, tmin = 6.19 D / Fu = {6.19 * 4 / 65:.3f} in", R,
         0.75 * 0.6 * 65 * tw * lw)
    agv, anv, ant = (L - 2) * t, (L - 2 - 3.5 * 0.875) * t, (1.0 - 0.4375) * t
    block = min(0.6 * 65 * anv, 0.6 * 50 * agv) + 65 * ant
    line("end plate block shear, both sides, full block (J4.3)", R, 2 * 0.75 * block)
    agv1, anv1 = 2 * t, (2 - 0.4375) * t
    block1 = min(0.6 * 65 * anv1, 0.6 * 50 * agv1) + 65 * ant
    line("end plate block shear, one bolt at the top edge (J4.3)", R / 8, 0.75 * block1)
    line("end plate shear rupture, two net sections (J4.2b)", R, 0.75 * 0.6 * 65 * 2 * (L - 4 * 0.875) * t)
    print()

    # without_petra/303-022: 5/16 in A572 Gr 50 plate, two 3/16 in E70 fillets 13 in long to a
    # W12x40 flange (tf 0.515), e = 5 in. Manual Table 8-4 special case, load not in the plane
    # of the weld group: k = 0, a = e / l.
    print("without_petra/303-022: weld bracket, ASD, P = 48.42 kip, e = 5 in, l = 13 in")
    P, l, e, D = 48.42, 13.0, 5.0, 3
    C, along, across = weld_ic(e / l, l)
    capacity = C * D * l / 2.00
    line(f"weld group, IC, k = 0, a = {e / l:.3f}, C = {C:.3f} (Table 8-4)", P, capacity)
    fv, fb = P / (2 * l), P * e / (2 * l ** 2 / 6)
    line("weld group, elastic method, kds = 1.0", math.hypot(fv, fb), 0.6 * 70 * 0.707 * 0.1875 / 2.00, "kip/in")
    print(f"  plate tmin = 6.19 D / Fu = {6.19 * D / 65:.3f} in against 0.3125 in; flange 0.515 in")
    # The plate behind each weld element at the design load, from the IC element forces:
    # the share along the weld against shear rupture, the share across it against tensile yield.
    rult = 2 * 0.6 * 70 * 0.707 * 0.1875                  # both welds, nominal, kip/in
    scale = rult * (P / capacity) / 2.00                    # ASD flows at the design load
    shear, tension = 0.6 * 65 * 0.3125 / 2.00, 50 * 0.3125 / 1.67
    worst = np.max((along * scale / shear) ** 2 + (across * scale / tension) ** 2)
    print(f"  plate behind the weld, worst element: (f_along / {shear:.3f})^2 + (f_across / {tension:.3f})^2 "
          f"= {worst:.3f} (at most 1)")
    line("plate flexural yield at the weld line, Z = t l^2 / 4 (F11)", P * e, 50 * 0.3125 * l ** 2 / 4 / 1.67, "kip-in")
    line("plate shear yield (J4.2a)", P, 0.6 * 50 * 0.3125 * l / 1.50)


if __name__ == "__main__":
    main()
