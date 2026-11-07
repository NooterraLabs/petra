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
issuer; a value recalled from the AISC 360-22 text, which Petra has not been able to read
yet, is judged, owned by petra-maintainers, and its source says "recalled". Upgrading a row
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
MAINTAINERS = "petra-maintainers"
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


COMMON_NAMES: Mapping[str, tuple[str, ...]] = {
    "bolt_group.120": ("A325", "F1852"),
    "bolt_group.144": ("F3148",),
    "bolt_group.150": ("A490", "F2280"),
    "bolt_group.200": ("F3043", "F3111"),
    "bolt_group.A307": ("A307",),
    "steel.A36": ("A36",),
    "steel.A572_50": ("A572 Grade 50",),
    "steel.A992": ("A992",),
    "electrode.E70": ("E70", "E70XX"),
    "electrode.E80": ("E80", "E80XX"),
}
"""Registry id -> the designations an engineer writes for it, each one its standard text
names (AISC 360-22 Section J3.1 puts A325 and F1852 in Group 120, A490 and F2280 in Group
150). Registry.canonical maps each to its id, after `model.fold`, so "A572 Gr 50" and
A572_50 are A572 Grade 50. AISC's A325-N and A325-X are not names: the N and X say
whether the threads are included in or excluded from the shear planes, which a `bolts`
line states with `threads`."""


def steel_names() -> dict[str, str]:
    return {name: mid for mid, names in COMMON_NAMES.items() for name in names}


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
    ("aisc360.j2_2b.end_loaded_ratio", "100", "1", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(d)(1): an end-loaded fillet up to 100 times its size long counts its actual length; "
     f"{CHECKED}"),
    ("aisc360.j3_3.long_slot_plies", "1", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.3(f): long-slotted holes in only one of the connected parts at an individual faying surface; "
     f"{CHECKED}"),
    ("rcsc2025.joint_level.snug", "0", "1", JUDGED, MAINTAINERS,
     f"{RCSC}, Section 4: joint types ranked by what their installation guarantees, snug-tight 0 < pretensioned 1 < "
     "slip-critical 2 (each meets the requirements of the ones before it); the ranking is Petra's encoding, "
     "not checked against the published text"),
    ("rcsc2025.joint_level.pretensioned", "1", "1", JUDGED, MAINTAINERS,
     f"{RCSC}, Section 4: a pretensioned joint ranks 1 (above snug-tight, below slip-critical); Petra's encoding, "
     "not checked against the published text"),
    ("rcsc2025.joint_level.slip_critical", "2", "1", JUDGED, MAINTAINERS,
     f"{RCSC}, Section 4: a slip-critical joint ranks 2, the highest; Petra's encoding, not checked against the "
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


QUOTED = "checked against the Companion's use of it (P901-23W.pdf)"

COEFFICIENTS: tuple[_F, ...] = (
    ("aisc360.b4_1a.case1", "0.56", "1", SANCTIONED, "AISC",
     f"{AISC} Table B4.1a, Case 1: limiting width-to-thickness 0.56 sqrt(E/Fy) of a projecting plate, which "
     f"{MANUAL} Part 10 holds a seat stiffener to; {CHECKED}"),
    ("aisc360.b4_3b.hole_allowance", "1/16", "m", SANCTIONED, "AISC",
     f"{AISC} Section B4.3b: a bolt hole's width for net area is 1/16 in more than its nominal dimension; {CHECKED}"),
    ("aisc360.j2_2b.beta_intercept", "1.2", "1", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(d)(2), Eq. J2-1: beta = 1.2 - 0.002 (l/w); {CHECKED}"),
    ("aisc360.j2_2b.beta_slope", "0.002", "1", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(d)(2), Eq. J2-1: beta = 1.2 - 0.002 (l/w); {CHECKED}"),
    ("aisc360.j2_2b.end_loaded_cap", "300", "1", SANCTIONED, "AISC",
     f"{AISC} Section J2.2b(d)(2)-(3): beta applies up to 300 times the weld size; beyond, the effective length is "
     f"180 w, the value beta l takes at 300 w; {CHECKED}"),
    ("aisc360.j2_4.fnw", "0.60", "1", SANCTIONED, "AISC",
     f"{AISC} Section J2.4, Table J2.5: fillet weld metal Fnw = 0.60 FEXX; {CHECKED}"),
    ("aisc360.j3_8.intercept", "1.3", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.8, Eqs. J3-3a and J3-3b: F'nt = 1.3 Fnt - ...; {CHECKED}"),
    ("aisc360.j3_8.exemption", "0.30", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.8, User Note: combined stress need not be investigated where the required shear or tension "
     f"stress is at most 30% of the corresponding available stress; {CHECKED}"),
    ("aisc360.j3_10.ksc_asd", "1.5", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.10, Eq. J3-5b: ksc = 1 - 1.5 Ta / (Du Tb nb) (ASD); {CHECKED}"),
    ("aisc360.j3_11a.bearing_considered", "2.4", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.11a(1)(i), Eq. J3-6a: bearing 2.4 d t Fu, deformation a design consideration; {CHECKED}"),
    ("aisc360.j3_11a.tearout_considered", "1.2", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.11a(1)(i), Eq. J3-6c: tearout 1.2 lc t Fu, deformation a design consideration; {CHECKED}"),
    ("aisc360.j3_11a.bearing_not_considered", "3.0", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.11a(1)(ii), Eq. J3-6b: bearing 3.0 d t Fu, deformation not a design consideration; "
     f"{CHECKED}"),
    ("aisc360.j3_11a.tearout_not_considered", "1.5", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.11a(1)(ii), Eq. J3-6d: tearout 1.5 lc t Fu, deformation not a design consideration; "
     f"{CHECKED}"),
    ("aisc360.j3_11a.bearing_lsl_perpendicular", "2.0", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.11a(2), Eq. J3-6e: bearing 2.0 d t Fu at a long slot perpendicular to the force; {CHECKED}"),
    ("aisc360.j3_11a.tearout_lsl_perpendicular", "1.0", "1", SANCTIONED, "AISC",
     f"{AISC} Section J3.11a(2), Eq. J3-6f: tearout 1.0 lc t Fu at a long slot perpendicular to the force; "
     f"{CHECKED}"),
    ("aisc360.j4_2.shear", "0.60", "1", SANCTIONED, "AISC",
     f"{AISC} Section J4.2, Eqs. J4-3 and J4-4: shear yielding 0.60 Fy Agv, shear rupture 0.60 Fu Anv; {CHECKED}"),
    ("aisc360.j4_3.shear", "0.60", "1", SANCTIONED, "AISC",
     f"{AISC} Section J4.3, Eq. J4-5: block shear 0.60 Fu Anv + Ubs Fu Ant <= 0.60 Fy Agv + Ubs Fu Ant; {CHECKED}"),
    ("aisc360.j4_3.ubs_nonuniform", "0.5", "1", SANCTIONED, "AISC",
     f"{AISC} Section J4.3: Ubs = 0.5 where the tension stress is nonuniform (1 where uniform); {CHECKED}"),
    ("aisc360.j5_2.floor", "0.85", "1", SANCTIONED, "AISC",
     f"{AISC} Section J5.2(a): through fillers over 1/4 in thick a bolt's shear strength is multiplied by "
     f"1 - 0.4(t - 0.25), not less than 0.85; {CHECKED}"),
    ("aisc360.j7.milled", "1.8", "1", SANCTIONED, "AISC",
     f"{AISC} Section J7, Eq. J7-1: bearing on milled surfaces 1.8 Fy Apb; {CHECKED}"),
    ("aisc360.j10_1.coefficient", "6.25", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.1, Eq. J10-1: flange local bending 6.25 Fyf tf^2; {CHECKED}"),
    ("aisc360.j10_1.end_distance", "10", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.1: the strength is halved for a force less than 10 tf from the member end; {CHECKED}"),
    ("aisc360.j10_2.interior", "5", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.2, Eq. J10-2: web local yielding Fyw tw (5k + lb) away from the end; {CHECKED}"),
    ("aisc360.j10_2.end", "2.5", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.2, Eq. J10-3: web local yielding Fyw tw (2.5k + lb) within d of the end; {CHECKED}"),
    ("aisc360.j10_3.interior", "0.80", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.3, Eq. J10-4: web local crippling 0.80 tw^2 [...] away from the end; {CHECKED}"),
    ("aisc360.j10_3.end", "0.40", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.3, Eqs. J10-5a and J10-5b: web local crippling 0.40 tw^2 [...] near the end; {CHECKED}"),
    ("aisc360.j10_3.bearing", "3", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.3, Eqs. J10-4 and J10-5a: the term 3 (lb/d); {CHECKED}"),
    ("aisc360.j10_3.long_bearing", "4", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.3, Eq. J10-5b: the term (4 lb/d - 0.2); {CHECKED}"),
    ("aisc360.j10_3.long_offset", "0.2", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.3, Eq. J10-5b: the term (4 lb/d - 0.2), for lb/d > 0.2; {CHECKED}"),
    ("aisc360.j10_4.coefficient", "0.4", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.4, Eqs. J10-6 and J10-7: the term 0.4 [(h/tw)/(Lb/bf)]^3; {CHECKED}"),
    ("aisc360.j10_4.restrained_limit", "2.3", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.4(a): with the compression flange restrained, the limit state does not apply above "
     f"(h/tw)/(Lb/bf) = 2.3; {CHECKED}"),
    ("aisc360.j10_4.unrestrained_limit", "1.7", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.4(b): with the compression flange not restrained, the limit state does not apply above "
     f"(h/tw)/(Lb/bf) = 1.7; {CHECKED}"),
    ("aisc360.j10_5.coefficient", "24", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.5, Eq. J10-8: web compression buckling 24 tw^3 sqrt(E Fyw) / h; {CHECKED}"),
    ("aisc360.j10_6.coefficient", "0.60", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.6, Eqs. J10-9 and J10-10: panel-zone shear 0.60 Fy dc tw; {CHECKED}"),
    ("aisc360.j10_6.intercept", "1.4", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.6, Eq. J10-10: the factor (1.4 - alpha Pr / Py); {CHECKED}"),
    ("aisc360.j10_6.alpha_asd", "1.6", "1", SANCTIONED, "AISC",
     f"{AISC} Section J10.6: alpha = 1.6 (ASD), 1.0 (LRFD); {CHECKED}"),
    ("aisc360.f1.cantilever_cb", "1", "1", SANCTIONED, "AISC",
     f"{AISC} Section F1(c): Cb = 1.0 for a cantilever whose free end is unbraced, warping prevented at the support; "
     f"{CHECKED}"),
    ("aisc360.f11.inelastic_intercept", "1.52", "1", SANCTIONED, "AISC",
     f"{AISC} Section F11.2(b), Eq. F11-3: Cb [1.52 - 0.274 (Lb d/t^2)(Fy/E)] My; {CHECKED}"),
    ("aisc360.f11.inelastic_slope", "0.274", "1", SANCTIONED, "AISC",
     f"{AISC} Section F11.2(b), Eq. F11-3: Cb [1.52 - 0.274 (Lb d/t^2)(Fy/E)] My; {CHECKED}"),
    ("aisc360.f11.inelastic_limit", "1.9", "1", SANCTIONED, "AISC",
     f"{AISC} Section F11.2(b)-(c): Eq. F11-3 applies up to Lb d/t^2 = 1.9 E/Fy, Eq. F11-4 above; {CHECKED}"),
    ("aisc360.f11.elastic", "1.9", "1", SANCTIONED, "AISC",
     f"{AISC} Section F11.2(c), Eq. F11-5: Fcr = 1.9 E Cb / (Lb d/t^2); {CHECKED}"),
    ("aisc_manual.p9.k_coefficient", "2.2", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eqs. 9-19a and 9-19b: the plate buckling coefficient k = 2.2 (hc/c)^1.65 or 2.2 hc/c; {QUOTED}"),
    ("aisc_manual.p9.k_exponent", "1.65", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-19a: k = 2.2 (hc/c)^1.65 for c/hc <= 1; {QUOTED}"),
    ("aisc_manual.p9.k1_min", "1.61", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, coped beams: k1 = f k >= 1.61; {QUOTED}"),
    ("aisc_manual.p9.lambda_p", "0.475", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-18: lambda_p = 0.475 sqrt(k1 E / Fy); {QUOTED}"),
    ("aisc_manual.p9.cb_intercept", "3", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-21: Cb = [3 + ln(Lb/d)](1 - dct/d) >= 1.84; {QUOTED}"),
    ("aisc_manual.p9.cb_min", "1.84", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-21: Cb = [3 + ln(Lb/d)](1 - dct/d) >= 1.84; {QUOTED}"),
    ("aisc_manual.p9.a_limit", "1.25", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-23: a' = min(a, 1.25 b) + d/2; {QUOTED}"),
    ("aisc_manual.p9.tc", "4", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-30a: tc = sqrt(4 B b' / (phi p Fu)); {QUOTED}"),
    ("aisc_manual.p9.tributary", "1.75", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Figure 9-4: the flange length a bolt's prying acts on reaches at most 1.75 b either side of "
     f"it; {QUOTED} (Example II.D-1)"),
    ("aisc_manual.p9.tee_weld_coefficient", "0.0155", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-51: a shear tee welded to its support is ductile with fillets of at least wmin = "
     f"0.0155 (Fy tf^2 / b)(b^2 / l^2 + 2) <= (5/8) ts, Fy in ksi and lengths in inches; {QUOTED} (Example II.A-31)"),
    ("aisc_manual.p9.tee_weld_cap", "5/8", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-51: wmin = 0.0155 (Fy tf^2 / b)(b^2 / l^2 + 2) <= (5/8) ts; {QUOTED} (Example II.A-31)"),
    ("aisc_manual.p9.tee_bolt_coefficient", "0.0941", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-52: a shear tee bolted to its support is ductile with bolts of at least dmin = "
     f"0.0941 tf sqrt((Fy p / b)(b^2 / l^2 + 2)) <= 0.115 sqrt(Fy ts), Fy in ksi and lengths in inches; {QUOTED} "
     "(Example II.A-30)"),
    ("aisc_manual.p9.tee_bolt_cap", "0.115", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-52: dmin <= 0.115 sqrt(Fy ts), Fy in ksi and ts in inches; {QUOTED} (Example II.A-30)"),
    ("aisc_manual.p9.tee_flexibility", "2", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eqs. 9-51 and 9-52: the term (b^2 / l^2 + 2); {QUOTED} (Examples II.A-30 and II.A-31)"),
    ("aisc_manual.p9.tee_stem_allowance", "1/16", "m", SANCTIONED, "AISC",
     f"{MANUAL} Part 9, Eq. 9-53: a shear tee bolted to the beam web is ductile when the stem or the beam web is "
     f"at most d/2 + 1/16 in thick, the alternate to Eqs. 9-51 and 9-52; {QUOTED} (Examples II.A-30 and II.A-31)"),
    ("aisc_manual.p9.cope_length", "2", "1", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 9, coped beams: the method holds for a cope no longer than 2 d; {RECALLED}"),
    ("aisc_manual.p9.cope_depth", "1/2", "1", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 9, coped beams: the method holds for a cope no deeper than d/2; {RECALLED}"),
    ("aisc_manual.p10.extended_cb", "1.84", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 10, extended single-plate connections: the plate's buckling by {AISC} Section F11 with "
     f"Cb = 1.84; {QUOTED}"),
    ("aisc_manual.p10.fnv_divisor", "0.90", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 10, Eq. 10-7: Mmax = (Fnv / 0.90) Ab C'; {QUOTED}"),
    ("aisc_manual.p10.ductile_allowance", "1/16", "m", SANCTIONED, "AISC",
     f"{MANUAL} Part 10, Table 10-9: the plate or the beam web at most d/2 + 1/16 in thick; {QUOTED}"),
    ("aisc_manual.p10.weld_ratio", "5/8", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 10, single-plate connections: fillets on both faces of the plate, each at least 5/8 of its "
     f"thickness (Companion II.A-17A); {QUOTED}"),
    ("aisc_manual.p10.edge_ratio", "2", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 10, conventional single-plate connections: the horizontal edge distance Leh at least 2d on the "
     f"plate and the beam web (Companion II.A-17A); {QUOTED}"),
    ("aisc_manual.p10.underrun", "1/4", "m", SANCTIONED, "AISC",
     f"{MANUAL} Part 10: the length a beam may be delivered short, which the Companion takes off the beam web's end "
     f"distance and adds to a seat's setback in its strength checks (II.A-4, II.A-12A, II.A-14, II.A-28A); {QUOTED}"),
    ("aisc_manual.p10.conventional_a", "3.5", "m", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 10, conventional single-plate connections: the bolt line at most 3.5 in from the weld line; "
     f"{RECALLED}"),
    ("aisc_manual.p10.conventional_rows", "12", "1", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 10, Table 10-9: conventional single-plate connections of 2 to 12 bolt rows; {RECALLED}"),
    ("aisc_manual.t10_6.lever", "2.25", "1", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 10, the elastic method behind Table 10-6: R = v / (2 L^2) sqrt(L^2 + 20.25 e^2), so the "
     f"horizontal force per length is 2.25 v e / L^2; {RECALLED}"),
    ("aisc_manual.t10_8.eccentricity", "0.8", "1", JUDGED, MAINTAINERS,
     f"{MANUAL} Part 10, Table 10-8: the reaction on a stiffened seat at 0.8 W from the support face; {RECALLED}"),
    ("aisc_manual.p15.lambda_coefficient", "5", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15, Eq. 15-18: lambda = (b'/t) sqrt(Fy) / (5 sqrt(475 + 1120 (b'/a')^2)); {QUOTED}"),
    ("aisc_manual.p15.lambda_intercept", "475", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15, Eq. 15-18: lambda = (b'/t) sqrt(Fy) / (5 sqrt(475 + 1120 (b'/a')^2)); {QUOTED}"),
    ("aisc_manual.p15.lambda_slope", "1120", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15, Eq. 15-18: lambda = (b'/t) sqrt(Fy) / (5 sqrt(475 + 1120 (b'/a')^2)); {QUOTED}"),
    ("aisc_manual.p15.q_intercept", "1.34", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15: Q = 1.34 - 0.486 lambda for 0.70 < lambda <= 1.41; {QUOTED}"),
    ("aisc_manual.p15.q_slope", "0.486", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15: Q = 1.34 - 0.486 lambda for 0.70 < lambda <= 1.41; {QUOTED}"),
    ("aisc_manual.p15.q_slender", "1.30", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15, Eq. 15-16: Q = 1.30 / lambda^2 for lambda > 1.41; {QUOTED}"),
    ("aisc_manual.p15.lambda_slender", "1.41", "1", SANCTIONED, "AISC",
     f"{MANUAL} Part 15: the free edge's slenderness at which Q turns from 1.34 - 0.486 lambda to 1.30 / lambda^2; "
     f"{QUOTED}"),
    ("petra.strict.length", "1/1000000", "m", JUDGED, MAINTAINERS,
     f"{AISC} strict boundaries such as Section J10.2's 'x > d': Petra's shift of a length guard a millionth of an "
     "inch toward the excused side, so the stricter formula holds at the boundary and just past it, which only errs "
     "safe; Petra's encoding, not checked against the published text"),
    ("petra.strict.ratio", "1/1000000000", "1", JUDGED, MAINTAINERS,
     f"{AISC} strict boundaries such as Section F11.2(c)'s 'Lb d / t^2 > 1.9 E / Fy': Petra's shift of a "
     "dimensionless guard a billionth toward the excused side, which only errs safe; Petra's encoding, not checked "
     "against the published text"),
)
"""The numbers the provisions print, which limits.py and checks.py read by name (D5 of
docs/principles.md): each with its clause and tag, a value Petra has seen in the published
text sanctioned, one it recalls judged."""


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
    for name, text, unit, tag, owner, source in (*FACTORS, *COEFFICIENTS):
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
