"""The parts deck's data: process presets, finishes, polymer materials, screws and heat-set
inserts. Trusted; each row is a premise with a tag, an owner and a source.

Every value's standard text starts with its label. "reported: <where>" is a number a
shop, maker or datasheet publishes, read on the page named. "inferred: <how>" is derived
from reported values. "guess: <why>" is a typical value nobody has signed. All are tagged
judged and owned by petra-maintainers until a maker signs its own preset or the design
overrides a row with a signed bound. Lengths are in metres, temperatures in degC,
densities in kg/m3, masses in kg.

The rows the parts rules read:
    process.<kind>.<id>   tolerance (each surface lies within it of nominal, both ways;
                          with tolerance_rate, within the larger of it and the rate times
                          the part's largest dimension), hole_shrink (diametral undersize of a modelled hole, print and
                          powder), build_x, build_y, build_z (print, powder) or bed_x, bed_y
                          (sheet), thickness (sheet: the stock the preset cuts), bridge (print:
                          the longest span over air)
    process.<finish>      buildup (thickness a finish adds to each coated surface), density
    polymer.<id>          density, tg, hdt (heat deflection at 0.45 MPa, ISO 75-2 method B)
    screw.<id>            d (major diameter), thread_d (the nominal size), pitch, head_d
                          (least to greatest), head_h, length (least to greatest), mass;
                          csk_angle on a countersunk head
    insert.<id>           hole_min, hole_max (the catalogue's hole range), length, wall_min,
                          mass, and the screw thread it takes
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from ..kernel import Interval
from .constants import JUDGED, MAINTAINERS, STATED
from .model import Constant, Material, Part, PartKind, Process, ProcessKind, Stated

MM = Fraction(1, 1000)
STEEL_DENSITY = (Fraction(7750), Fraction(8050))   # kg/m3; inferred: carbon and alloy steels span about this range


def _mm(lo: str, hi: str | None = None) -> Interval:
    return Interval(Fraction(lo) * MM, Fraction(hi if hi is not None else lo) * MM)


def _iv(lo: str, hi: str | None = None) -> Interval:
    return Interval(Fraction(lo), Fraction(hi if hi is not None else lo))


def _s(value: Interval, unit: str, label: str, conditions: str = "") -> Stated:
    return Stated(value, unit, JUDGED, MAINTAINERS, label, conditions)


HUBS_FDM = "hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/"
HUBS_SLS = "hubs.com/knowledge-base/how-design-parts-sls-3d-printing/"
CNC_SHOPS = ("Hubs hubs.com/knowledge-base/how-design-parts-cnc-machining/, Protolabs "
             "protolabs.com/services/cnc-machining/cnc-milling/design-guidelines/, SendCutSend "
             "sendcutsend.com/guidelines/cnc-machining/ (quoted in the 2026-11-08 gap audit, row E-138)")


def presets() -> Mapping[str, Process]:
    """Every parts process preset by id."""
    fdm = {
        "tolerance": _s(_mm("0.5"), "m", f"guess: recalled, {HUBS_FDM} desktop FDM, +/-0.5 % with a lower limit of +/-0.5 mm; "
                                         "not confirmed against a source on disk. This row is the lower limit"),
        "tolerance_rate": _s(_iv("0.005"), "1", f"guess: recalled, {HUBS_FDM} desktop FDM, +/-0.5 %; not confirmed against a "
                                                "source on disk. The rules apply it to the part's box diagonal, which no "
                                                "dimension of the part exceeds"),
        "hole_shrink": _s(_mm("0.1", "0.2"), "m", "guess: modelled holes print 0.1 to 0.2 mm undersize on a tuned desktop FDM printer "
                                                  "(gap audit row E-006 reports tenths of a millimetre)"),
        "bridge": _s(_mm("5", "10"), "m", f"reported: {HUBS_FDM} and hubs.com/knowledge-base/key-design-considerations-"
                                          "3d-printing/ give 5 mm and 10 mm for an unsupported span (gap audit row E-010)"),
        "build_x": _s(_mm("250"), "m", "reported: Prusa MK4 build volume 250 x 210 x 220 mm, prusa3d.com"),
        "build_y": _s(_mm("210"), "m", "reported: Prusa MK4 build volume 250 x 210 x 220 mm, prusa3d.com"),
        "build_z": _s(_mm("220"), "m", "reported: Prusa MK4 build volume 250 x 210 x 220 mm, prusa3d.com"),
    }
    sls = {
        "tolerance": _s(_mm("0.3"), "m", f"guess: recalled, {HUBS_SLS} +/-0.3 % with a lower limit of +/-0.3 mm; not "
                                         "confirmed against a source on disk. This row is the lower limit"),
        "tolerance_rate": _s(_iv("0.003"), "1", f"guess: recalled, {HUBS_SLS} +/-0.3 %; not confirmed against a source on disk. "
                                                "The rules apply it to the part's box diagonal"),
        "hole_shrink": _s(_mm("0", "0.2"), "m", "guess: powder sinters into small holes; 0 to 0.2 mm diametral"),
        "build_x": _s(_mm("340"), "m", "guess: an EOS P 396 class machine, 340 x 340 x 600 mm"),
        "build_y": _s(_mm("340"), "m", "guess: an EOS P 396 class machine, 340 x 340 x 600 mm"),
        "build_z": _s(_mm("600"), "m", "guess: an EOS P 396 class machine, 340 x 340 x 600 mm"),
    }
    laser = {
        "tolerance": _s(_mm("0.127"), "m", "reported: sendcutsend.com/guidelines/ laser cutting, +/-0.005 in"),
        "thickness": _s(_mm("3"), "m", "guess: the preset cuts 3 mm sheet; the mesh models its nominal thickness"),
        "bed_x": _s(_mm("1200"), "m", "guess: a 1200 x 600 mm sheet"),
        "bed_y": _s(_mm("600"), "m", "guess: a 1200 x 600 mm sheet"),
    }
    mill = {
        "tolerance": _s(_mm("0.13"), "m", f"reported: {CNC_SHOPS}, standard milling tolerance +/-0.1 to +/-0.13 mm; "
                                          "the wider end is the preset's"),
    }

    def p(id: str, kind: ProcessKind, rows: Mapping[str, Stated], source: str) -> tuple[str, Process]:
        return id, Process(id, kind, dict(rows), source=source)

    return dict((
        p("process.print.fdm_pla_0_4", ProcessKind.PRINT, fdm, "desktop FDM, 0.4 mm nozzle; rows labelled each"),
        p("process.print.fdm_petg_0_4", ProcessKind.PRINT, fdm, "desktop FDM, 0.4 mm nozzle; rows labelled each"),
        p("process.powder.sls_pa12", ProcessKind.POWDER, sls, "SLS polyamide 12; rows labelled each"),
        p("process.sheet.laser_al_3", ProcessKind.SHEET, laser, "laser-cut 3 mm aluminium sheet; rows labelled each"),
        p("process.mill.al6061_3axis", ProcessKind.MILL, mill, "3-axis milling of 6061-T6; rows labelled each"),
    ))


def finishes() -> Mapping[str, Process]:
    """Coatings that add thickness to every coated surface, so fit rules read their buildup."""
    return {
        "process.anodize_ii": Process("process.anodize_ii", ProcessKind.COATING, {
            "buildup": _s(_mm("0.005", "0.0125"), "m", "guess: MIL-A-8625 type II coatings run about 0.01 to 0.025 mm "
                                                     "thick and about half grows outward"),
            "density": _s(_iv("2400", "4000"), "kg/m3", "guess: porous anodic alumina up to dense alumina, about 3.95 g/cm3"),
        }, surface="oxide.anodic_aluminium", source="type II sulphuric anodize on aluminium; rows labelled each"),
        "process.powder_coat": Process("process.powder_coat", ProcessKind.COATING, {
            "buildup": _s(_mm("0.05", "0.12"), "m", "guess: one coat of polyester powder, 0.05 to 0.12 mm"),
            "density": _s(_iv("1100", "2000"), "kg/m3", "guess: cured polyester powder coats with fillers"),
        }, surface="polymer.powder_coat", source="polyester powder coat; rows labelled each"),
    }


def polymers() -> Mapping[str, Material]:
    """Printable polymers with density, glass transition and heat deflection rows, and
    the two finish surfaces. No strength rows until a strength rule reads them."""

    def m(id: str, density: tuple[str, str], tg: tuple[str, str], hdt: tuple[str, str], what: str) -> tuple[str, Material]:
        label = f"guess: typical {what} filament and resin datasheets; no single sheet signed"
        return id, Material(id, "polymer", what, {
            "density": _s(_iv(*density), "kg/m3", label),
            "tg": _s(_iv(*tg), "degC", label, "glass transition, DSC"),
            "hdt": _s(_iv(*hdt), "degC", label, "heat deflection temperature at 0.45 MPa, ISO 75-2 method B"),
        })

    return dict((
        m("polymer.pla", ("1240", "1250"), ("55", "60"), ("50", "56"), "PLA"),
        m("polymer.petg", ("1260", "1280"), ("75", "85"), ("64", "70"), "PETG"),
        m("polymer.abs", ("1030", "1060"), ("100", "110"), ("85", "98"), "ABS"),
        m("polymer.asa", ("1050", "1080"), ("100", "110"), ("90", "100"), "ASA"),
        m("polymer.pa12", ("930", "1010"), ("40", "55"), ("150", "180"), "SLS PA12"),
        m("polymer.pc", ("1190", "1210"), ("140", "150"), ("130", "140"), "polycarbonate"),
        ("oxide.anodic_aluminium", Material("oxide.anodic_aluminium", "oxide", "anodic aluminium oxide", {})),
        ("polymer.powder_coat", Material("polymer.powder_coat", "polymer", "polyester powder coat", {})),
    ))


# ISO 4762 socket head cap and ISO 10642 countersunk screws: (d, head_d least, head_d greatest,
# head_h max, pitch), mm. The least head diameters are recalled, not read from a source on
# disk, and rounded down, so the seat and sink rules that read them err safe.
_SHCS = {"M2_5": ("2.5", "4.3", "4.5", "2.5", "0.45"), "M3": ("3", "5.3", "5.5", "3", "0.5"),
         "M4": ("4", "6.75", "7", "4", "0.7")}
_CSK = {"M3": ("3", "5.5", "6.72", "1.86", "0.5"), "M4": ("4", "7.5", "8.96", "2.48", "0.7")}
_DK_RECALLED = {"shcs": {"M2_5": "4.32", "M3": "5.32", "M4": "6.78"}, "csk": {"M3": "5.54", "M4": "7.53"}}
# Nominal length and half its range, mm: the recalled ISO 4762 js15 length limits (0.24,
# 0.29, 0.35 and 0.42 mm), rounded up, not read from a source on disk.
_LENGTHS = (("6", "0.25"), ("8", "0.3"), ("10", "0.3"), ("12", "0.35"), ("16", "0.35"), ("20", "0.45"))
ISO4762 = "reported: ISO 4762:2004 Table 1 dk max and k max, as printed in maker catalogues (e.g. bossard.com)"
ISO10642 = "reported: ISO 10642:2004 Table 1 dk theoretical max and k max, as printed in maker catalogues"
ISO261 = "guess: recalled, ISO 261 coarse pitch for the size, not confirmed against a source on disk"


def fasteners() -> Mapping[str, Part]:
    """Screws by id, "screw.<size>x<length>_<head>", steel class 8.8 or 12.9 unplated.
    Mass is inferred from the head and shank volumes, which over-counts the socket."""
    out: dict[str, Part] = {}
    for head, table, std in (("shcs", _SHCS, ISO4762), ("csk", _CSK, ISO10642)):
        for size, (d, dk_lo, dk, k, pitch) in table.items():
            for length, half in _LENGTHS:
                id = f"screw.{size}x{length}_{head}"
                d_, dk_, k_ = (Fraction(x) for x in (d, dk, k))
                l_lo, l_hi = Fraction(length) - Fraction(half), Fraction(length) + Fraction(half)
                cone = 1 if head == "shcs" else Fraction(1, 3)
                lo_, hi_ = ((dk_ ** 2 * k_ * cone + d_ ** 2 * l) * Fraction(785398, 10**6) for l in (l_lo, l_hi))
                mass = Interval(lo_ * MM ** 3 * STEEL_DENSITY[0] * Fraction(85, 100), hi_ * MM ** 3 * STEEL_DENSITY[1])
                standard = "ISO 4762" if head == "shcs" else "ISO 10642"
                props = {
                    "d": _s(_mm(d), "m", f"{std}; nominal major diameter"),
                    "thread_d": _s(_mm(d), "m", f"{std}; the thread's nominal size"),
                    "pitch": _s(_mm(pitch), "m", ISO261),
                    "head_d": _s(_mm(dk_lo, dk), "m", f"guess: the least recalled, {standard} dk min about "
                                                     f"{_DK_RECALLED[head][size]} mm, not confirmed against a source on "
                                                     f"disk, rounded down to {dk_lo} mm; the greatest {std[10:]}"),
                    "head_h": _s(_mm(k), "m", std),
                    "length": _s(_mm(str(Fraction(length) - Fraction(half)), str(Fraction(length) + Fraction(half))), "m",
                                 f"guess: recalled, ISO 4762 js15 length limits, not confirmed against a source on disk, rounded "
                                 f"out to +/-{half} mm about {length} mm; the head's top to the tip for a countersunk "
                                 f"screw and the bearing face to the tip otherwise"),
                    "mass": _s(mass, "kg", "inferred: steel density times the head's and the shank's volume at "
                                           "their least and greatest length, less up to 15 % for the socket and "
                                           "thread"),
                }
                if head == "csk":
                    props["csk_angle"] = _s(_iv("90"), "1", f"{std}; included head angle", "degrees")
                out[id] = Part(id, PartKind.SCREW, f"{size} x {length} {'ISO 4762 socket head cap' if head == 'shcs' else 'ISO 10642 countersunk'} screw",
                               "steel.bolt_qt", props, source=std)
    return out


def inserts() -> Mapping[str, Part]:
    """Heat-set threaded inserts for printed parts, by their catalogue's hole and wall."""
    label = "guess: typical heat-set insert catalogues (Ruthex, CNC Kitchen); no single sheet signed"

    def i(id: str, thread: str, hole: tuple[str, str], length: str, wall: str, mass: tuple[str, str]) -> tuple[str, Part]:
        return id, Part(id, PartKind.INSERT, f"heat-set brass insert {thread}, {length} mm long", "brass.insert", {
            "hole_min": _s(_mm(hole[0]), "m", label, "the least hole diameter the catalogue accepts, as printed"),
            "hole_max": _s(_mm(hole[1]), "m", label, "the greatest hole diameter the catalogue accepts, as printed"),
            "length": _s(_mm(length), "m", label),
            "wall_min": _s(_mm(wall), "m", label, "least wall around the hole"),
            "mass": _s(Interval(Fraction(mass[0]) / 1000, Fraction(mass[1]) / 1000), "kg", label),
            "thread_d": _s(_mm(thread[1:]), "m", label, "the screw size it takes"),
        }, source=label)

    return dict((
        i("insert.M3x5_7", "M3", ("3.9", "4.1"), "5.7", "1.6", ("0.3", "0.4")),
        i("insert.M3x4", "M3", ("3.9", "4.1"), "4", "1.6", ("0.2", "0.3")),
        i("insert.M4x8_1", "M4", ("5.5", "5.7"), "8.1", "2", ("0.7", "0.9")),
    ))


def brass() -> Mapping[str, Material]:
    return {"brass.insert": Material("brass.insert", "brass", "CuZn39Pb3 free-cutting brass, EN 12164",
                                     {"anodic_index": STATED["anodic.high_brass"]})}


def constants() -> Mapping[str, Constant]:
    """The least engaged length of a screw's thread, in diameters, by what the thread
    enters: "parts.engagement.<tap|form|insert>"."""

    def c(role: str, value: Fraction, why: str) -> tuple[str, Constant]:
        name = f"parts.engagement.{role}"
        return name, Constant(name, Interval(value, value), "1", JUDGED, MAINTAINERS, f"guess: {why}",
                              f"a screw's thread engages at least {value} diameters when it enters a {role} hole")

    return dict((
        c("tap", Fraction(3, 2), "common practice for a thread tapped in aluminium"),
        c("form", Fraction(2), "common practice for a thread formed in plastic"),
        c("insert", Fraction(3, 2), "common practice for a heat-set insert"),
    ))
