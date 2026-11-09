"""What each fatigue mode checks (AISC 360-22 Appendix 3). Trusted physics.

A fatigue check reads two views of one cyclic load case. The case's own Ctx gives the peak:
each load ranges over its interval, so the check holds at the larger magnitude. A Range
over the same StatementBuilder gives the range: each load is its excursion above the low
end of its interval, so it ranges over [0, hi - lo], and the check holds at the width.
Both views build the kind's geometry (checks.GEOMETRY) from the same hypotheses, so a
stress is the same expression of the load in each, and every stress here is linear in it.
The number of cycles nSR is the case's `cycles` load (lower.CYCLES).

Every check is a stress against an allowable stress, in Pa, with no resistance or safety
factor (group None): Appendix 3 holds the stress range under the service load to its
allowable range. Each is excused where nSR <= 20,000, the cycles Section 3.1 starts at, and
FSR reads nSR no lower than that, so the formula stays finite where it is excused. The
registry rows are petra/registry/steel_fatigue.py's.

GENERATORS and ROWS extend checks.GENERATORS and checks.ROWS with the fatigue modes;
build.py and calc.py read these.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Mapping

from ... import mechanics as M
from ...ir import Input
from ...kernel import Expr, Max
from ...mechanics import add, c, div, mul, power, sq, sub
from . import checks as C
from . import limits as L
from .checks import GEOMETRY, Check, Ctx, Geometry, Interface, Ply
from .cyclic import PLATE_ENDS, paired
from .lower import CYCLES

PREFIX = "aisc360.app3"


class Range(Ctx):
    """The Ctx of the cyclic load's range. It shares the case's builder, so its hypotheses
    are the peak's; each load is its excursion above the low end of its interval."""

    def __init__(self, ctx: Ctx) -> None:
        vars(self).update(vars(ctx))

    def load(self, field_name: str) -> Expr | None:
        found = Ctx.load(self, field_name)
        if found is None:
            return None
        entry = next(e for e in self.design.loads[self.case].entries
                     if e.target == (self.conn.name,) and e.field == field_name)
        bound = entry.value.range if isinstance(entry.value, Input) else self.design.params[entry.value.name].range
        low = bound.value.lo
        return found if low == 0 else sub(found, c(low))


# --- Appendix 3's allowable stress ranges ---------------------------------------------------

def _k(ctx: Ctx, name: str) -> Expr:
    return ctx.const(f"{PREFIX}.{name}")


def cycles(ctx: Ctx) -> tuple[Expr, Expr] | None:
    """(nSR as the formulas read it, no lower than 20,000; the guard that excuses the check
    where nSR <= 20,000), or None where the case states no cycles."""
    n = ctx.load(CYCLES)
    if n is None:
        return None
    floor = _k(ctx, "cycles_min")
    return Max((n, floor)), sub(n, floor)


def fsr(ctx: Ctx, category: str, n: Expr) -> Expr:
    """Eq A-3-1: FSR = 1000 (Cf / nSR)^0.333 ksi, at least FTH, with Cf and FTH of the
    Table A-3.1 category."""
    cf, fth = _k(ctx, f"cat_{category}.cf"), _k(ctx, f"cat_{category}.fth")
    return Max((mul(_k(ctx, "a3_1"), power(div(cf, n), _k(ctx, "a3_1_exponent"))), fth))


def fsr_f(ctx: Ctx, n: Expr) -> Expr:
    """Eq A-3-2, category F: FSR = 100 (1.5 / nSR)^0.167 ksi, at least 8 ksi."""
    return Max((mul(_k(ctx, "a3_2"), power(div(_k(ctx, "a3_2_cf"), n), _k(ctx, "a3_2_exponent"))),
                _k(ctx, "a3_2_threshold")))


def rfil(ctx: Ctx, w: Expr, tp: Expr) -> Expr:
    """Eq A-3-6 before its cap at 1.0: RFIL = (0.06 + 0.72 w / tp) / tp^0.167, w and tp in
    inches."""
    inches = div(tp, c(L.INCH))
    return div(add(_k(ctx, "a3_6_intercept"), mul(_k(ctx, "a3_6_slope"), div(w, tp))),
               power(inches, _k(ctx, "a3_6_exponent")))


def fsr_root(ctx: Ctx, n: Expr, reduction: Expr) -> Expr:
    """Eq A-3-5, the root crack of a pair of transverse fillets (C''): FSR = 1000 RFIL
    (4.4 / nSR)^0.333 ksi, with no threshold; 4.4 is category C's Cf."""
    return mul(_k(ctx, "a3_1"), reduction, power(div(_k(ctx, "cat_c.cf"), n), _k(ctx, "a3_1_exponent")))


def peak_limit(ctx: Ctx, grade: str) -> Expr:
    """Section 3.1: the stress due to peak cyclic loads is at most 0.66 Fy."""
    return mul(_k(ctx, "peak"), ctx.mat(grade, "fy"))


def section_stress(moment: Expr | None, v: Expr, t: Expr, depth: Expr, modulus: Expr) -> Expr:
    """M / S + 3 V / (2 t depth): the extreme-fibre bending stress plus the rectangle's peak
    shear stress, which bounds the largest principal stress anywhere on the section."""
    shear = M.rectangle_peak_shear_stress(v, t, depth)
    return shear if moment is None else add(div(moment, modulus), shear)


# --- Bolted joints in shear: Section 3.4(a), Table A-3.1 Section 2 --------------------------

def _ply_stress(ctx: Ctx, itf: Interface, ply: Ply, moment: Expr | None, v: Expr, net: bool) -> Expr:
    """The stress at one of the ply's sections, each carrying its share of v: the gross
    section, or the net section through the line of holes, its shear taken on its net depth."""
    share = v if ply.sections == 1 else div(v, c(ply.sections))
    if not net:
        return section_stress(moment, share, ply.t, ply.depth, M.rectangle_elastic_modulus(ply.t, ply.depth))
    _, dh_v, _ = C.bolt_dims(ctx, itf.bolts, ply.hole, itf.oriented)
    hole = L.hole_net(ctx.const, dh_v)
    depth = sub(ply.depth, mul(c(itf.rows), hole))
    modulus = M.rectangle_net_elastic_modulus(ply.t, ply.depth, itf.rows, itf.pitch, hole)
    return section_stress(moment, share, ply.t, depth, modulus)


def gen_fatigue_bolted(ctx: Ctx, geo: Geometry) -> list[Check]:
    n = cycles(ctx)
    if n is None:
        return []
    nsr, floor = n
    rng = GEOMETRY[ctx.conn.kind](Range(ctx))
    moments = {f.name: f.moment for f in geo.flexures}
    ranges = {f.name: f.moment for f in rng.flexures}
    out = []
    for (itf, ply), (r_itf, r_ply) in zip(C._plies(geo), C._plies(rng)):
        if ply.depth is None or itf.shear is None or itf.bolts.joint == "snug":
            continue
        slip = itf.bolts.joint == "slip_critical"
        where, case = ("gross section", "Case 2.1") if slip else ("net section through the holes", "Case 2.2")
        stress = _ply_stress(ctx, r_itf, r_ply, ranges.get(ply.name), r_itf.shear, not slip)
        out.append(Check(f"{ply.name} ({itf.name}): stress range in the {where}, category B (App. 3.4(a), "
                         f"Table A-3.1 {case})", (stress,), fsr(ctx, "b", nsr), None, "", (floor,), "ksi"))
        peak = _ply_stress(ctx, itf, ply, moments.get(ply.name), itf.shear, not slip)
        out.append(Check(f"{ply.name} ({itf.name}): stress from the peak cyclic load in the {where}, at most "
                         "0.66 Fy (App. 3.1)", (peak,), peak_limit(ctx, ply.grade), None, "", (floor,), "ksi"))
    return out


# --- Bolts in tension: Section 3.4(b), Table A-3.1 Case 8.5 ----------------------------------

def tensile_stress_area(ctx: Ctx, size: str) -> Expr:
    """Eq A-3-7: At = (pi / 4) (db - 0.9743 / n)^2, n the bolt's threads per unit length."""
    g = f"bolt_us.{size}"
    return M.circle_area(sub(ctx.const(f"{g}.d"), div(_k(ctx, "a3_7_thread"), ctx.const(f"{g}.tpi"))))


def gen_fatigue_bolt_tension(ctx: Ctx, geo: Geometry) -> list[Check]:
    n = cycles(ctx)
    if n is None:
        return []
    nsr, floor = n
    rng = GEOMETRY[ctx.conn.kind](Range(ctx))
    out = []
    for itf, r_itf in zip(geo.interfaces, rng.interfaces):
        if itf.tension is None:
            continue
        area = mul(c(itf.n), tensile_stress_area(ctx, itf.bolts.size))
        if itf.bolts.joint == "snug":
            what = "the whole range of the applied tension"
            stress = div(r_itf.tension, area)
        else:
            what = "20% of the peak applied tension, the joint pretensioned with steel in the grip"
            stress = div(mul(_k(ctx, "s3_4_share"), itf.tension), area)
        out.append(Check(f"{itf.name}: bolt stress range on the tensile stress area from {what}, category G "
                         "(App. 3.4(b), Table A-3.1 Case 8.5)", (stress,), fsr(ctx, "g", nsr), None, "", (floor,), "ksi"))
    return out


# --- Fillet welds: Section 3.3(b), Table A-3.1 Case 8.2 --------------------------------------

def gen_fatigue_weld(ctx: Ctx, geo: Geometry) -> list[Check]:
    n = cycles(ctx)
    if n is None:
        return []
    nsr, floor = n
    r_ctx = Range(ctx)
    rng = GEOMETRY[ctx.conn.kind](r_ctx)
    out = []
    for wg in rng.welds:
        variants = [(wg, "", ())]
        if wg.end_loaded:
            # J2.2b(d): a fillet loaded from its end past 100 w carries its force over its
            # effective length (Eq J2-1), as the weld check takes it
            effective = replace(wg, length=L.end_loaded_length(ctx.const, wg.length, wg.size))
            beyond = sub(wg.length, mul(ctx.const("aisc360.j2_2b.end_loaded_ratio"), wg.size))
            variants.append((effective, ", over the end-loaded effective length of Eq J2-1", (beyond,)))
        throat = M.fillet_throat(wg.size)
        for group, over, guards in variants:
            for where, per_length in C._weld_points(r_ctx, group):
                out.append(Check(f"{wg.name}: shear stress range on the fillet throat{where}{over}, category F "
                                 "(App. 3.3(b), Table A-3.1 Case 8.2)", tuple(div(f, throat) for f in per_length),
                                 fsr_f(ctx, nsr), None, "", (floor, *guards), "ksi"))
    return out


# --- A plate's end welded with a pair of fillets: Section 3.3(c), Table A-3.1 Case 5.7 ----------

def weld_line_moment(geo: Geometry, plate: str) -> Expr:
    """The moment at the plate's welded end: its flexural check's, except a single plate's,
    which is its shear times the distance from the weld line to its bolt group's centroid,
    a + (columns - 1) g / 2. That is the most elastic analysis (Section 3.2) can put at the
    weld, with the beam end free to rotate at the bolts, and V a with one bolt column."""
    sp = geo.single_plate
    if plate == "plate" and sp is not None and sp.cols > 1:
        return mul(sp.force, add(sp.a, div(mul(c(sp.cols - 1), sp.gauge), c(2))))
    return next(f.moment for f in geo.flexures if f.name == plate)


def gen_fatigue_weld_end(ctx: Ctx, geo: Geometry) -> list[Check]:
    n = cycles(ctx)
    if n is None or not paired(ctx.conn):
        return []
    nsr, floor = n
    rng = GEOMETRY[ctx.conn.kind](Range(ctx))
    out = []
    for wg, r_wg in zip(geo.welds, rng.welds):
        if wg.name not in PLATE_ENDS:
            continue
        plate = PLATE_ENDS[wg.name]
        _, grade, tp, _ = wg.base[0]
        modulus = M.rectangle_elastic_modulus(tp, wg.length)
        moment, r_moment = weld_line_moment(geo, plate), weld_line_moment(rng, plate)
        stress = section_stress(r_moment, r_wg.force, tp, wg.length, modulus)
        out.append(Check(f"{plate}: stress range across the pair of fillets at its end, from the weld toe, category C "
                         "(App. 3.3(c)(1), Table A-3.1 Case 5.7)", (stress,), fsr(ctx, "c", nsr), None, "", (floor,),
                         "ksi"))
        reduction = rfil(ctx, wg.size, tp)
        out.append(Check(f"{plate}: stress range across the pair of fillets at its end, from the weld root, RFIL "
                         "(App. 3.3(c)(3), Table A-3.1 Case 5.7)", (stress,), fsr_root(ctx, nsr, reduction), None, "",
                         (floor, sub(c(1), reduction)), "ksi"))
        peak = section_stress(moment, wg.force, tp, wg.length, modulus)
        out.append(Check(f"{plate}: stress from the peak cyclic load at its welded end, at most 0.66 Fy (App. 3.1)",
                         (peak,), peak_limit(ctx, grade), None, "", (floor,), "ksi"))
    return out


# --- A beam coped at both flanges: Table A-3.1 Case 1.3 --------------------------------------

def gen_fatigue_cope(ctx: Ctx, geo: Geometry) -> list[Check]:
    n = cycles(ctx)
    cope = geo.cope
    if n is None or cope is None or cope.dcb is None:
        return []
    nsr, floor = n
    r_cope = GEOMETRY[ctx.conn.kind](Range(ctx)).cope

    def stress(cg) -> Expr:
        modulus = M.rectangle_elastic_modulus(cg.tw, cg.hc)
        return section_stress(mul(cg.force, cg.moment_arm), cg.force, cg.tw, cg.hc, modulus)

    return [
        Check("beam web: stress range at the bottom cope's reentrant corner, category E' (App. 3.3(a), Table A-3.1 "
              "Case 1.3)", (stress(r_cope),), fsr(ctx, "e_prime", nsr), None, "", (floor,), "ksi"),
        Check("beam web: stress from the peak cyclic load at the bottom cope, at most 0.66 Fy (App. 3.1)",
              (stress(cope),), peak_limit(ctx, cope.grade), None, "", (floor,), "ksi"),
    ]


# --- A joint under a cyclic load is pretensioned ----------------------------------------------

def gen_joint_type(ctx: Ctx, geo: Geometry) -> list[Check]:
    """checks.gen_joint_type, and in a cyclic case each joint pretensioned: J3.2(a)(2) lets
    snug-tight bolts carry tension only where fatigue is no design consideration, J3.2(b)(1)
    defers to RCSC 4.2, which requires a pretensioned joint under a fatigue load, and
    Appendix 3 considers and permits pretensioned joints only (Commentary 3.4). Excused
    where nSR <= 20,000, as every fatigue check."""
    out = C.gen_joint_type(ctx, geo)
    n = cycles(ctx)
    if n is None:
        return out
    _, floor = n
    for itf in geo.interfaces:
        out.append(Check(f"{itf.name}: the joint is pretensioned, its load cyclic (J3.2, RCSC 4.2)",
                         (ctx.const("rcsc2025.joint_level.pretensioned"),), C._joint_level(ctx, itf.bolts), None, "",
                         (floor,), "1"))
    return out


GENERATORS: Mapping[str, Callable[[Ctx, Geometry], list[Check]]] = {
    **C.GENERATORS,
    "joint_type": gen_joint_type,
    "fatigue_bolted": gen_fatigue_bolted, "fatigue_bolt_tension": gen_fatigue_bolt_tension,
    "fatigue_weld": gen_fatigue_weld, "fatigue_weld_end": gen_fatigue_weld_end, "fatigue_cope": gen_fatigue_cope,
}


# --- Validity rows -------------------------------------------------------------------------

def _row_no_prying(ctx: Ctx, geo: Geometry) -> tuple[tuple[Expr, ...], str]:
    """Manual Eq 9-30a with the tension T per bolt for Tc: a flange at least
    tmin = sqrt(4 T b' / (phi p Fu)) thick carries T with no prying. So T <= phi p Fu t^2 / (4 b'), the bound the prying
    check's no-prying branch takes, at each bolt's tributary length p, phi by the basis as
    the prying check takes it."""
    itf = next(i for i in geo.interfaces if i.prying)
    d = ctx.const(f"bolt_us.{itf.bolts.size}.d")
    phi = ctx.const("aisc360.j4_5.phi_y") if ctx.lrfd else div(c(1), ctx.const("aisc360.j4_5.omega_y"))
    per_bolt = div(itf.tension, c(itf.n))
    exprs = []
    for pr in itf.prying:
        b1 = sub(pr.b, div(d, c(2)))
        for _, p in pr.p:
            no_prying = div(mul(phi, p, ctx.mat(pr.grade, "fu"), sq(pr.t)), mul(ctx.const("aisc_manual.p9.tc"), b1))
            exprs.append(sub(per_bolt, no_prying))
    return tuple(exprs), "each flange the bolts bend is thick enough that they carry no prying force under the peak tension"


ROWS: Mapping[str, Callable[[Ctx, Geometry], tuple[tuple[Expr, ...], str]]] = {
    **C.ROWS,
    "steel.fatigue_bolt_tension.no_prying": _row_no_prying,
}
"""Each validity row's statement, the fatigue rows added to checks.ROWS."""
