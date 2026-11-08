"""Coped beam ends: the reduced section's moduli and its nominal flexural strength.

A top cope leaves a tee, checked by Manual Part 9 (Eqs. 9-9 to 9-20a, as Examples II.A-4, II.A-6
and II.A-28A apply them). A cope at both flanges leaves a rectangle, checked by Specification F11
with Lb equal to the cope length and Cb from Manual Eq. 9-21 (Example II.A-7).
"""

import math
from fractions import Fraction as F

from twin.checks import sqrt
from twin.data import E


class OutOfRange(ValueError):
    """The geometry falls in a branch the documents read do not give."""


def _first_moment_abs(y0, y1, yp):
    """Integral of |y - yp| over [y0, y1]."""
    if yp <= y0:
        return ((y1 - yp) ** 2 - (y0 - yp) ** 2) / 2
    if yp >= y1:
        return ((yp - y0) ** 2 - (yp - y1) ** 2) / 2
    return ((yp - y0) ** 2 + (y1 - yp) ** 2) / 2


def moduli(rects):
    """Least elastic modulus and plastic modulus of stacked rectangles (y0, y1, width)."""
    area = sum((y1 - y0) * w for y0, y1, w in rects)
    ybar = sum((y1 - y0) * w * (y0 + y1) / 2 for y0, y1, w in rects) / area
    inertia = sum(w * (y1 - y0) ** 3 / 12 + (y1 - y0) * w * ((y0 + y1) / 2 - ybar) ** 2 for y0, y1, w in rects)
    top = max(y1 for _, y1, _ in rects)
    bottom = min(y0 for y0, _, _ in rects)
    s = inertia / max(top - ybar, ybar - bottom)
    half, below, yp = area / 2, F(0), bottom
    for y0, y1, w in sorted(rects):
        piece = (y1 - y0) * w
        if below + piece >= half:
            yp = y0 + (half - below) / w
            break
        below += piece
    z = sum(w * _first_moment_abs(y0, y1, yp) for y0, y1, w in rects)
    return s, z


def tee_moduli(beam, dc):
    """Sc and Zc of a W coped at the top flange to depth dc, fillets ignored (Manual Table 9-2 values)."""
    h0 = beam.d - dc
    if h0 <= beam.tf:
        raise OutOfRange("the cope removes the whole web")
    return moduli([(F(0), beam.tf, beam.bf), (beam.tf, h0, beam.tw)])


def top_cope_moment(beam, fy, dc, c):
    """Nominal moment of a top-coped web; returns (Mn, equation note)."""
    hc = beam.d - dc
    if c / beam.d > 1 or c / hc > 1:
        raise OutOfRange("c/d or c/hc above 1.0 needs Manual Eqs. 9-19b and 9-20b, not in the documents read")
    f = 2 * c / beam.d  # Eq. 9-20a
    k = F(22, 10) * F(math.pow(float(hc / c), 1.65))  # Eq. 9-19a
    k1 = max(f * k, F(161, 100))  # Eq. 9-14
    lam = hc / beam.tw  # Eq. 9-17
    lam_p = F(475, 1000) * sqrt(k1 * E / fy)  # Eq. 9-18
    sc, zc = tee_moduli(beam, dc)
    mp, my = fy * zc, fy * sc  # Eqs. 9-15 and 9-16
    if lam <= lam_p:
        return mp, f"Mn = Mp (lambda {float(lam):.3g} <= lambda_p {float(lam_p):.3g}, Eq. 9-10 inferred)"
    if lam <= 2 * lam_p:
        mn = mp - (mp - my) * (lam / lam_p - 1)  # Eq. 9-11
        return mn, f"Eq. 9-11, lambda {float(lam):.3g}, lambda_p {float(lam_p):.3g}, Zc {float(zc):.3g}, Sc {float(sc):.3g}"
    raise OutOfRange("lambda above 2 lambda_p needs Manual Eqs. 9-12 and 9-13, not in the documents read")


def double_cope_moment(beam, fy, dct, dcb, c):
    """Nominal moment of a web coped at both flanges over the same length; returns (Mn, note)."""
    hc = beam.d - dct - dcb
    if hc <= 0:
        raise OutOfRange("the copes remove the whole web")
    tw = beam.tw
    sc, zc = tw * hc * hc / 6, tw * hc * hc / 4
    my, mp = fy * sc, fy * zc
    lb = c
    cb = max(3 + F(math.log(float(lb / beam.d))) * (1 - dct / beam.d), F(184, 100))  # Manual Eq. 9-21
    ratio = lb * hc / (tw * tw)
    if ratio <= F(8, 100) * E / fy:
        return mp, "F11.1, Eq. F11-1"
    if ratio <= F(19, 10) * E / fy:
        mn = min(cb * (F(152, 100) - F(274, 1000) * ratio * fy / E) * my, mp)
        return mn, f"F11.2(b), Eq. F11-3, Lb d/t^2 = {float(ratio):.4g}, Cb = {float(cb):.3g}"
    fcr = F(19, 10) * E * cb / ratio
    return min(fcr * sc, mp), f"F11.2(c), Eqs. F11-4 and F11-5, Cb = {float(cb):.3g}"
