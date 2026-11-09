"""The short list of numbers the makeable set is computed from. Trusted; each one is a
premise with a tag, an owner and a source.

CONSTANTS holds every number a derivation in catalog.py reads: physical constants, the
size series (thread, conductor and section dimensions) and the coefficients standards
define. STATED holds the values no formula derives (spec minimums, product ratings,
tabulated classifications); catalog.py attaches each to the entries it describes as a
Stated property. Adding a size means adding one row to a series below.

Values are exact rationals parsed from decimal text, in SI base units (degC for
temperature). A value a standard fixes is tagged sanctioned and its owner is the issuing
body. A value we could not check against the published text is tagged judged, owned by
petra-maintainers, and its source says so. A range that widens a standard's point value
(steel E in [200, 210] GPa around EN 1993-1-1's 210 GPa) is still sanctioned: the
standard's value lies inside it, so the premise is implied by the standard.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from ..kernel import Interval
from ..premises import Tag
from .model import Constant, Erratum, Stated

SANCTIONED, JUDGED = Tag.SANCTIONED, Tag.JUDGED
MAINTAINERS = "petra-maintainers"

MM = Fraction(1, 1000)
MM2 = Fraction(1, 10**6)
OHM_MM2_PER_KM = Fraction(1, 10**9)   # ohm/km times mm2, in ohm m
STANDARD_GRAVITY = Fraction("9.80665")   # m/s2, the CGPM 1901 conventional value
MPA = Fraction(10**6)
GPA = Fraction(10**9)


def _iv(lo: str, hi: str | None = None, scale: Fraction = Fraction(1)) -> Interval:
    low = Fraction(lo) * scale
    return Interval(low, Fraction(hi) * scale if hi is not None else low)


# --- Size series -----------------------------------------------------------------------

THREADS: tuple[tuple[str, str, str], ...] = (
    ("M6", "6", "1"),
    ("M8", "8", "1.25"),
    ("M10", "10", "1.5"),
    ("M12", "12", "1.75"),
    ("M16", "16", "2"),
    ("M20", "20", "2.5"),
    ("M24", "24", "3"),
)
"""ISO 261 coarse threads: (designation, nominal diameter d in mm, pitch P in mm)."""

CABLE_SIZES: tuple[tuple[str, str, str, str], ...] = (
    ("1_5", "1.5", "0.7", "12.1"),
    ("2_5", "2.5", "0.8", "7.41"),
    ("4", "4", "0.8", "4.61"),
    ("6", "6", "0.8", "3.08"),
    ("10", "10", "1.0", "1.83"),
    ("16", "16", "1.0", "1.15"),
)
"""(size key, IEC 60228 nominal area in mm2, IEC 60227-3 type 01 insulation thickness in mm,
IEC 60228 Table 2 maximum resistance at 20 degC of the class 2 plain copper conductor in
ohm/km)."""

CHS_SIZES: tuple[tuple[str, str], ...] = (
    ("48.3", "3.2"),
    ("60.3", "3.2"),
    ("76.1", "3.2"),
    ("88.9", "3.2"),
    ("88.9", "4"),
    ("114.3", "3.6"),
)
"""EN 10219-2 circular hollow sections: (outside diameter D in mm, wall thickness t in mm)."""

MCB_RATINGS: tuple[str, ...] = ("6", "10", "16", "20", "32")
"""IEC 60898-1 rated currents In in A of the type B breakers in the catalogue."""


def size_key(text: str) -> str:
    """"60.3" -> "60_3": decimal points cannot appear inside an id segment."""
    return text.replace(".", "_")


def chs_key(d: str, t: str) -> str:
    return f"{size_key(d)}x{size_key(t)}"


# --- Constants -------------------------------------------------------------------------

def _constants() -> dict[str, Constant]:
    rows: list[Constant] = [
        Constant("cu.rho20", _iv("1", scale=Fraction(1, 58) * MM2), "ohm m", SANCTIONED, "IEC",
                 "IEC 60028:1925, standard annealed copper: resistivity 1/58 ohm mm2/m at 20 degC",
                 "annealed copper has resistivity 1/58 ohm mm2/m at 20 degC"),
        Constant("cu.alpha20", _iv("0.00393"), "1/K", SANCTIONED, "IEC",
                 "IEC 60028:1925, standard annealed copper: temperature coefficient of resistance 0.00393 /K at 20 degC",
                 "annealed copper's resistance rises by 0.00393 of its 20 degC value per kelvin"),
        Constant("cu.beta", _iv("234.5"), "K", SANCTIONED, "IEC",
                 "IEC 60949:1988 Table 1, copper: reciprocal of the temperature coefficient of resistance at 0 degC, 234.5 K",
                 "copper's resistance extrapolates to zero at -234.5 degC"),
        Constant("cu.qc", _iv("3.45e6"), "J/(K m3)", SANCTIONED, "IEC",
                 "IEC 60949:1988 Table 1, copper: volumetric specific heat 3.45e6 J/(K m3) at 20 degC",
                 "copper stores 3.45 MJ per cubic metre per kelvin"),
        Constant("pvc.thermal_resistivity", _iv("5"), "K m/W", SANCTIONED, "IEC",
                 "IEC 60287-2-1:2015 Table 1, PVC insulation of low-voltage cables: 5.0 K m/W",
                 "PVC insulation conducts heat with thermal resistivity 5.0 K m/W"),
        Constant("pvc.theta_max", _iv("70"), "degC", SANCTIONED, "IEC",
                 "IEC 60364-5-52:2009 Table 52.1, PVC insulation: maximum conductor operating temperature 70 degC",
                 "a PVC-insulated conductor may run continuously at up to 70 degC"),
        Constant("pvc.theta_sc", _iv("160"), "degC", SANCTIONED, "IEC",
                 "IEC 60364-4-43:2008 Table 43A, PVC insulation up to 300 mm2: final short-circuit temperature 160 degC",
                 "a PVC-insulated conductor may reach 160 degC at the end of a short circuit"),
        Constant("steel.E", _iv("200", "210", GPA), "Pa", SANCTIONED, "CEN",
                 "EN 1993-1-1:2005 3.2.6(1) fixes E = 210000 N/mm2; the range widens it down to 200 GPa",
                 "the elastic modulus of structural steel lies in [200, 210] GPa"),
        Constant("steel.nu", _iv("0.3"), "1", SANCTIONED, "CEN",
                 "EN 1993-1-1:2005 3.2.6(1): Poisson's ratio in the elastic range 0.3",
                 "structural steel has Poisson's ratio 0.3"),
        Constant("en1993_1_1.curve_c.alpha", _iv("0.49"), "1", SANCTIONED, "CEN",
                 "EN 1993-1-1:2005 Table 6.1: imperfection factor of flexural buckling curve c, alpha = 0.49",
                 "buckling curve c has imperfection factor 0.49"),
        Constant("en1993_1_1.class3_tube_limit", _iv("90"), "1", SANCTIONED, "CEN",
                 "EN 1993-1-1:2005 Table 5.2 (sheet 3 of 3), tubular sections in compression: class 3 when d / t <= 90 eps^2",
                 "a tube is class 3 or better in compression when d / t <= 90 eps^2"),
        Constant("en1993_1_1.epsilon_reference_fy", _iv("235", scale=MPA), "Pa", SANCTIONED, "CEN",
                 "EN 1993-1-1:2005 Table 5.2: eps = sqrt(235 / fy) with fy in N/mm2",
                 "the slenderness limits of EN 1993-1-1 Table 5.2 scale with 235 MPa / fy"),
        Constant("steel.density", _iv("77000", "78500", 1 / STANDARD_GRAVITY), "kg/m3", JUDGED, MAINTAINERS,
                 "EN 1991-1-1:2002 Table A.4, steel: unit weight 77.0 to 78.5 kN/m3, over standard gravity "
                 "9.80665 m/s2; the range is the source's own; recalled and not checked against the published text",
                 "structural steel has density 7851.8 to 8004.8 kg/m3 (unit weight 77.0 to 78.5 kN/m3)",
                 errata=(Erratum("2026-11-06", "7850 kg/m3, a conventional point value below the range its own "
                                 "source states (77.0 kN/m3 is 7851.8 kg/m3 at standard gravity)",
                                 "the range EN 1991-1-1 Table A.4 states, 77.0 to 78.5 kN/m3, over standard gravity: "
                                 "[7851.8, 8004.8] kg/m3, so a self-weight is checked at the heaviest steel the "
                                 "source allows"),)),
        Constant("aluminium.E", _iv("68", "70", GPA), "Pa", SANCTIONED, "CEN",
                 "EN 1999-1-1:2007 3.2.5(1) fixes E = 70000 N/mm2; the range widens it down to 68 GPa "
                 "to cover 6061-T6 handbook values",
                 "the elastic modulus of wrought aluminium alloys lies in [68, 70] GPa"),
        Constant("aluminium.nu", _iv("0.3", "0.33"), "1", SANCTIONED, "CEN",
                 "EN 1999-1-1:2007 3.2.5(1) fixes nu = 0.3; the range widens it to the 6061-T6 handbook value 0.33",
                 "wrought aluminium alloys have Poisson's ratio in [0.30, 0.33]"),
        Constant("aluminium.density", _iv("2700"), "kg/m3", SANCTIONED, "CEN",
                 "EN 1999-1-1:2007 3.2.5(1): unit mass 2700 kg/m3",
                 "wrought aluminium alloys have density 2700 kg/m3"),
        # Gravity, which turns a member's mass into its self-weight (models/truss.py).
        Constant("earth.gravity", _iv("9.76", "9.84"), "m/s2", JUDGED, MAINTAINERS,
                 "WGS 84 normal gravity at sea level runs from 9.7803 m/s2 at the equator to 9.8322 m/s2 at the "
                 "poles (NIMA TR8350.2); the range widens it for the altitude of the highest summits and for local "
                 "anomalies, and holds the standard acceleration 9.80665 m/s2 (CGPM 1901); recalled and not "
                 "checked against the published text",
                 "the acceleration of gravity at any site on the Earth's surface lies in [9.76, 9.84] m/s2"),
        Constant("iso724.d2_coefficient", _iv("0.649519"), "1", SANCTIONED, "ISO",
                 "ISO 724:1993 basic dimensions: d2 = d - 2 x 3/8 H with H = (sqrt 3 / 2) P from ISO 68-1, "
                 "so the coefficient is 3 sqrt 3 / 8 = 0.64951905, rounded to six places",
                 "the basic pitch diameter of an ISO metric thread is d - 0.649519 P"),
        Constant("iso724.d3_coefficient", _iv("1.226869"), "1", SANCTIONED, "ISO",
                 "ISO 898-1:2013 9.1.6.1: d3 = d1 - H/6 with d1 = d - 2 x 5/8 H (ISO 724), "
                 "so the coefficient is 17 sqrt 3 / 24 = 1.22686932, rounded to six places",
                 "the minor diameter of an ISO metric external thread is d - 1.226869 P"),
        Constant("iso898_1.8_8.yield_ratio", _iv("0.8"), "1", SANCTIONED, "ISO",
                 "ISO 898-1:2013 clause 4, designation system: the second number of class 8.8 is 10 times the yield ratio",
                 "property class 8.8 has nominal yield ratio 0.8"),
        Constant("iso898_1.10_9.yield_ratio", _iv("0.9"), "1", SANCTIONED, "ISO",
                 "ISO 898-1:2013 clause 4, designation system: the second number of class 10.9 is 10 times the yield ratio",
                 "property class 10.9 has nominal yield ratio 0.9"),
        Constant("iec60898_1.nontrip_factor", _iv("1.13"), "1", SANCTIONED, "IEC",
                 "IEC 60898-1:2015 Table 7, test a: conventional non-tripping current 1.13 In (table number not checked)",
                 "a breaker carries 1.13 In for the conventional time without tripping"),
        Constant("iec60898_1.trip_factor", _iv("1.45"), "1", SANCTIONED, "IEC",
                 "IEC 60898-1:2015 Table 7, test b: conventional tripping current 1.45 In (table number not checked)",
                 "a breaker trips within the conventional time at 1.45 In"),
        Constant("iec60364_4_43.overload_factor", _iv("1.45"), "1", SANCTIONED, "IEC",
                 "IEC 60364-4-43:2008 433.1, second condition I2 <= 1.45 Iz (formula number not checked)",
                 "a device's conventional tripping current I2 may be at most 1.45 times the conductor's "
                 "current-carrying capacity Iz"),
        Constant("install.clipped_direct.h", _iv("5", "10"), "W/(m2 K)", JUDGED, MAINTAINERS,
                 "combined convection and radiation coefficient of a PVC cable clipped direct to a wall in still "
                 "indoor air, judged by petra-maintainers; not taken from a standard",
                 "a cable clipped direct sheds heat to the air at 5 to 10 W/(m2 K)"),
    ]
    for name, d, p in THREADS:
        rows.append(Constant(f"iso261.{name}.d", _iv(d, scale=MM), "m", SANCTIONED, "ISO",
                             f"ISO 261:1998 Table 1: {name} has nominal diameter {d} mm (the designation)",
                             f"an {name} thread has nominal diameter {d} mm"))
        rows.append(Constant(f"iso261.{name}.pitch", _iv(p, scale=MM), "m", SANCTIONED, "ISO",
                             f"ISO 261:1998 Table 1: coarse pitch of {name} is {p} mm",
                             f"an {name} coarse thread has pitch {p} mm"))
    for key, area, insulation, _ in CABLE_SIZES:
        rows.append(Constant(f"iec60228.{key}.area", _iv(area, scale=MM2), "m2", SANCTIONED, "IEC",
                             f"IEC 60228:2004 Table 2, class 2 conductor: nominal cross-sectional area {area} mm2 "
                             "(the size designation)",
                             f"a {area} mm2 conductor has nominal area {area} mm2"))
        rows.append(Constant(f"iec60227_3.{key}.insulation", _iv(insulation, scale=MM), "m", JUDGED, MAINTAINERS,
                             f"IEC 60227-3:1993 Table 1 (type 60227 IEC 01): nominal insulation thickness {insulation} mm "
                             f"for {area} mm2, recalled and not checked against the published table",
                             f"a {area} mm2 PVC single-core cable has {insulation} mm of insulation"))
    for d, t in CHS_SIZES:
        key = chs_key(d, t)
        rows.append(Constant(f"en10219_2.{key}.D", _iv(d, scale=MM), "m", SANCTIONED, "CEN",
                             f"EN 10219-2:2006, CHS {d} x {t}: nominal outside diameter {d} mm (the designation)",
                             f"CHS {d} x {t} has outside diameter {d} mm"))
        rows.append(Constant(f"en10219_2.{key}.t", _iv(t, scale=MM), "m", SANCTIONED, "CEN",
                             f"EN 10219-2:2006, CHS {d} x {t}: nominal wall thickness {t} mm (the designation)",
                             f"CHS {d} x {t} has wall thickness {t} mm"))
    table = {c.name: c for c in rows}
    if len(table) != len(rows):
        raise RuntimeError("a constant is defined twice")
    return table


CONSTANTS: Mapping[str, Constant] = _constants()


# --- Stated values ---------------------------------------------------------------------

def _stated() -> dict[str, Stated]:
    recalled = "recalled and not checked against the published text"
    anodic = "anodic index in the table commonly reproduced after MIL-STD-889, " + recalled
    table: dict[str, Stated] = {
        "en10025_2.S355.fy": Stated(_iv("355", scale=MPA), "Pa", SANCTIONED, "CEN", "EN 10025-2:2019 Table 7",
                                    "minimum upper yield strength ReH, nominal thickness <= 16 mm"),
        "en10025_2.S355.fu": Stated(_iv("470", "630", MPA), "Pa", SANCTIONED, "CEN", "EN 10025-2:2019 Table 7",
                                    "tensile strength Rm, 3 mm <= nominal thickness <= 100 mm"),
        "6061_T6.fy": Stated(_iv("240", scale=MPA), "Pa", JUDGED, MAINTAINERS,
                             "EN 485-2 and ASTM B209 minimum 0.2 % proof strength of 6061-T6 and T651 plate, " + recalled,
                             "minimum 0.2 % proof strength, plate up to 12.5 mm"),
        "6061_T6.fu": Stated(_iv("290", scale=MPA), "Pa", JUDGED, MAINTAINERS,
                             "EN 485-2 and ASTM B209 minimum tensile strength of 6061-T6 and T651 plate, " + recalled,
                             "minimum tensile strength, plate up to 12.5 mm"),
        "iso898_1.8_8.small.Rm_min": Stated(_iv("800", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                            "property class 8.8, d <= 16 mm: minimum tensile strength"),
        "iso898_1.8_8.small.Rp02_min": Stated(_iv("640", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                              "property class 8.8, d <= 16 mm: minimum 0.2 % proof stress"),
        "iso898_1.8_8.small.Sp": Stated(_iv("580", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                        "property class 8.8, d <= 16 mm: proof stress"),
        "iso898_1.8_8.large.Rm_min": Stated(_iv("830", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                            "property class 8.8, d > 16 mm: minimum tensile strength"),
        "iso898_1.8_8.large.Rp02_min": Stated(_iv("660", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                              "property class 8.8, d > 16 mm: minimum 0.2 % proof stress"),
        "iso898_1.8_8.large.Sp": Stated(_iv("600", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                        "property class 8.8, d > 16 mm: proof stress"),
        "iso898_1.10_9.Rm_min": Stated(_iv("1040", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                       "property class 10.9: minimum tensile strength"),
        "iso898_1.10_9.Rp02_min": Stated(_iv("940", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                         "property class 10.9: minimum 0.2 % proof stress"),
        "iso898_1.10_9.Sp": Stated(_iv("830", scale=MPA), "Pa", SANCTIONED, "ISO", "ISO 898-1:2013 Table 3",
                                   "property class 10.9: proof stress"),
        "iso3506_1.A4_70.Rm_min": Stated(_iv("700", scale=MPA), "Pa", SANCTIONED, "ISO",
                                         "ISO 3506-1:2020, austenitic grades, property class 70 (table number not checked)",
                                         "A4-70, d <= M24: minimum tensile strength"),
        "iso3506_1.A4_70.Rp02_min": Stated(_iv("450", scale=MPA), "Pa", SANCTIONED, "ISO",
                                           "ISO 3506-1:2020, austenitic grades, property class 70 (table number not checked)",
                                           "A4-70, d <= M24: minimum stress at 0.2 % non-proportional elongation"),
        "iec60898_1.Icn_6000": Stated(_iv("6000"), "A", SANCTIONED, "IEC",
                                      "IEC 60898-1:2015, standard value of rated short-circuit capacity, marked on the "
                                      "device (clause not checked)",
                                      "rated short-circuit capacity Icn 6000 A"),
        "en60898_1.class3.In_le_16.I2t": Stated(_iv("35000"), "A2s", JUDGED, MAINTAINERS,
                                                "EN 60898-1 Annex ZA, energy-limiting class 3, type B, In <= 16 A, at "
                                                "6000 A: maximum let-through I2t, " + recalled,
                                                "let-through I2t at the rated short-circuit capacity"),
        "en60898_1.class3.In_le_32.I2t": Stated(_iv("45000"), "A2s", JUDGED, MAINTAINERS,
                                                "EN 60898-1 Annex ZA, energy-limiting class 3, type B, 16 A < In <= 32 A, "
                                                "at 6000 A: maximum let-through I2t, " + recalled,
                                                "let-through I2t at the rated short-circuit capacity"),
        "anodic.carbon_steel": Stated(_iv("0.85"), "V", JUDGED, MAINTAINERS, "plain carbon and low-alloy steel: " + anodic,
                                      "anodic index of the bare surface"),
        "anodic.stainless_18cr": Stated(_iv("0.5"), "V", JUDGED, MAINTAINERS,
                                        "18 % chromium corrosion-resistant steel, passive: " + anodic,
                                        "anodic index of the bare surface"),
        "anodic.wrought_aluminium": Stated(_iv("0.9"), "V", JUDGED, MAINTAINERS,
                                           "wrought aluminium other than the 2000 series: " + anodic,
                                           "anodic index of the bare surface"),
        "anodic.copper": Stated(_iv("0.35"), "V", JUDGED, MAINTAINERS, "copper, solid or plated: " + anodic,
                                "anodic index of the bare surface"),
        "anodic.high_brass": Stated(_iv("0.45"), "V", JUDGED, MAINTAINERS, "high brasses and bronzes: " + anodic,
                                    "anodic index of the bare surface"),
        "anodic.zinc_plate": Stated(_iv("1.25"), "V", JUDGED, MAINTAINERS, "zinc plated surfaces: " + anodic,
                                    "anodic index of the plated surface"),
        "weld.mig_6xxx_T6.haz_fy_factor": Stated(_iv("0.48"), "1", JUDGED, MAINTAINERS,
                                                 "EN 1999-1-1:2007 Table 3.2b, HAZ factor rho_o,haz for 6061-T6 MIG "
                                                 "welds, " + recalled,
                                                 "0.2 % proof strength in the heat-affected zone over the parent value"),
        "iec60364_5_51.AA5": Stated(_iv("5", "40"), "degC", SANCTIONED, "IEC",
                                    "IEC 60364-5-51:2005, external influence code AA5",
                                    "ambient air temperature from +5 to +40 degC"),
        "iec60364_5_51.AA7": Stated(_iv("-25", "55"), "degC", SANCTIONED, "IEC",
                                    "IEC 60364-5-51:2005, external influence code AA7",
                                    "ambient air temperature from -25 to +55 degC"),
    }
    terminal = ("generic terminal rating standing for a manufacturer's datasheet tested to IEC 60998-2-2, "
                "judged by petra-maintainers; replace it with the real part's datasheet")
    for part, temperature, current, smallest, largest in (
        ("lever_4mm2_75C", "75", "32", "0.2", "4"),
        ("screw_16mm2_75C", "75", "76", "1.5", "16"),
    ):
        table[f"terminal.{part}.temperature_max"] = Stated(_iv(temperature), "degC", JUDGED, MAINTAINERS, terminal,
                                                           "maximum temperature at the clamping point")
        table[f"terminal.{part}.current_max"] = Stated(_iv(current), "A", JUDGED, MAINTAINERS, terminal,
                                                       "rated current")
        table[f"terminal.{part}.conductor_min"] = Stated(_iv(smallest, scale=MM2), "m2", JUDGED, MAINTAINERS, terminal,
                                                         "smallest conductor the clamp accepts")
        table[f"terminal.{part}.conductor_max"] = Stated(_iv(largest, scale=MM2), "m2", JUDGED, MAINTAINERS, terminal,
                                                         "largest conductor the clamp accepts")
    for key, area, _, r_max in CABLE_SIZES:
        table[f"iec60228.{key}.rho20_max"] = Stated(
            _iv(r_max, scale=Fraction(area) * OHM_MM2_PER_KM), "ohm m", JUDGED, MAINTAINERS,
            f"IEC 60228:2004 Table 2, class 2 plain copper conductor {area} mm2: maximum resistance at 20 degC "
            f"{r_max} ohm/km, times the nominal area; " + recalled,
            f"resistivity of a conductor at its IEC 60228 maximum resistance: {r_max} ohm/km times {area} mm2")
    sizes = [table[f"iec60228.{key}.rho20_max"].value for key, *_ in CABLE_SIZES]
    table["iec60228.class2_cu.rho20_max"] = Stated(
        Interval(min(v.lo for v in sizes), max(v.hi for v in sizes)), "ohm m", JUDGED, MAINTAINERS,
        "IEC 60228:2004 Table 2, class 2 plain copper: the least and greatest maximum resistance at 20 degC times "
        "nominal area over the catalogue's sizes " + ", ".join(area for _, area, *_ in CABLE_SIZES) + " mm2; "
        + recalled,
        "the span of a size's rho20_max over the catalogue's sizes, not a tolerance")
    for rating in MCB_RATINGS:
        table[f"iec60898_1.B{rating}.In"] = Stated(_iv(rating), "A", SANCTIONED, "IEC",
                                                   f"IEC 60898-1:2015, rated current {rating} A, a preferred value "
                                                   f"(clause not checked); the designation B{rating}",
                                                   "rated current at the 30 degC reference ambient")
    return table


STATED: Mapping[str, Stated] = _stated()
