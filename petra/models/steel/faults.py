"""Manufactured faults for the steel deck's gate (docs/steel_connections.md §8, §9 item 6).
Tooling: nothing here changes a verdict.

A fault is one known defect put into a design the deck passes: a fillet far under Table
J2.4's minimum, a short edge, holes too close or too far apart, oversized holes in a
bearing joint, Group 150 bolts in tension left snug, a shear tab or tee too stiff to rotate, a
slender seat stiffener, a seat plate softer than the stiffener it bears on, a seat stiffener
too short for its moment, a seated beam's web past its shear yielding, a hanger's support web
past its local yielding, bracket bolts with no room for a socket, a lapped fillet as thick
as its plate, bolts against a hanger's stem, a cope deeper than half the beam, a load past
the governing strength; and parts that
do not fit: bolt rows run past the beam's depth or off a seat's leg, a support gauge wider
than the face, a beam too wide to pass between a column's flanges, a plate on the beam's
fillet, a bracket's bolt columns off the flange; a flange force's panel_shear or axial
load left out, which leaves its panel zone open rather than unchecked; and a flange force
at a member end free to twist, whose J10.7 stiffeners leave it open; and under a cyclic
load (Appendix 3): snug-tight bolts, a load range past a detail's fatigue strength, and a
plate's end welded on one face, whose detail the deck does not encode. `seed_faults`
applies each fault to passing designs from the generator; the deck catches a fault when
its verdict is not PASS, and names it when a refuted or open requirement is one of the
fault's modes. The gate wants every fault caught and named.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Iterator

from ...lang import parse_design
from ...pipeline import check_design
from ...registry import Registry
from ...solvers import SolverSource
from ...verdict import STATUS
from ..base import ComponentError
from .generate import SIGNATURE, Generated, generate
from .lower import CYCLES, KIND_SPECS

BOLTED = ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate", "bolt_bracket", "hanger")


@dataclass(frozen=True)
class Fault:
    name: str
    defect: str
    kinds: tuple[str, ...]
    edit: Callable[[str, Generated], str | None]    # the defective text, or None where it does not apply
    modes: frozenset[str]                           # the deck names the fault by one of these


@dataclass(frozen=True)
class Caught:
    fault: str
    base: str
    kind: str
    status: str             # the deck's verdict on the defective design, or "REJECTED" at lowering
    named: tuple[str, ...]  # the fault's modes among the refuted or open requirements
    others: tuple[str, ...] # other modes refuted or open

    @property
    def caught(self) -> bool:
        return self.status != "PASS"

    @property
    def is_named(self) -> bool:
        return bool(self.named) or self.status == "REJECTED"


def _field(text: str, key: str) -> str | None:
    m = re.search(rf"^  {key} (.*)$", text, re.M)
    return m.group(1) if m else None


def _set(text: str, key: str, value: str) -> str | None:
    """Replace the whole `key` line (fixed or toleranced) with `key value`."""
    if _field(text, key) is None:
        return None
    return re.sub(rf"^  {key} .*$", f"  {key} {value}", text, count=1, flags=re.M)


def _inches(text: str, key: str) -> Fraction | None:
    raw = _field(text, key)
    m = re.match(r"(?:in \[)?([0-9.]+) inch", raw or "")
    return Fraction(m.group(1)) if m else None


def _weld_size(text: str, key: str, size: str) -> str | None:
    raw = _field(text, key)
    if raw is None:
        return None
    return _set(text, key, re.sub(r"size [0-9.]+ inch", f"size {size} inch", raw))


def _missing_weld(text: str, g: Generated) -> str | None:
    key = "weld" if _field(text, "weld") is not None else "support_weld"
    return _weld_size(text, key, "0.0625")


def _short_edge(text: str, g: Generated) -> str | None:
    return _set(text, "edge_vertical", "0.625 inch")


def _close_holes(text: str, g: Generated) -> str | None:
    rows = _field(text, "rows")
    return _set(text, "pitch", "1.5 inch") if rows and int(rows) > 1 else None


def _drop_load(field: str) -> Callable[[str, Generated], str | None]:
    """The design with its `field` load left out of the load case."""
    def edit(text: str, g: Generated) -> str | None:
        return re.sub(rf"^  on c1 {field} in .*\n", "", text, count=1, flags=re.M)
    return edit


def _free_end(text: str, g: Generated) -> str | None:
    """The force at a member end free to twist about its axis, which J10.7 stiffens: an
    end force's end_twist set free, or an interior force moved 16 in from a free end."""
    if _field(text, "end_twist") is not None:
        return _set(text, "end_twist", "free")
    return _set(text, "location", "end\n  distance 16 inch\n  end_twist free")


def _far_holes(text: str, g: Generated) -> str | None:
    rows = _field(text, "rows")
    return _set(text, "pitch", "13 inch") if rows and int(rows) > 1 else None


def _oversized_in_bearing(text: str, g: Generated) -> str | None:
    bolts = _field(text, "bolts")
    if bolts is None or "slip_critical" in bolts or _field(text, "holes") is not None:
        return None
    ply = {"shear_tab": "plate", "double_angle": "angles", "single_angle": "angle", "shear_tee": "stem",
           "shear_end_plate": "plate", "seated": "angle", "bolt_bracket": "plate", "hanger": "flange"}[g.kind]
    return text.replace(f"  bolts {bolts}\n", f"  bolts {bolts}\n  holes {ply} ovs\n", 1)


def _snug_in_tension(text: str, g: Generated) -> str | None:
    bolts = _field(text, "bolts")
    if bolts is None:
        return None
    snug = re.sub(r" joint \w+( surface \w+)?( fillers \w+)?", "", bolts).replace("bolt_group.120", "bolt_group.150")
    return text.replace(f"  bolts {bolts}\n", f"  bolts {snug}\n", 1)


def _thin_tab_weld(text: str, g: Generated) -> str | None:
    if _field(text, "form") == "extended":
        return None
    plate = _field(text, "plate")
    tp = Fraction(re.search(r"thickness ([0-9.]+) inch", plate).group(1))
    return _weld_size(text, "weld", "0.1875") if Fraction(5, 8) * tp > Fraction(3, 16) else None


def _slender_stiffener(text: str, g: Generated) -> str | None:
    st = _field(text, "stiffener")
    thin = re.sub(r"thickness [0-9.]+ inch", "thickness 0.25 inch", st)
    out = text.replace(f"  stiffener {st}\n", f"  stiffener {thin}\n", 1)
    return _set(out, "stiffener_width", "6 inch")


def _soft_seat_plate(text: str, g: Generated) -> str | None:
    """An A36 seat plate on a 5 x 1/2 in A572 Grade 50 stiffener, loaded to 1.15 times the
    plate's available bearing on the stiffener's fitted edge (J7), 1.8 (36 ksi)(5 in - 1/2
    in)(1/2 in) = 145.8 kip nominal, and to 0.83 times the stiffener's."""
    if _field(text, "stiffener") is None:
        return None
    available = Fraction(1458, 10) * (Fraction(3, 4) if _field(text, "basis") == "lrfd" else Fraction(1, 2))
    out = re.sub(r"^  plate steel\.\w+ ", "  plate steel.A36 ", text, count=1, flags=re.M)
    out = re.sub(r"^  stiffener .*$", "  stiffener steel.A572_50 thickness 0.5 inch", out, count=1, flags=re.M)
    out = _set(out, "stiffener_width", "5 inch")
    load = float(available * Fraction(115, 100))
    return re.sub(r"^  on c1 shear in .*$", f"  on c1 shear in [0 kip, {load:.3f} kip]", out, count=1, flags=re.M)


def _available(text: str, nominal: Fraction, phi: Fraction, omega: Fraction) -> Fraction:
    """A nominal strength in kip at the design's basis: phi Rn (LRFD) or Rn / Omega (ASD)."""
    return nominal * phi if _field(text, "basis") == "lrfd" else nominal / omega


def _loaded(text: str, field: str, load: Fraction) -> str:
    return re.sub(rf"^  on c1 {field} in .*$", f"  on c1 {field} in [0 kip, {float(load):.3f} kip]", text, count=1, flags=re.M)


def _short_stiffener(text: str, g: Generated) -> str | None:
    """A 6 x 1/2 in A36 seat stiffener only 4 in long, bent at its weld line by the reaction
    at 0.8 W = 4.8 in: Mn = Fy t L^2 / 4 = 36 (0.5)(16) / 4 = 72 kip-in, loaded to 1.25 times
    the reaction that reaches it (J4.5; phi 0.90, Omega 1.67)."""
    out = _set(text, "stiffener", "steel.A36 thickness 0.5 inch")
    out = out and _set(out, "stiffener_width", "6 inch")
    out = out and _set(out, "stiffener_length", "4 inch")
    if out is None:
        return None
    reaction = _available(text, Fraction(72), Fraction(9, 10), Fraction(167, 100)) / Fraction(48, 10)
    return _loaded(out, "shear", reaction * Fraction(125, 100))


def _seated_web_in_shear(text: str, g: Generated) -> str | None:
    """A W12x26 (d 12.2 in, tw 0.230 in) on its seat, loaded to 1.2 times its web's shear
    yielding at the end, 0.6 (50 ksi)(12.2 in)(0.230 in) = 84.18 kip (J4.2(a); phi 1.00,
    Omega 1.50)."""
    out = _set(text, "beam", "W12x26 grade steel.A992")
    if out is None:
        return None
    return _loaded(out, "shear", _available(text, Fraction(8418, 100), Fraction(1), Fraction(3, 2)) * Fraction(12, 10))


def _thin_support_web(text: str, g: Generated) -> str | None:
    """A hanger from a W16x26 (tw 0.250 in, kdes 0.747 in) with two rows 3 in apart, pulled
    to 1.25 times its web's local yielding at the member end, 50 ksi (0.250 in)(2.5 (0.747
    in) + 3 in) = 60.84 kip (J10-3; phi 1.00, Omega 1.50)."""
    out = _set(text, "support", "W16x26 flange grade steel.A992")
    out = out and _set(out, "rows", "2")
    out = out and _set(out, "pitch", "3 inch")
    if out is None:
        return None
    return _loaded(out, "tension", _available(text, Fraction(6084375, 100000), Fraction(1), Fraction(3, 2)) * Fraction(125, 100))


def _cramped_bracket(text: str, g: Generated) -> str | None:
    """Two columns of 3/4 in bolts 2-1/2 in apart on a W12x26's flange (bf 6.49 in, tw
    0.230 in). On one side of the web the outer hole on the flange leaves 3.13 - 2.5 - 0.41 =
    0.22 in to the web; split across it, they leave (2.5 - 0.23) / 2 = 1.135 in. A socket on
    a 3/4 in heavy hex nut needs 1.25 / sqrt 3 + 1/2 = 1.222 in (Manual Part 7). The split
    fits the flange; only the wrench has no room."""
    bolts = _field(text, "bolts")
    out = _set(text, "support", "W12x26 flange grade steel.A992")
    out = out and _set(out, "columns", "2")
    out = out and _set(out, "gauge", "2.5 inch")
    if out is None or bolts is None:
        return None
    return _set(out, "bolts", re.sub(r"diameter [0-9.]+ inch", "diameter 0.75 inch", bolts))


def _thick_lap_fillet(text: str, g: Generated) -> str | None:
    if _field(text, "weld_return") is None:
        return None
    plate = _field(text, "plate")
    tp = re.search(r"thickness ([0-9.]+) inch", plate).group(1)
    return _weld_size(text, "weld", tp)


def _bolts_at_stem(text: str, g: Generated) -> str | None:
    return _set(text, "tee_gauge", "1.25 inch")


def _deep_cope(text: str, g: Generated) -> str | None:
    beam = _field(text, "beam")
    depth = Fraction(re.match(r"W(\d+)x", beam).group(1))
    cope = f"top depth {float(depth * Fraction(3, 5)):g} inch length 4 inch"
    if _field(text, "cope") is not None:
        return _set(text, "cope", cope)
    out = text.replace("  top ", f"  cope {cope}\n  top ", 1)
    # a coped beam states its setback (lower.SET_BACK)
    return out if _field(out, "setback") is not None else out.replace("  top ", "  setback 0.5 inch\n  top ", 1)


def _overload(text: str, g: Generated) -> str | None:
    """Every load raised in proportion so the governing check reaches about 1.3 at least,
    for u growing at least as the square root of the load."""
    factor = (Fraction(13, 10) / Fraction(g.utilisation)) ** 2

    def raised(m: re.Match) -> str:
        return f"  on c1 {m.group(1)} in [0 kip, {float(Fraction(m.group(2)) * factor):.3f} kip]"
    return re.sub(r"^  on c1 (\w+) in \[0 kip, ([0-9.]+) kip\]$", raised, text, flags=re.M)


def _cyclic_case(text: str, g: Generated, factor: int, cycles: int) -> str | None:
    """The design with a second load case, cyclic: its gate case's primary load, `factor`
    times over, as the range [0, factor P] for `cycles` cycles."""
    field = KIND_SPECS[g.kind].loads[0]
    m = re.search(rf"^  on c1 {field} in \[0 kip, ([0-9.]+) kip\]$", text, re.M)
    if m is None:
        return None
    top = Fraction(m.group(1)) * factor
    return (f"{text}\nload cycled {{\n  on c1 {field} in [0 kip, {float(top):.3f} kip]\n"
            f"  on c1 {CYCLES} in [0, {cycles}]\n  {SIGNATURE}\n}}\n")


def _bolts_as(text: str, joint: str) -> str | None:
    """The bolts installed `joint`: snug, or pretensioned unless slip-critical."""
    bolts = _field(text, "bolts")
    if bolts is None:
        return None
    if joint == "pretensioned" and "slip_critical" in bolts:
        return text
    plain = re.sub(r" joint \w+( surface \w+)?( fillers \w+)?", "", bolts)
    return text.replace(f"  bolts {bolts}\n", f"  bolts {plain}{'' if joint == 'snug' else ' joint ' + joint}\n", 1)


def _snug_under_cycles(text: str, g: Generated) -> str | None:
    """Snug-tight bolts under the design's own load, cycled two million times."""
    out = _bolts_as(text, "snug")
    return _cyclic_case(out, g, 1, 2_000_000) if out else None


def _cyclic_overload(text: str, g: Generated) -> str | None:
    """A pretensioned joint under three times the design's load, cycled 200 million times:
    every detail's range far past its threshold."""
    out = _bolts_as(text, "pretensioned") if _field(text, "bolts") is not None else text
    return _cyclic_case(out, g, 3, 200_000_000) if out else None


def _one_sided_end(text: str, g: Generated) -> str | None:
    """A plate's end welded on one face under the design's load, cycled two million times."""
    weld = _field(text, "weld")
    if weld is None or " sides 2" not in weld or _field(text, "weld_return") is not None:
        return None
    return _cyclic_case(_set(text, "weld", weld.replace(" sides 2", " sides 1")), g, 1, 2_000_000)


def _thick_tab(text: str, g: Generated) -> str | None:
    """Neither part thin enough to rotate: a 3/4 in plate on a W30x90 (tw 0.470 in) with
    3/4 in bolts, both past d/2 + 1/16 = 7/16 in."""
    if _field(text, "form") == "extended":
        return None
    plate, bolts = _field(text, "plate"), _field(text, "bolts")
    out = _set(text, "plate", re.sub(r"thickness [0-9.]+ inch", "thickness 0.75 inch", plate))
    out = _set(out, "bolts", re.sub(r"diameter [0-9.]+ inch", "diameter 0.75 inch", bolts))
    out = _set(out, "beam", "W30x90 grade steel.A992")
    return _weld_size(out, "weld", "0.5")


def _stiff_tee(text: str, g: Generated) -> str | None:
    """A tee too stiff to rotate: a WT10.5x36.5 (stem 0.455 in, flange 0.740 in) on a
    W30x90 (web 0.470 in) with 3/4 in bolts, both past d/2 + 1/16 = 7/16 in, its flange
    welded to the support with 3/16 in fillets where Manual Eq 9-51 wants about 0.28 in."""
    bolts = _field(text, "bolts")
    out = _set(text, "tee", "WT10_5x36_5 grade steel.A992")
    out = _set(out, "beam", "W30x90 grade steel.A992")
    out = _set(out, "bolts", re.sub(r"diameter [0-9.]+ inch", "diameter 0.75 inch", bolts))
    if _field(out, "support_weld") is not None:
        return _weld_size(out, "support_weld", "0.1875")
    out = re.sub(r"^  support_gauge .*\n", "", out, count=1, flags=re.M)
    return _set(out, "support_side", "welded\n  support_weld electrode.E70 size 0.1875 inch")


def _rows_past_depth(text: str, g: Generated) -> str | None:
    """Rows at the pitch drawn to reach 3 pitches past the beam's nominal depth."""
    beam, pitch = _field(text, "beam"), _inches(text, "pitch")
    if beam is None or pitch is None or _field(text, "rows") is None:
        return None
    nominal = Fraction(re.match(r"W(\d+)x", beam).group(1))
    return _set(text, "rows", str(int(nominal // pitch) + 4))


def _rows_off_leg(text: str, g: Generated) -> str | None:
    """A bolted seat's leg with six rows: the bottom hole runs past the leg."""
    return _set(text, "rows", "6") if _field(text, "support_side") == "bolted" else None


def _gauge_off_face(text: str, g: Generated) -> str | None:
    """Support bolt lines 20 in apart: wider than every support's flange and web."""
    key = "tee_gauge" if g.kind == "hanger" else "support_gauge"
    return _set(text, key, "20 inch")


def _beam_too_wide(text: str, g: Generated) -> str | None:
    """A W24x76 (flange 8.99 in) framed into the web of a W10x49, whose flanges stand 8.86 in
    apart, its end inside their tips."""
    out = _set(text, "beam", "W24x76 grade steel.A992")
    return _set(out, "support", "W10x49 web grade steel.A992") if out else None


def _plate_on_fillet(text: str, g: Generated) -> str | None:
    """The top row a quarter inch more than the edge distance below the beam's top: the
    part's top edge is on the flange's fillet, which reaches (d - T)/2 down (at least 0.665 in
    on every W in the Shapes Database)."""
    lev = _inches(text, "edge_vertical")
    if lev is None or _field(text, "cope") is not None:
        return None
    return _set(text, "top", f"{float(lev + Fraction(1, 4)):g} inch")


def _columns_off_flange(text: str, g: Generated) -> str | None:
    """Two bracket bolt columns 16 in apart: no flange of the catalogue's supports is that wide."""
    out = _set(text, "columns", "2")
    return _set(out, "gauge", "16 inch") if out else None


BEAM_SIDE = ("shear_tab", "double_angle", "single_angle", "shear_tee")
FIT_FACES = frozenset({"flange_fit", "web_fit"})
FATIGUE = frozenset({"fatigue_bolted", "fatigue_bolt_tension", "fatigue_weld", "fatigue_weld_end", "fatigue_cope"})

FAULTS: tuple[Fault, ...] = (
    Fault("missing weld", "a 1/16 in fillet, far under Table J2.4's minimum",
          ("shear_tab", "shear_end_plate", "stiffened_seat", "weld_bracket", "double_angle", "single_angle", "shear_tee",
           "seated"), _missing_weld, frozenset({"fillet_size"})),
    Fault("short edge", "a 5/8 in edge, under Table J3.4's minimum", ("shear_tab", "double_angle", "single_angle", "shear_tee",
          "shear_end_plate", "bolt_bracket", "hanger"), _short_edge, frozenset({"edge_min"})),
    Fault("close holes", "1-1/2 in pitch, under 2-2/3 d", BOLTED, _close_holes, frozenset({"spacing_min"})),
    Fault("far holes", "13 in pitch, past the 12 in limit", BOLTED, _far_holes, frozenset({"spacing_max"})),
    Fault("wrong joint type", "oversized holes in a joint that is not slip-critical", BOLTED, _oversized_in_bearing,
          frozenset({"hole_use"})),
    Fault("snug tension bolts", "Group 150 bolts in tension left snug-tight", ("hanger",), _snug_in_tension,
          frozenset({"joint_type"})),
    Fault("thick shear tab", "a 3/4 in conventional shear tab, past d/2 + 1/16 in", ("shear_tab",), _thick_tab,
          frozenset({"ductility"})),
    Fault("thin tab weld", "a 3/16 in fillet on a shear tab that needs 5/8 of its thickness", ("shear_tab",), _thin_tab_weld,
          frozenset({"ductility"})),
    Fault("slender stiffener", "a 6 x 1/4 in seat stiffener, past 0.56 sqrt(E / Fy)", ("stiffened_seat",), _slender_stiffener,
          frozenset({"compression"})),
    Fault("soft seat plate", "an A36 seat plate bearing on a Grade 50 stiffener's edge past its own yield",
          ("stiffened_seat",), _soft_seat_plate, frozenset({"bearing"})),
    Fault("thick lap fillet", "a fillet as thick as the lapped plate it runs along", ("weld_bracket",), _thick_lap_fillet,
          frozenset({"fillet_size"})),
    Fault("bolts at the stem", "a 1-1/4 in hanger gauge, the bolts against the stem", ("hanger",), _bolts_at_stem,
          frozenset({"clearance", "prying", "edge_max"})),
    Fault("stiff tee", "a WT10.5x36.5 on a W30x90, both past d/2 + 1/16 in, welded with 3/16 in fillets", ("shear_tee",),
          _stiff_tee, frozenset({"tee_ductility"})),
    Fault("deep cope", "a cope 3/5 of the beam deep", ("shear_tab", "double_angle", "single_angle", "shear_tee"), _deep_cope,
          frozenset({"cope_buckling"})),
    Fault("overload", "a load past the governing strength", ("shear_tab", "double_angle", "single_angle", "shear_tee",
          "shear_end_plate", "seated", "stiffened_seat", "flange_force", "bolt_bracket", "weld_bracket", "hanger"), _overload,
          frozenset()),
    Fault("rows past the depth", "bolt rows running three pitches past the beam's depth", (*BEAM_SIDE, "shear_end_plate"),
          _rows_past_depth, frozenset({"beam_fit"})),
    Fault("rows off the seat leg", "six rows of bolts in a seat angle's vertical leg", ("seated",), _rows_off_leg,
          FIT_FACES),
    Fault("gauge off the face", "support bolt lines 20 in apart, wider than the support's face",
          ("double_angle", "shear_tee", "shear_end_plate", "seated", "hanger"), _gauge_off_face, FIT_FACES),
    Fault("beam too wide for the web", "a W24x76 framed between the flanges of a W10x49, 8.86 in apart",
          (*BEAM_SIDE, "shear_end_plate", "seated", "stiffened_seat"), _beam_too_wide, frozenset({"web_fit"})),
    Fault("plate on the fillet", "the part's top edge a quarter inch below the beam's top flange, on its fillet",
          BEAM_SIDE, _plate_on_fillet, frozenset({"beam_fit"})),
    Fault("columns off the flange", "two bracket bolt columns 16 in apart", ("bolt_bracket",), _columns_off_flange,
          FIT_FACES),
    Fault("panel shear left out", "a flange force's panel_shear load left out of its case", ("flange_force",),
          _drop_load("panel_shear"), frozenset({"panel_zone"})),
    Fault("column axial left out", "a flange force's axial load left out of its case", ("flange_force",),
          _drop_load("axial"), frozenset({"panel_zone"})),
    Fault("free end", "a flange force at a member end free to twist about its axis", ("flange_force",), _free_end,
          frozenset({"j10_stiffeners"})),
    Fault("short stiffener", "a 4 in long seat stiffener bent at its weld line past its yield", ("stiffened_seat",),
          _short_stiffener, frozenset({"flexural_yield"})),
    Fault("seated web in shear", "a W12x26 on its seat loaded past its web's shear yielding", ("seated", "stiffened_seat"),
          _seated_web_in_shear, frozenset({"shear_yield"})),
    Fault("thin support web", "a hanger from a W16x26 pulled past its web's local yielding", ("hanger",), _thin_support_web,
          frozenset({"web_local_yielding"})),
    Fault("cramped bracket bolts", "two bracket bolt columns 2-1/2 in apart on a W12x26's flange, no room for a socket",
          ("bolt_bracket",), _cramped_bracket, frozenset({"clearance"})),
    Fault("snug joint under cycles", "snug-tight bolts under a cyclic load, which RCSC 4.2 requires pretensioned", BOLTED,
          _snug_under_cycles, frozenset({"joint_type"})),
    Fault("cyclic overload", "three times the design load cycled 200 million times, past every detail's threshold",
          (*BOLTED, "stiffened_seat", "weld_bracket"), _cyclic_overload, FATIGUE),
    Fault("one-sided plate end", "a cyclic plate's end welded on one face, a detail without an encoded category",
          ("shear_tab", "stiffened_seat", "weld_bracket"), _one_sided_end, frozenset({"fatigue_detail"})),
)


def bases(registry: Registry, per_kind: int, seed: int) -> dict[str, list[Generated]]:
    """Generated designs that the deck passes with a fixed geometry: `per_kind` of each kind."""
    out: dict[str, list[Generated]] = {}
    want = per_kind * 11
    for g in generate(want * 3, seed, registry):
        if g.expected == "PASS" and not g.free and not g.toleranced and len(out.setdefault(g.kind, [])) < per_kind:
            out[g.kind].append(g)
        if sum(len(v) for v in out.values()) >= want:
            break
    return out


def status_and_modes(text: str, registry: Registry) -> tuple[str, tuple[str, ...]]:
    try:
        report = check_design(parse_design(text, "fault.petra", registry), registry, (SolverSource(),))
    except ComponentError:
        return "REJECTED", ()
    modes = []
    for o in report.outcomes:
        kind = type(o).__name__
        if kind in ("Refuted", "Open", "WithinMargin"):
            req = o.requirement if kind == "Open" else o.obligation.requirement
            modes.append(req.mode.id.split(".", 1)[1])
    return STATUS[type(report.verdict)], tuple(sorted(set(modes)))


def seed_faults(registry: Registry, per_kind: int = 3, seed: int = 101) -> Iterator[Caught]:
    """Each fault on up to `per_kind` passing designs of each kind it applies to."""
    pool = bases(registry, per_kind, seed)
    for fault in FAULTS:
        for kind in fault.kinds:
            for g in pool.get(kind, []):
                text = fault.edit(g.text, g)
                if text is None or text == g.text:
                    continue
                status, modes = status_and_modes(text, registry)
                expect = fault.modes or frozenset({g.governing})
                named = tuple(m for m in modes if m in expect)
                yield Caught(fault.name, g.name, kind, status, named, tuple(m for m in modes if m not in expect))
