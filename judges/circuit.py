"""Circuit fit: every conductor clamped in a terminal is a size the terminal accepts.

The judge reads the circuit's lines from the design IR and the two numbers it needs from
the registry: the cable's conductor area (an IEC 60228 size entry fixes it, a series entry
takes it from the `area` option) and the terminal's conductor range, conductor_min to
conductor_max. Those ratings are registry rows tagged judged, standing for a maker's
datasheet tested to IEC 60998-2-2. A wire connected at either port of a terminal is
clamped in it.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from petra.ir import Component, Design, Fixed, ParamRef, Ref
from petra.registry import Registry

MM2 = Fraction(1, 10**6)


@dataclass(frozen=True)
class Clamped:
    subject: str
    area: tuple[Fraction, Fraction]
    terminal: str
    smallest: Fraction
    largest: Fraction

    def check(self) -> tuple[str, str] | None:
        lo, hi = self.area
        if hi > self.largest or lo < self.smallest:
            return "circuit.terminal.conductor_area", (f"{_mm2(lo, hi)} conductor in {self.terminal}, which clamps {_mm2(self.smallest)} to "
                    f"{_mm2(self.largest)} (registry, tagged judged)")
        return None


def _mm2(lo: Fraction, hi: Fraction | None = None) -> str:
    text = lambda x: f"{float(x / MM2):g}"
    return f"{text(lo)} mm2" if hi is None or hi == lo else f"[{text(lo)}, {text(hi)}] mm2"


def _options(args: tuple) -> dict[str, object]:
    return {a.parts[0]: b for a, b in zip(args[1::2], args[2::2]) if isinstance(a, Ref) and len(a.parts) == 1}


def _area(options: dict, design: Design, registry: Registry) -> tuple[Fraction, Fraction] | None:
    cable = options.get("cable")
    part = registry.parts.get(".".join(cable.parts)) if isinstance(cable, Ref) else None
    if part is not None and "area" in part.fixes:
        return part.fixes["area"].lo, part.fixes["area"].hi
    area = options.get("area")
    if isinstance(area, Fixed):
        return area.quantity.value.lo, area.quantity.value.hi
    if isinstance(area, ParamRef) and area.name in design.params:
        value = design.params[area.name].range.value
        return value.lo, value.hi
    return None


def facts(component: Component, design: Design, registry: Registry) -> tuple[list[Clamped], list[str]]:
    """(one Clamped per wire end in a terminal, what the judge could not read)."""
    wires, terminals, links = {}, {}, []
    for attr in component.attrs:
        name = attr.args[0].parts[0] if attr.args and isinstance(attr.args[0], Ref) else None
        if attr.key == "wire":
            wires[name] = _options(attr.args)
        elif attr.key == "terminal":
            part = _options(attr.args).get("part")
            terminals[name] = ".".join(part.parts) if isinstance(part, Ref) else None
        elif attr.key == "connect" and len(attr.args) == 3:
            links.append((attr.args[0].parts[0], attr.args[2].parts[0]))
    out, undecided = [], []
    for a, b in links:
        for wire, terminal in ((a, b), (b, a)):
            if wire not in wires or terminal not in terminals:
                continue
            subject = f"{component.name}.{wire} in {component.name}.{terminal}"
            area = _area(wires[wire], design, registry)
            part = registry.parts.get(terminals[terminal] or "")
            props = part.props if part is not None else {}
            smallest, largest = props.get("conductor_min"), props.get("conductor_max")
            if area is None or not hasattr(smallest, "value") or not hasattr(largest, "value"):
                undecided.append(f"{subject}: the conductor area or the terminal's conductor range is not a stated value")
                continue
            out.append(Clamped(subject, area, terminals[terminal], smallest.value.lo, largest.value.hi))
    return out, undecided
