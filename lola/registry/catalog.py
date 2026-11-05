"""Generate the makeable set from physics plus constants.py. Trusted.

Each generator maps a series from constants.py to registry entries whose derivable
properties are Derived expressions. Adding a size means adding one row to a series in
constants.py, never a row of computed values. Each formula is written once, as a
template over Sym("self.<prop>"), and shared by every entry it applies to:

  cable R20             = const.cu.rho20 / self.area                  (A = nominal area)
  cable k (adiabatic)   = sqrt(const.cu.qc * (const.cu.beta + 20) / const.cu.rho20
                               * ln((const.cu.beta + theta_f) / (const.cu.beta + theta_i)))
  bolt As               = (pi/4) * ((d2 + d3) / 2)^2,  d2, d3 from ISO 724 coefficients
  bolt proof load Fp    = Sp(class) * As
  CHS area A            = (pi/4) * (D^2 - (D - 2t)^2)
  CHS second moment I   = (pi/64) * (D^4 - (D - 2t)^4)
  steel G               = E / (2 (1 + nu))

A size entry (a cable size) names its series and defines the series parameters as
Derived references to the constants it was cut from, so Registry.expand of
"cable.cu_pvc_2_5" R20 is const.cu.rho20 / const.iec60228.2_5.area.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from ..kernel import Add, Const, Div, Expr, Ln, Mul, Neg, Pi, PowInt, Sqrt, Sym
from .constants import CABLE_SIZES, CHS_SIZES, CONSTANTS, MCB_RATINGS, STATED, THREADS, chs_key
from .model import (
    Corrosivity,
    Derived,
    Environment,
    Material,
    Part,
    PartKind,
    Process,
    ProcessKind,
    Property,
    PropertyEffect,
    Registry,
)


def _own(prop: str) -> Sym:
    return Sym(f"self.{prop}")


def _c(name: str) -> Sym:
    return Sym(f"const.{name}")


def _n(value: int | str) -> Const:
    return Const(Fraction(value))


def constant(name: str) -> Derived:
    """A property that is one constant, so its premise is that constant."""
    c = CONSTANTS[name]
    return Derived(_c(name), c.unit, note=c.source)


def _minus(a: Expr, b: Expr) -> Expr:
    return Add((a, Neg(b)))


SHEAR_MODULUS = Derived(Div(_own("E"), Mul((_n(2), Add((_n(1), _own("nu")))))), "Pa",
                        note="isotropic elasticity: G = E / (2 (1 + nu))")

STRESS_AREA = Derived(
    Mul((Div(Pi(), _n(4)), PowInt(Div(Add((
        _minus(_own("d"), Mul((_c("iso724.d2_coefficient"), _own("pitch")))),
        _minus(_own("d"), Mul((_c("iso724.d3_coefficient"), _own("pitch")))),
    )), _n(2)), 2))),
    "m2",
    note="ISO 898-1:2013 9.1.6.1: As,nom = (pi/4) ((d2 + d3) / 2)^2, d2 = d - 0.649519 P, d3 = d - 1.226869 P",
)

PROOF_LOAD = Derived(Mul((_own("Sp"), _own("As"))), "N", note="ISO 898-1:2013: proof load Fp = Sp As,nom")

_D_INNER = _minus(_own("D"), Mul((_n(2), _own("t"))))
CHS_AREA = Derived(Mul((Div(Pi(), _n(4)), _minus(PowInt(_own("D"), 2), PowInt(_D_INNER, 2)))), "m2",
                   note="annulus: A = (pi/4) (D^2 - (D - 2t)^2)")
CHS_SECOND_MOMENT = Derived(Mul((Div(Pi(), _n(64)), _minus(PowInt(_own("D"), 4), PowInt(_D_INNER, 4)))), "m4",
                            note="annulus: I = (pi/64) (D^4 - (D - 2t)^4)")

CABLE_SERIES_PROPS: Mapping[str, Derived] = {
    "R20": Derived(Div(_c("cu.rho20"), _own("area")), "ohm/m",
                   note="conductor of the nominal area: R20 = rho20 / A"),
    "alpha": constant("cu.alpha20"),
    "theta_max": constant("pvc.theta_max"),
    "theta_sc": constant("pvc.theta_sc"),
    "k": Derived(
        Sqrt(Mul((
            Div(Mul((_c("cu.qc"), Add((_c("cu.beta"), _n(20))))), _c("cu.rho20")),
            Ln(Div(Add((_c("cu.beta"), _own("theta_sc"))), Add((_c("cu.beta"), _own("theta_max"))))),
        ))),
        "A s0.5/m2",
        note="IEC 60949:1988 adiabatic heating: k = sqrt(qc (beta + 20) / rho20 ln((beta + theta_f) / (beta + theta_i)))",
    ),
    "conductor_diameter": Derived(Sqrt(Div(Mul((_n(4), _own("area"))), Pi())), "m",
                                  note="solid round conductor of the nominal area"),
    "outer_diameter": Derived(Add((_own("conductor_diameter"), Mul((_n(2), _own("insulation"))))), "m",
                              note="conductor plus two insulation thicknesses"),
    "thermal_resistivity": constant("pvc.thermal_resistivity"),
    "T1": Derived(
        Mul((Div(_own("thermal_resistivity"), Mul((_n(2), Pi()))),
             Ln(Div(_own("outer_diameter"), _own("conductor_diameter"))))),
        "K m/W",
        note="IEC 60287-2-1 single-core insulation: T1 = rho_T / (2 pi) ln(1 + 2 t1 / dc)",
    ),
}
"""Series "cable.cu_pvc". Open parameters: area and insulation (thickness)."""

BREAKER_PROPS: Mapping[str, Derived] = {
    "I_nt": Derived(Mul((_c("iec60898_1.nontrip_factor"), _own("In"))), "A",
                    note="IEC 60898-1 conventional non-tripping current"),
    "I_t": Derived(Mul((_c("iec60898_1.trip_factor"), _own("In"))), "A",
                   note="IEC 60898-1 conventional tripping current"),
}


def build_registry() -> Registry:
    """The default makeable set. Pure; same output every call."""
    return Registry(
        constants=CONSTANTS,
        materials={**structural_steels(), **aluminium_alloys(), **conductors_and_insulation(), **fastener_steels()},
        parts={**chs_sections(), **cables(), **breakers(), **terminals(), **metric_bolts()},
        processes=processes(),
        environments=environments(),
    )


def structural_steels() -> Mapping[str, Material]:
    return {
        "steel.S355": Material("steel.S355", "steel", "EN 10025-2:2019", {
            "fy": STATED["en10025_2.S355.fy"],
            "fu": STATED["en10025_2.S355.fu"],
            "E": constant("steel.E"),
            "nu": constant("steel.nu"),
            "G": SHEAR_MODULUS,
            "density": constant("steel.density"),
            "anodic_index": STATED["anodic.carbon_steel"],
        }),
    }


def aluminium_alloys() -> Mapping[str, Material]:
    return {
        "aluminium.6061_T6": Material("aluminium.6061_T6", "aluminium", "EN 573-3 EN AW-6061, temper T6", {
            "fy": STATED["6061_T6.fy"],
            "fu": STATED["6061_T6.fu"],
            "E": constant("aluminium.E"),
            "nu": constant("aluminium.nu"),
            "G": SHEAR_MODULUS,
            "density": constant("aluminium.density"),
            "anodic_index": STATED["anodic.wrought_aluminium"],
        }),
    }


def conductors_and_insulation() -> Mapping[str, Material]:
    return {
        "copper.cu_etp": Material("copper.cu_etp", "copper", "IEC 60028:1925", {
            "rho20": constant("cu.rho20"),
            "alpha20": constant("cu.alpha20"),
            "beta": constant("cu.beta"),
            "qc": constant("cu.qc"),
            "anodic_index": STATED["anodic.copper"],
        }),
        "pvc.general_70C": Material("pvc.general_70C", "pvc", "IEC 60227-1, insulation compound PVC/C", {
            "thermal_resistivity": constant("pvc.thermal_resistivity"),
            "theta_max": constant("pvc.theta_max"),
            "theta_sc": constant("pvc.theta_sc"),
        }),
    }


def fastener_steels() -> Mapping[str, Material]:
    """Bolt materials. Their strengths belong to the property class, so they live on the
    bolt parts; the material carries what the class does not fix."""
    return {
        "steel.bolt_qt": Material("steel.bolt_qt", "steel", "ISO 898-1:2013, quenched and tempered steel", {
            "E": constant("steel.E"),
            "anodic_index": STATED["anodic.carbon_steel"],
        }),
        "stainless.A4": Material("stainless.A4", "stainless", "ISO 3506-1:2020, austenitic grade A4", {
            "anodic_index": STATED["anodic.stainless_18cr"],
        }),
    }


def chs_sections() -> Mapping[str, Part]:
    sections = {}
    for d, t in CHS_SIZES:
        key = chs_key(d, t)
        sections[f"chs.{key}"] = Part(f"chs.{key}", PartKind.SECTION, f"EN 10219-2 CHS {d} x {t}", "steel.S355", {
            "D": constant(f"en10219_2.{key}.D"),
            "t": constant(f"en10219_2.{key}.t"),
            "A": CHS_AREA,
            "I": CHS_SECOND_MOMENT,
        })
    return sections


def cables() -> Mapping[str, Part]:
    """A series entry per insulation ("cable.cu_pvc") whose props are Derived over two
    series parameters, Sym("self.area") and Sym("self.insulation"), plus one size entry
    per IEC 60228 size ("cable.cu_pvc_2_5") that fixes both. Props: R20, alpha,
    theta_max, theta_sc, k, conductor_diameter, outer_diameter, thermal_resistivity, T1.

    A size defines area and insulation as references to the constants they came from,
    so Registry.expand gives a concrete wire and the series family the same statement
    shape and the library can match them."""
    series = "cable.cu_pvc"
    parts = {series: Part(series, PartKind.CABLE, "copper conductor, IEC 60228 class 2, PVC insulated, single core",
                          "copper.cu_etp", CABLE_SERIES_PROPS)}
    for key, area, insulation in CABLE_SIZES:
        area_name, insulation_name = f"iec60228.{key}.area", f"iec60227_3.{key}.insulation"
        parts[f"{series}_{key}"] = Part(
            f"{series}_{key}", PartKind.CABLE, f"{area} mm2 copper, PVC insulated (type 60227 IEC 01)", "copper.cu_etp",
            {"area": constant(area_name), "insulation": constant(insulation_name)},
            series=series,
            fixes={"area": CONSTANTS[area_name].value, "insulation": CONSTANTS[insulation_name].value},
        )
    return parts


def breakers() -> Mapping[str, Part]:
    """IEC 60898-1 type B MCBs. Props: In (stated), I_nt = 1.13 In and I_t = 1.45 In
    (derived from the IEC 60898-1 constants), Icn and the let-through I2t at Icn (stated,
    energy-limiting class 3 maximum)."""
    parts = {}
    for rating in MCB_RATINGS:
        energy = "In_le_16" if int(rating) <= 16 else "In_le_32"
        parts[f"mcb.B{rating}"] = Part(f"mcb.B{rating}", PartKind.BREAKER, f"IEC 60898-1 type B, {rating} A, 6 kA",
                                       "copper.cu_etp", {
                                           "In": STATED[f"iec60898_1.B{rating}.In"],
                                           **BREAKER_PROPS,
                                           "Icn": STATED["iec60898_1.Icn_6000"],
                                           "I2t": STATED[f"en60898_1.class3.{energy}.I2t"],
                                       })
    return parts


def terminals() -> Mapping[str, Part]:
    """Props: temperature_max (stated rating to IEC 60998), current_max, and the
    conductor size range conductor_min to conductor_max."""
    parts = {}
    for name, designation in (
        ("lever_4mm2_75C", "lever terminal, 0.2 to 4 mm2, 32 A, 75 degC"),
        ("screw_16mm2_75C", "screw terminal, 1.5 to 16 mm2, 76 A, 75 degC"),
    ):
        props = {p: STATED[f"terminal.{name}.{p}"] for p in ("temperature_max", "current_max", "conductor_min", "conductor_max")}
        parts[f"terminal.{name}"] = Part(f"terminal.{name}", PartKind.TERMINAL, designation, "copper.cu_etp", props)
    return parts


_BOLT_GRADES: tuple[tuple[str, str, str, str | None], ...] = (
    ("8_8", "8.8", "steel.bolt_qt", None),
    ("8_8_zn", "8.8", "steel.bolt_qt", "process.zinc_plate"),
    ("10_9", "10.9", "steel.bolt_qt", None),
    ("10_9_zn", "10.9", "steel.bolt_qt", "process.zinc_plate"),
    ("A4_70", "A4-70", "stainless.A4", None),
)
"""(id suffix, property class, material, coating process)."""


def _class_ratings(grade: str, d_mm: str) -> dict[str, Property]:
    if grade == "A4-70":
        return {p: STATED[f"iso3506_1.A4_70.{p}"] for p in ("Rm_min", "Rp02_min")}
    key = "iso898_1.10_9" if grade == "10.9" else f"iso898_1.8_8.{'small' if Fraction(d_mm) <= 16 else 'large'}"
    ratio = "iso898_1.10_9.yield_ratio" if grade == "10.9" else "iso898_1.8_8.yield_ratio"
    return {
        **{p: STATED[f"{key}.{p}"] for p in ("Rm_min", "Rp02_min", "Sp")},
        "Fp": PROOF_LOAD,
        "class_yield_ratio": constant(ratio),
    }


def metric_bolts() -> Mapping[str, Part]:
    """One part per ISO 261 coarse thread and grade. Props: d, pitch, As (derived from
    ISO 724 geometry), the class minimums Rm_min and Rp02_min (stated), and for ISO 898-1
    classes Sp (stated), Fp = Sp As, and class_yield_ratio."""
    parts = {}
    for size, d_mm, p_mm in THREADS:
        for suffix, grade, material, coating in _BOLT_GRADES:
            pid = f"bolt.{size}_{suffix}"
            finish = ", zinc plated" if coating else ""
            parts[pid] = Part(pid, PartKind.BOLT, f"{size}x{p_mm} property class {grade}{finish}", material, {
                "d": constant(f"iso261.{size}.d"),
                "pitch": constant(f"iso261.{size}.pitch"),
                "As": STRESS_AREA,
                **_class_ratings(grade, d_mm),
            }, process=coating)
    return parts


def processes() -> Mapping[str, Process]:
    """Install methods (the surface heat-transfer coefficient that sets the external
    thermal resistance per metre), coatings, welds."""
    return {
        "install.clipped_direct": Process("install.clipped_direct", ProcessKind.INSTALL,
                                          {"h": constant("install.clipped_direct.h")}),
        "process.zinc_plate": Process("process.zinc_plate", ProcessKind.COATING,
                                      {"anodic_index": STATED["anodic.zinc_plate"]}),
        "process.mig_weld_6xxx": Process("process.mig_weld_6xxx", ProcessKind.WELD, {}, effects=(
            PropertyEffect("aluminium", "fy", STATED["weld.mig_6xxx_T6.haz_fy_factor"],
                           "within 30 mm of the weld for plates 6 mm < t <= 12 mm (EN 1999-1-1 6.1.6.3, not checked)"),
        )),
    }


def environments() -> Mapping[str, Environment]:
    """indoor_dry (C1), outdoor_c3 (C3), marine_c5 (C5, wet)."""
    return {
        "indoor_dry": Environment("indoor_dry", STATED["iec60364_5_51.AA5"], Corrosivity.C1, wet=False),
        "outdoor_c3": Environment("outdoor_c3", STATED["iec60364_5_51.AA7"], Corrosivity.C3, wet=True),
        "marine_c5": Environment("marine_c5", STATED["iec60364_5_51.AA7"], Corrosivity.C5, wet=True),
    }
