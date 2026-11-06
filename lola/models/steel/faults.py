"""Manufactured faults for the steel deck's gate (docs/steel_connections.md §8, §9 item 6).
Tooling: nothing here changes a verdict.

A fault is one known defect put into a design the deck passes: a fillet far under Table
J2.4's minimum, a short edge, holes too close or too far apart, oversized holes in a
bearing joint, Group 150 bolts in tension left snug, a shear tab too thick to rotate, a
slender seat stiffener, a lapped fillet as thick as its plate, bolts against a hanger's
stem, a cope deeper than half the beam, a load past the governing strength. `seed_faults`
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
    return text.replace("  top ", f"  cope {cope}\n  top ", 1)


def _overload(text: str, g: Generated) -> str | None:
    """Every load raised in proportion so the governing check reaches about 1.3 at least,
    for u growing at least as the square root of the load."""
    factor = (Fraction(13, 10) / Fraction(g.utilisation)) ** 2

    def raised(m: re.Match) -> str:
        return f"  on c1 {m.group(1)} in [0 kip, {float(Fraction(m.group(2)) * factor):.3f} kip]"
    return re.sub(r"^  on c1 (\w+) in \[0 kip, ([0-9.]+) kip\]$", raised, text, flags=re.M)


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
    Fault("thick lap fillet", "a fillet as thick as the lapped plate it runs along", ("weld_bracket",), _thick_lap_fillet,
          frozenset({"fillet_size"})),
    Fault("bolts at the stem", "a 1-1/4 in hanger gauge, the bolts against the stem", ("hanger",), _bolts_at_stem,
          frozenset({"clearance", "prying", "edge_max"})),
    Fault("deep cope", "a cope 3/5 of the beam deep", ("shear_tab", "double_angle", "single_angle", "shear_tee"), _deep_cope,
          frozenset({"cope_buckling"})),
    Fault("overload", "a load past the governing strength", ("shear_tab", "double_angle", "single_angle", "shear_tee",
          "shear_end_plate", "seated", "stiffened_seat", "flange_force", "bolt_bracket", "weld_bracket", "hanger"), _overload,
          frozenset()),
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
        report = check_design(parse_design(text, "fault.lola", registry), registry, (SolverSource(),))
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
