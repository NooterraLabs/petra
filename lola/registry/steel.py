"""The steel-connection deck's data: AISC 360-22 Chapter J and RCSC 2025 numbers.
Trusted; each row is a premise with a tag, an owner and a source that cites its clause.

What is here, by clause:
- J3.1-J3.2, RCSC Tables 5.1-5.2: bolt groups as registry materials "bolt_group.<g>" with
  their nominal tensile strength (the group's number), Fnt, Fnv threads included (N) and
  excluded (X); minimum pretensions per size.
- J3.3, RCSC Table 3.1: hole dimensions per bolt size, constants "bolt_us.<size>.<hole>".
- J3.4-J3.6: minimum spacing, minimum edge distance per size, maximum spacing and edge.
- J3.7-J3.11, RCSC Section 5: resistance and safety factors, slip coefficients, Du, hf.
- J2: fillet size limits and the weld resistance factor; electrodes as materials.
- J4, J7, J10: resistance and safety factors; the web-sidesway-buckling constants Cr.
- ASTM minimum yield and tensile stresses of the plate and shape grades.
- Shapes from the AISC Shapes Database (steel_shapes.py).

Tags follow constants.py: a value checked against the free published text (RCSC 2025,
AISC's 2022-to-2016 comparison) or fixed by a designation is sanctioned and owned by its
issuer; a value recalled from the AISC 360-22 text, which LoLa has not been able to read
yet, is judged, owned by lola-maintainers, and its source says "recalled". Upgrading a row
to sanctioned is a one-line change once the published text is checked.

Values are exact rationals in SI base units, converted from inches, kips and ksi with the
exact factors of units.CUSTOMARY. A size id spells a fraction with underscores: bolt
"3_4" is 3/4 in, "1_1_8" is 1-1/8 in.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Callable, Mapping

from ..kernel import Add, Const, Div, Expr, Interval, Mul, Neg, Pi, PowInt, Sym
from ..premises import Tag
from ..units import CUSTOMARY
from .model import Constant, Derived, Material, Stated
from .steel_shapes import constants as shape_constants

SANCTIONED, JUDGED = Tag.SANCTIONED, Tag.JUDGED
MAINTAINERS = "lola-maintainers"
RECALLED = "recalled and not checked against the published text"
CHECKED = "checked against the published text (A360-22W-ewr.pdf)"

INCH = CUSTOMARY["inch"][0]
KIP = CUSTOMARY["kip"][0]
KSI = CUSTOMARY["ksi"][0]

RCSC = "RCSC 2025 Specification for Structural Joints Using High-Strength Bolts"
AISC = "AISC 360-22"
MANUAL = "AISC Steel Construction Manual, 16th ed."
COMPARISON = "AISC 360-22 vs 360-16 comparison (aisc.org, 2022-to-2016-spec-comparison.pdf)"


def _q(text: str) -> Fraction:
    """"1-1/8" -> 9/8; "13/16" -> 13/16; "29000" -> 29000."""
    whole, _, frac = text.partition("-")
    return Fraction(whole) + (Fraction(frac) if frac else 0)


def _iv(x: Fraction) -> Interval:
    return Interval(x, x)


# --- Bolt sizes ------------------------------------------------------------------------

BOLT_SIZES: tuple[str, ...] = ("1/2", "5/8", "3/4", "7/8", "1", "1-1/8", "1-1/4", "1-3/8", "1-1/2")
"""Nominal diameters in inches of the high-strength bolts RCSC 2025 Table 5.2 lists."""


def size_id(size: str) -> str:
    """"1-1/8" -> "1_1_8"."""
    return size.replace("-", "_").replace("/", "_")


HOLES: Mapping[str, tuple[str, str, str, str, str, str]] = {
    "1/2": ("9/16", "5/8", "9/16", "11/16", "9/16", "1-1/4"),
    "5/8": ("11/16", "13/16", "11/16", "7/8", "11/16", "1-9/16"),
    "3/4": ("13/16", "15/16", "13/16", "1", "13/16", "1-7/8"),
    "7/8": ("15/16", "1-1/16", "15/16", "1-1/8", "15/16", "2-3/16"),
    "1": ("1-1/8", "1-1/4", "1-1/8", "1-5/16", "1-1/8", "2-1/2"),
}
"""RCSC 2025 Table 3.1 (= AISC 360-22 Table J3.3), in inches: standard diameter, oversized
diameter, short-slot width and length, long-slot width and length. Larger bolts follow the
table's last row (holes_for)."""

HOLE_PROPS = ("std", "ovs", "ssl_w", "ssl_l", "lsl_w", "lsl_l")


def holes_for(size: str) -> tuple[Fraction, ...]:
    if size in HOLES:
        return tuple(_q(x) for x in HOLES[size])
    d = _q(size)
    eighth = Fraction(1, 8)
    return (d + eighth, d + Fraction(5, 16), d + eighth, d + Fraction(3, 8), d + eighth, Fraction(5, 2) * d)


EDGE_MIN: Mapping[str, str] = {
    "1/2": "3/4", "5/8": "7/8", "3/4": "1", "7/8": "1-1/8", "1": "1-1/4", "1-1/8": "1-1/2", "1-1/4": "1-5/8",
}
"""AISC 360-22 Table J3.4, minimum edge distance in inches from the centre of a standard
hole to an edge; over 1-1/4 in, 1.25 d. Checked against the published table."""

PRETENSION: Mapping[str, tuple[int, int]] = {
    "1/2": (12, 15), "5/8": (19, 24), "3/4": (28, 35), "7/8": (39, 49), "1": (51, 64),
    "1-1/8": (64, 80), "1-1/4": (81, 102), "1-3/8": (97, 121), "1-1/2": (118, 148),
}
"""RCSC 2025 Table 5.2 minimum bolt pretension Tm in kips: (Group 120, Groups 144 and 150)."""

THREADS_PER_INCH: Mapping[str, int] = {
    "1/2": 13, "5/8": 11, "3/4": 10, "7/8": 9, "1": 8, "1-1/8": 7, "1-1/4": 7, "1-3/8": 6, "1-1/2": 6,
}
"""ASME B1.1 UNC coarse series, threads per inch. Recalled; read only by the consistency
relation that re-derives Table 5.2 from the tensile stress area."""


def _bolt_constants() -> list[Constant]:
    rows: list[Constant] = []
    for size in BOLT_SIZES:
        d = _q(size)
        g = f"bolt_us.{size_id(size)}"
        rows.append(Constant(f"{g}.d", _iv(d * INCH), "m", SANCTIONED, "ASTM",
                             f"ASTM F3125 bolt designation {size} in: nominal diameter {size} in (the designation)",
                             f"a {size} in bolt has nominal diameter {size} in"))
        names = {"std": "standard hole diameter", "ovs": "oversized hole diameter", "ssl_w": "short-slot width",
                 "ssl_l": "short-slot length", "lsl_w": "long-slot width", "lsl_l": "long-slot length"}
        tabulated = size in HOLES
        for prop, value in zip(HOLE_PROPS, holes_for(size)):
            how = "tabulated" if tabulated else "the table's row for d >= 1-1/8 in"
            rows.append(Constant(f"{g}.{prop}", _iv(value * INCH), "m", SANCTIONED, "RCSC",
                                 f"{RCSC}, Table 3.1 Nominal Bolt Hole Dimensions (= {AISC} Table J3.3), {size} in bolt: "
                                 f"{names[prop]} {value} in ({how})",
                                 f"a {size} in bolt's {names[prop]} is {value} in"))
        edge = _q(EDGE_MIN[size]) if size in EDGE_MIN else Fraction(5, 4) * d
        rows.append(Constant(f"{g}.edge_min", _iv(edge * INCH), "m", SANCTIONED, "AISC",
                             f"{AISC} Section J3.5, Table J3.4 Minimum Edge Distance from Center of Standard Hole to Edge "
                             f"of Connected Part, {size} in bolt: {edge} in; {CHECKED}",
                             f"a {size} in bolt in a standard hole sits at least {edge} in from an edge"))
        g120, g150 = PRETENSION[size]
        rows.append(Constant(f"{g}.Tm_g120", _iv(g120 * KIP), "N", SANCTIONED, "RCSC",
                             f"{RCSC}, Table 5.2 Minimum Bolt Pretension, Group 120, {size} in: {g120} kips "
                             f"(= {AISC} Table J3.1)",
                             f"a pretensioned {size} in Group 120 bolt carries at least {g120} kips"))
        rows.append(Constant(f"{g}.Tm_g150", _iv(g150 * KIP), "N", SANCTIONED, "RCSC",
                             f"{RCSC}, Table 5.2 Minimum Bolt Pretension, Groups 144 and 150, {size} in: {g150} kips "
                             f"(= {AISC} Table J3.1)",
                             f"a pretensioned {size} in Group 144 or 150 bolt carries at least {g150} kips"))
        tpi = THREADS_PER_INCH[size]
        rows.append(Constant(f"{g}.tpi", _iv(Fraction(tpi) / INCH), "1/m", JUDGED, MAINTAINERS,
                             f"ASME B1.1 Unified coarse thread series (UNC), {size} in: {tpi} threads per inch; {RECALLED}",
                             f"a {size} in UNC thread has {tpi} threads per inch"))
        nut = Fraction(3, 2) * d + Fraction(1, 8)
        rows.append(Constant(f"{g}.nut_F", _iv(nut * INCH), "m", JUDGED, MAINTAINERS,
                             f"ASME B18.2.6, dimensions of heavy hex nuts, {size} in structural bolts: width across flats "
                             f"F = 1.5 d + 1/8 in = {nut} in; {RECALLED}",
                             f"a {size} in heavy hex nut is {nut} in across flats"))
    return rows


# --- Bolt groups (J3.1-J3.2) ------------------------------------------------------------

BOLT_GROUPS: Mapping[str, tuple[str, str, str | None, str | None, str | None, str]] = {
    "120": ("ASTM F3125 Grades A325 and F1852 (Group 120)", "90", "54", "68", "120", "sanctioned"),
    "144": ("ASTM F3148 Grade 144 (Group 144)", "108", "65", "81", "144", "sanctioned"),
    "150": ("ASTM F3125 Grades A490 and F2280 (Group 150)", "113", "68", "84", "150", "sanctioned"),
    "200": ("ASTM F3043 and F3111 (Group 200)", "150", "90", "113", "200", "comparison"),
    "A307": ("ASTM A307 Grade A", "45", "27", None, "60", "comparison"),
}
"""group -> (standard, Fnt, Fnv threads included, Fnv threads excluded, tensile strength,
where Fn was checked), stresses in ksi. Groups 120, 144 and 150 are RCSC 2025 Table 5.1;
Group 200's Fnt and Fnv(X) and A307's Fnt and Fnv are in AISC's comparison document;
Group 200's Fnv(N) was checked against AISC 360-22 Table J3.2; A307's tensile strength is
recalled. A307 has one Fnv, whatever
the threads."""


def _bolt_groups() -> dict[str, Material]:
    out: dict[str, Material] = {}
    for group, (standard, fnt, fnv_n, fnv_x, fu, checked) in BOLT_GROUPS.items():
        def stated(value: str, what: str, sanctioned: bool, where: str) -> Stated:
            tag, owner = (SANCTIONED, "RCSC" if checked == "sanctioned" else "AISC") if sanctioned else (JUDGED, MAINTAINERS)
            source = where if sanctioned else f"{where}; {RECALLED}"
            return Stated(_iv(_q(value) * KSI), "Pa", tag, owner, source, f"{standard}: {what} {value} ksi")

        table = (f"{RCSC}, Table 5.1 Nominal Strengths per Unit Area (= {AISC} Table J3.2)" if checked == "sanctioned"
                 else f"{AISC} Table J3.2 as printed in the {COMPARISON}")
        props: dict[str, Stated] = {
            "Fnt": stated(fnt, "nominal tensile stress Fnt", True, f"{table}, Group {group}: Fnt = {fnt} ksi"),
            "Fnv_N": stated(fnv_n, "nominal shear stress Fnv, threads not excluded", True,
                            f"{AISC} Table J3.2, Group {group}: Fnv (N) = {fnv_n} ksi; {CHECKED}"
                            if group == "200" else f"{table}, Group {group}: Fnv = {fnv_n} ksi"),
        }
        if fnv_x is not None:
            props["Fnv_X"] = stated(fnv_x, "nominal shear stress Fnv, threads excluded", True,
                                    f"{table}, Group {group}: Fnv (X) = {fnv_x} ksi")
        if group == "A307":
            props["fu"] = stated(fu, "minimum tensile strength", False,
                                 f"ASTM A307 Grade A minimum tensile strength 60 ksi (the ASTM A307 standard; {AISC} Section J3.1 "
                                 "names the grade without it)")
        else:
            props["fu"] = Stated(_iv(_q(fu) * KSI), "Pa", SANCTIONED, "AISC",
                                 f"{AISC} Section J3.1-J3.2 bolt group naming ({COMPARISON}): Group {group} is named by "
                                 f"its minimum tensile strength, {fu} ksi (the designation)",
                                 f"{standard}: minimum tensile strength {fu} ksi")
        mid = f"bolt_group.{group}"
        out[mid] = Material(mid, "bolt", standard, props)
    return out


# --- Plate and shape grades, electrodes -------------------------------------------------

GRADES: Mapping[str, tuple[str, str, str, str | None]] = {
    "A992": ("ASTM A992 (W shapes)", "50", "65", "Example D.1"),
    "A36": ("ASTM A36 (plates, angles, shapes)", "36", "58", None),
    "A572_50": ("ASTM A572 Grade 50 (plates, shapes)", "50", "65", "Example D.2"),
}
"""grade -> (standard, Fy, Fu, the Companion example that prints them) in ksi: the ASTM
specified minimums AISC Manual Table 2-4 lists. AISC 360-22 Table A3.1 names the grades
without values; the Companion to the Manual (v16.0, Vol. 1) quotes Table 2-4's values for
A992 and A572 Grade 50. A36's appear in neither text, so they stay recalled."""


def _grades() -> dict[str, Material]:
    out: dict[str, Material] = {}
    for grade, (standard, fy, fu, example) in GRADES.items():
        tag, owner = (SANCTIONED, "AISC") if example else (JUDGED, MAINTAINERS)
        where = (f"{MANUAL} Table 2-4, as quoted in the Companion to the Manual v16.0 Vol. 1 {example}" if example
                 else f"{MANUAL} Table 2-4; {AISC} Table A3.1 lists the grade without values; {RECALLED}")
        props = {
            "fy": Stated(_iv(_q(fy) * KSI), "Pa", tag, owner,
                         f"{standard} specified minimum yield stress Fy = {fy} ksi ({where})", f"{standard}: Fy >= {fy} ksi"),
            "fu": Stated(_iv(_q(fu) * KSI), "Pa", tag, owner,
                         f"{standard} specified minimum tensile strength Fu = {fu} ksi ({where})", f"{standard}: Fu >= {fu} ksi"),
            "E": Derived(Sym("const.aisc360.E"), "Pa", f"{AISC} Symbols list: E = 29,000 ksi"),
        }
        mid = f"steel.{grade}"
        out[mid] = Material(mid, "steel", standard, props)
    return out


ELECTRODES: tuple[str, ...] = ("70", "80")


def _electrodes() -> dict[str, Material]:
    return {
        f"electrode.E{n}": Material(f"electrode.E{n}", "electrode", f"AWS A5.1/A5.5 E{n}XX", {
            "FEXX": Stated(_iv(_q(n) * KSI), "Pa", SANCTIONED, "AWS",
                           f"AWS A5.1/A5.5 classification E{n}XX: the digits after E give the weld metal's minimum "
                           f"tensile strength, {n} ksi (the designation); {AISC} Section J2.6, Table J2.5 FEXX",
                           f"E{n}XX weld metal has tensile strength {n} ksi"),
        })
        for n in ELECTRODES
    }


# --- Factors and limits ------------------------------------------------------------------

_F = tuple[str, str, str, Tag, str, str]
"""(constant name, value text, unit, tag, owner, source)."""

FACTORS: tuple[_F, ...] = (
    ("rcsc2025.s5_1.phi", "0.75", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.1: resistance factor 0.75 for bolt shear and tension (= {AISC} Section J3.7)"),
    ("rcsc2025.s5_1.omega", "2.00", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.1: safety factor 2.00 for bolt shear and tension (= {AISC} Section J3.7)"),
    ("rcsc2025.s5_3.phi", "0.75", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.3: resistance factor 0.75 for bearing at bolt holes (= {AISC} Section J3.11)"),
    ("rcsc2025.s5_3.omega", "2.00", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.3: safety factor 2.00 for bearing at bolt holes (= {AISC} Section J3.11)"),
    ("rcsc2025.s5_4.phi_std", "1.00", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: slip resistance factor 1.00 for standard holes and short slots perpendicular to the load "
     f"(= {AISC} Section J3.9)"),
    ("rcsc2025.s5_4.omega_std", "1.50", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: slip safety factor 1.50 for standard holes and short slots perpendicular to the load"),
    ("rcsc2025.s5_4.phi_ovs", "0.85", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: slip resistance factor 0.85 for oversized holes and short slots parallel to the load"),
    ("rcsc2025.s5_4.omega_ovs", "1.76", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: slip safety factor 1.76 for oversized holes and short slots parallel to the load"),
    ("rcsc2025.s5_4.phi_lsl", "0.70", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: slip resistance factor 0.70 for long-slotted holes"),
    ("rcsc2025.s5_4.omega_lsl", "2.14", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: slip safety factor 2.14 for long-slotted holes"),
    ("rcsc2025.s5_4.mu_a", "0.30", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4(1): mean slip coefficient 0.30 for Class A surfaces (= {AISC} Section J3.9)"),
    ("rcsc2025.s5_4.mu_b", "0.50", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4(2): mean slip coefficient 0.50 for Class B surfaces (= {AISC} Section J3.9)"),
    ("rcsc2025.s5_4.Du", "1.13", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: Du = 1.13 for building structures (= {AISC} Section J3.9)"),
    ("rcsc2025.s5_4.hf_one", "1.0", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: filler factor hf = 1.0 with no fillers or one filler (= {AISC} Section J3.9)"),
    ("rcsc2025.s5_4.hf_two", "0.85", "1", SANCTIONED, "RCSC",
     f"{RCSC}, Section 5.4: filler factor hf = 0.85 for two or more fillers without added bolts"),
    ("aisc360.E", "29000", "Pa", SANCTIONED, "AISC",
     f"{AISC} Symbols list: modulus of elasticity of steel E = 29,000 ksi; {CHECKED}"),
    ("aisc360.nu", "0.3", "1", SANCTIONED, "AISC",
     f"{AISC} Commentary Section E7, Eq. C-E7-3 (also Eq. C-F9-1): Poisson's ratio 0.3; {CHECKED}"),
    ("aisc360.j2_4.phi", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Section J2.4, Table J2.5: weld metal phi = 0.75; {CHECKED}"),
    ("aisc360.j2_4.omega", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Section J2.4, Table J2.5: weld metal Omega = 2.00; {CHECKED}"),
    ("aisc360.j4_1.phi_y", "0.90", "1", SANCTIONED, "AISC", f"{AISC} Section J4.1(a): tensile yielding phi = 0.90; {CHECKED}"),
    ("aisc360.j4_1.omega_y", "1.67", "1", SANCTIONED, "AISC", f"{AISC} Section J4.1(a): tensile yielding Omega = 1.67; {CHECKED}"),
    ("aisc360.j4_1.phi_r", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Section J4.1(b): tensile rupture phi = 0.75; {CHECKED}"),
    ("aisc360.j4_1.omega_r", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Section J4.1(b): tensile rupture Omega = 2.00; {CHECKED}"),
    ("aisc360.j4_2.phi_y", "1.00", "1", SANCTIONED, "AISC", f"{AISC} Section J4.2(a): shear yielding phi = 1.00; {CHECKED}"),
    ("aisc360.j4_2.omega_y", "1.50", "1", SANCTIONED, "AISC", f"{AISC} Section J4.2(a): shear yielding Omega = 1.50; {CHECKED}"),
    ("aisc360.j4_2.phi_r", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Section J4.2(b): shear rupture phi = 0.75; {CHECKED}"),
    ("aisc360.j4_2.omega_r", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Section J4.2(b): shear rupture Omega = 2.00; {CHECKED}"),
    ("aisc360.j4_3.phi", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Section J4.3: block shear phi = 0.75; {CHECKED}"),
    ("aisc360.j4_3.omega", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Section J4.3: block shear Omega = 2.00; {CHECKED}"),
    ("aisc360.j4_4.phi", "0.90", "1", SANCTIONED, "AISC", f"{AISC} Section J4.4: compression, Lc/r <= 25, phi = 0.90; {CHECKED}"),
    ("aisc360.j4_4.omega", "1.67", "1", SANCTIONED, "AISC", f"{AISC} Section J4.4: compression, Lc/r <= 25, Omega = 1.67; {CHECKED}"),
    ("aisc360.j4_5.phi_y", "0.90", "1", SANCTIONED, "AISC", f"{AISC} Section F1(a), which Commentary Section J4.5 applies to connecting elements: flexural yielding "
     f"phi = 0.90; {CHECKED}"),
    ("aisc360.j4_5.omega_y", "1.67", "1", SANCTIONED, "AISC", f"{AISC} Section F1(b), which Commentary Section J4.5 applies to connecting elements: flexural yielding "
     f"Omega = 1.67; {CHECKED}"),
    ("aisc360.j4_5.phi_r", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Commentary Section J4.5 (Fu Znet; Manual Eq. 9-8): flexural rupture phi = 0.75; {CHECKED}"),
    ("aisc360.j4_5.omega_r", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Commentary Section J4.5 (Fu Znet; Manual Eq. 9-8): flexural rupture Omega = 2.00; {CHECKED}"),
    ("aisc360.j7.phi", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Section J7: bearing on milled surfaces phi = 0.75; {CHECKED}"),
    ("aisc360.j7.omega", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Section J7: bearing on milled surfaces Omega = 2.00; {CHECKED}"),
    ("aisc360.j10_1.phi", "0.90", "1", SANCTIONED, "AISC", f"{AISC} Section J10.1: flange local bending phi = 0.90; {CHECKED}"),
    ("aisc360.j10_1.omega", "1.67", "1", SANCTIONED, "AISC", f"{AISC} Section J10.1: flange local bending Omega = 1.67; {CHECKED}"),
    ("aisc360.j10_2.phi", "1.00", "1", SANCTIONED, "AISC", f"{AISC} Section J10.2: web local yielding phi = 1.00; {CHECKED}"),
    ("aisc360.j10_2.omega", "1.50", "1", SANCTIONED, "AISC", f"{AISC} Section J10.2: web local yielding Omega = 1.50; {CHECKED}"),
    ("aisc360.j10_3.phi", "0.75", "1", SANCTIONED, "AISC", f"{AISC} Section J10.3: web local crippling phi = 0.75; {CHECKED}"),
    ("aisc360.j10_3.omega", "2.00", "1", SANCTIONED, "AISC", f"{AISC} Section J10.3: web local crippling Omega = 2.00; {CHECKED}"),
    ("aisc360.j10_4.phi", "0.85", "1", SANCTIONED, "AISC", f"{AISC} Section J10.4: web sidesway buckling phi = 0.85; {CHECKED}"),
    ("aisc360.j10_4.omega", "1.76", "1", SANCTIONED, "AISC", f"{AISC} Section J10.4: web sidesway buckling Omega = 1.76; {CHECKED}"),
    ("aisc360.j10_4.cr_below_my", "960000", "Pa", SANCTIONED, "AISC",
     f"{AISC} Section J10.4: Cr = 960,000 ksi when alpha_s Mr < My at the load (alpha_s 1.0 LRFD, 1.5 ASD); "
     f"{CHECKED}"),
    ("aisc360.j10_4.cr_at_my", "480000", "Pa", SANCTIONED, "AISC",
     f"{AISC} Section J10.4: Cr = 480,000 ksi when alpha_s Mr >= My at the load (alpha_s 1.0 LRFD, 1.5 ASD); "
     f"{CHECKED}"),
    ("aisc360.j10_5.phi", "0.90", "1", SANCTIONED, "AISC", f"{AISC} Section J10.5: web compression buckling phi = 0.90; {CHECKED}"),
    ("aisc360.j10_5.omega", "1.67", "1", SANCTIONED, "AISC", f"{AISC} Section J10.5: web compression buckling Omega = 1.67; {CHECKED}"),
    ("aisc360.j10_6.phi", "0.90", "1", SANCTIONED, "AISC", f"{AISC} Section J10.6: web panel-zone shear phi = 0.90; {CHECKED}"),
    ("aisc360.j10_6.omega", "1.67", "1", SANCTIONED, "AISC", f"{AISC} Section J10.6: web panel-zone shear Omega = 1.67; {CHECKED}"),
    ("aisc360.j3_4.spacing_ratio", "8/3", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.4 (minimum spacing): centre-to-centre distance at least 2-2/3 d; {CHECKED}"),
    ("aisc360.j3_6.pitch_t", "24", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.6(a): maximum spacing 24 times the thinner part for painted or unpainted members not "
     f"subject to corrosion; {CHECKED}"),
    ("aisc360.j3_6.pitch_max", "12", "m", SANCTIONED, "AISC",
     f"{AISC} Section J3.6(a): maximum spacing 12 in for painted or unpainted members not subject to corrosion; {CHECKED}"),
    ("aisc360.j3_6.weathering_pitch_t", "14", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.6(b): maximum spacing 14 times the thinner part for unpainted weathering steel; {CHECKED}"),
    ("aisc360.j3_6.weathering_pitch_max", "7", "m", SANCTIONED, "AISC",
     f"{AISC} Section J3.6(b): maximum spacing 7 in for unpainted weathering steel; {CHECKED}"),
    ("aisc360.j3_6.edge_t", "12", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.6: maximum edge distance 12 times the part's thickness; {CHECKED}"),
    ("aisc360.j3_6.edge_max", "6", "m", SANCTIONED, "AISC", f"{AISC} Section J3.6: maximum edge distance 6 in; {CHECKED}"),
    ("aisc360.j2_2b.t1", "1/4", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4 Minimum Size of Fillet Welds: first row, thinner part up to 1/4 in; {CHECKED}"),
    ("aisc360.j2_2b.w1", "1/8", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4: minimum fillet 1/8 in for a thinner part up to 1/4 in; {CHECKED}"),
    ("aisc360.j2_2b.t2", "1/2", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4: second row, thinner part over 1/4 in up to 1/2 in; {CHECKED}"),
    ("aisc360.j2_2b.w2", "3/16", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4: minimum fillet 3/16 in for a thinner part over 1/4 in up to 1/2 in; {CHECKED}"),
    ("aisc360.j2_2b.t3", "3/4", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4: third row, thinner part over 1/2 in up to 3/4 in; {CHECKED}"),
    ("aisc360.j2_2b.w3", "1/4", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4: minimum fillet 1/4 in for a thinner part over 1/2 in up to 3/4 in; {CHECKED}"),
    ("aisc360.j2_2b.w4", "5/16", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b, Table J2.4: minimum fillet 5/16 in for a thinner part over 3/4 in; {CHECKED}"),
    ("aisc360.j2_2b.edge_t", "1/4", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(b): along an edge at least 1/4 in thick the fillet is at most t - 1/16 in; {CHECKED}"),
    ("aisc360.j2_2b.edge_less", "1/16", "m", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(b): the fillet along an edge at least 1/4 in thick is at most 1/16 in less than t; {CHECKED}"),
    ("aisc360.j2_2b.length_ratio", "4", "1", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(c): a fillet weld is at least four times its size long; {CHECKED}"),
    ("aisc360.j4_4.slenderness", "25", "1", SANCTIONED, "AISC",
     f"{AISC} Section J4.4(a): the yield formula applies when Lc/r <= 25; {CHECKED}"),
    ("aisc360.j3_3.long_slot_plies", "1", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.3(f): long-slotted holes in only one of the connected parts at an individual faying surface; "
     f"{CHECKED}"),
    ("rcsc2025.joint_level.snug", "0", "1", JUDGED, MAINTAINERS,
     f"{RCSC}, Section 4: joint types ranked by what their installation guarantees, snug-tight 0 < pretensioned 1 < "
     "slip-critical 2 (each meets the requirements of the ones before it); the ranking is LoLa's encoding, "
     "not checked against the published text"),
    ("rcsc2025.joint_level.pretensioned", "1", "1", JUDGED, MAINTAINERS,
     f"{RCSC}, Section 4: a pretensioned joint ranks 1 (above snug-tight, below slip-critical); LoLa's encoding, "
     "not checked against the published text"),
    ("rcsc2025.joint_level.slip_critical", "2", "1", JUDGED, MAINTAINERS,
     f"{RCSC}, Section 4: a slip-critical joint ranks 2, the highest; LoLa's encoding, not checked against the "
     "published text"),
    ("aisc_manual.clearance.socket", "1/2", "m", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 7 (entering and tightening clearances): socket wall allowance beyond the nut's corners, judged "
     "at 1/2 in; the method is encoded, the value is judged and not checked against the Manual's table"),
    ("aisc_manual.seat.critical_offset", "3/8", "m", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 10 (unstiffened seated connections): critical section of the outstanding leg 3/8 in beyond the "
     f"angle thickness from the back of the angle; {RECALLED}"),
    ("aisc_manual.seat.stiffener_clip", "1/2", "m", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 10 (stiffened seated connections): corner clip of the stiffener's bearing edge, judged at 1/2 in; "
     "the bearing area is (W - clip) ts; not checked against the published text"),
)


STOCK_PLATES: tuple[str, ...] = (
    "3/16", "1/4", "5/16", "3/8", "7/16", "1/2", "9/16", "5/8",
    "3/4", "7/8", "1", "1-1/8", "1-1/4", "1-3/8", "1-1/2",
    "1-3/4", "2", "2-1/4", "2-1/2", "2-3/4", "3",
)
"""The shop deck's plate thicknesses in inches: sixteenths to 5/8, eighths to 1-1/2,
quarters to 3. A plate, stiffener or seat of another thickness is outside the makeable set."""

STOCK_PLATE = "shop_deck.plate."


def stock_plate_id(size: str) -> str:
    """ "1-1/8" -> "shop_deck.plate.t1_1_8" """
    return STOCK_PLATE + "t" + size.replace("-", "_").replace("/", "_")


def _stock_constants() -> list[Constant]:
    return [Constant(stock_plate_id(t), _iv(_q(t) * INCH), "m", JUDGED, MAINTAINERS,
                     f"{MANUAL} Part 1 (plate availability): the shop deck stocks plates in 1/16 in steps to 5/8 in, "
                     f"1/8 in to 1-1/2 in, 1/4 in to 3 in, a judged list; {RECALLED}", f"plate {t} in is stocked")
            for t in STOCK_PLATES]


def _factor_constants() -> list[Constant]:
    rows = []
    for name, text, unit, tag, owner, source in FACTORS:
        scale = {"1": Fraction(1), "Pa": KSI, "m": INCH}[unit]
        shown = {"1": "", "Pa": " ksi", "m": " in"}[unit]
        rows.append(Constant(name, _iv(_q(text) * scale), unit, tag, owner, source, f"{name} = {text}{shown}"))
    return rows


# --- Assembly ----------------------------------------------------------------------------

def steel_constants() -> dict[str, Constant]:
    rows = [*_bolt_constants(), *_factor_constants(), *_stock_constants(), *shape_constants().values()]
    table = {c.name: c for c in rows}
    if len(table) != len(rows):
        raise RuntimeError("a steel constant is defined twice")
    return table


def steel_materials() -> dict[str, Material]:
    return {**_grades(), **_bolt_groups(), **_electrodes()}


# --- Consistency relations (consistency.RELATIONS appends these) -------------------------


def _n(x: int | str | Fraction) -> Const:
    return Const(Fraction(x))


def _rec(prop: str) -> Callable[[object, str], Expr]:
    return lambda deck, e: Sym(f"{e}.{prop}")


def _plates(deck: object, e: str) -> Expr:
    """0.97 (2 bf tf + (d - 2 tf) tw): the three plates of a W shape, less 3 % for rounding."""
    d, bf, tf, tw = (Sym(f"{e}.{p}") for p in ("d", "bf", "tf", "tw"))
    web = Mul((Add((d, Neg(Mul((_n(2), tf))))), tw))
    return Mul((_n(Fraction(97, 100)), Add((Mul((_n(2), bf, tf)), web))))


def _pretension(group: str) -> Callable[[object, str], Expr]:
    """0.70 Fu As with As = (pi/4)(d - 0.9743/n)^2: RCSC's definition of Tm (Section 5.4
    commentary) over the UNC tensile stress area."""
    def build(deck: object, e: str) -> Expr:
        d, n = Sym(f"{e}.d"), Sym(f"{e}.tpi")
        area = Mul((Div(Pi(), _n(4)), PowInt(Add((d, Neg(Div(_n(Fraction(9743, 10000)), n)))), 2)))
        return Mul((_n(Fraction(7, 10)), Sym(f"bolt_group.{group}.fu"), area))
    return build


def steel_relations(relation: type) -> tuple:
    """The steel deck's relations, built with consistency.Relation (passed in, so this
    module does not import the checker)."""
    R = relation
    eighth = _n(INCH / 8)
    return (
        R("aisc.modulus", "const.aisc360", _rec("E"), lambda deck, e: Sym("const.steel.E"), Fraction(1, 100)),
        R("bolt.edge_distance", "const.bolt_us.", _rec("edge_min"),
          lambda deck, e: Mul((_n(Fraction(5, 4)), Sym(f"{e}.d"))), Fraction(1, 4), "within"),
        R("bolt.hole_clears_bolt", "const.bolt_us.", _rec("d"), _rec("std"), Fraction(0), "le"),
        R("bolt.long_slot_length", "const.bolt_us.", _rec("lsl_l"),
          lambda deck, e: Mul((_n(Fraction(5, 2)), Sym(f"{e}.d"))), Fraction(0)),
        R("bolt.long_slot_width", "const.bolt_us.", _rec("lsl_w"), _rec("std"), Fraction(0)),
        R("bolt.nut_width", "const.bolt_us.", _rec("nut_F"),
          lambda deck, e: Add((Mul((_n(Fraction(3, 2)), Sym(f"{e}.d"))), eighth)), Fraction(0)),
        R("bolt.oversize_order", "const.bolt_us.", _rec("std"), _rec("ovs"), Fraction(0), "le"),
        R("bolt.pretension_g120", "const.bolt_us.", _rec("Tm_g120"), _pretension("120"), Fraction(25, 1000)),
        R("bolt.pretension_g150", "const.bolt_us.", _rec("Tm_g150"), _pretension("150"), Fraction(25, 1000)),
        R("bolt.short_slot_width", "const.bolt_us.", _rec("ssl_w"), _rec("std"), Fraction(0)),
        R("bolt_group.shear_ratio_n", "bolt_group.", _rec("Fnv_N"),
          lambda deck, e: Mul((_n(Fraction(45, 100)), Sym(f"{e}.fu"))), Fraction(1, 100)),
        R("bolt_group.shear_ratio_x", "bolt_group.", _rec("Fnv_X"),
          lambda deck, e: Mul((_n(Fraction(563, 1000)), Sym(f"{e}.fu"))), Fraction(1, 100)),
        R("bolt_group.tensile_ratio", "bolt_group.", _rec("Fnt"),
          lambda deck, e: Mul((_n(Fraction(3, 4)), Sym(f"{e}.fu"))), Fraction(1, 100)),
        R("shape.plate_area", "const.aisc_shapes_v16.W", _rec("A"), _plates, Fraction(9, 100), "within"),
        R("shape.weight", "const.aisc_shapes_v16.W", _rec("w"),
          lambda deck, e: Mul((Sym("const.steel.density"), Sym(f"{e}.A"))), Fraction(2, 100)),
    )
