"""Planted faults for the electronics deck's gate (docs/electronics_dc.md, the gate).
Tooling: nothing here changes a verdict.

A fault is one known defect put into a generated design that the deck passes. Each fault
names the mode that should refute it:

    led_overdriven   an LED's resistor sized for 1.5 times the LED's maximum current     led_rating
    hot_divider      a divider's resistors so low that they dissipate 3 times a rating     resistor_power
    high_voltage     a divider across 3 times its resistors' limiting element voltage     resistor_voltage
    no_headroom      a regulator fed half its dropout above its output                     regulator_headroom
    over_input       a regulator fed 10 % past its input limit                             regulator_input
    overload         a regulator's sink drawing 1.25 times its maximum output current      regulator_current
    no_min_load      an LM317's feedback resistors 10 times too high, with a 1 mA load     regulator_min_load
    hot_regulator    a regulator fed near its input limit at 0.9 of its maximum current    regulator_thermal
    small_supply     a supply that can deliver 1 uA                                        supply_current
    loose_divider    a divider's 1 % resistors swapped for 5 % ones                        divider_output
    drifting_rail    an adjustable regulator's 1 % feedback resistors swapped for 5 % ones rail_voltage
    dim_led          an LED's resistor 1.25 times its value                                led_current

The last three need a claim. Each states one at the deck's own extremes of its base, TIGHT
past them on the safe side, and the base must still pass with that claim before the fault
goes in. `seed_faults` puts each fault into passing designs of every kind it applies to.
The deck catches a fault when its verdict is FAIL, and names it when one of the fault's
modes is refuted. The gate wants every fault caught and named.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Callable, Iterator

from ...registry import Registry
from ...verdict import STATUS
from ..base import ComponentError
from .generate import (
    FLOATING,
    KINDS,
    MILLI,
    Claim,
    Generated,
    check,
    fact,
    generate,
    render,
    resistor_line,
    series_value,
    significant,
)

TIGHT = Fraction(1, 100)
LOOSE = "res.0603_5pct"
REGULATED = ("fixed", "floating", "grounded", "chain")


@dataclass(frozen=True)
class Fault:
    name: str
    defect: str
    kinds: tuple[str, ...]
    edit: Callable[[Generated, Registry], Generated | None]   # the defective design, or None where it does not apply
    modes: frozenset[str]                                     # the deck names the fault by one of these
    claims: Callable[[Generated], tuple[Claim, ...]] = lambda g: ()


@dataclass(frozen=True)
class Caught:
    fault: str
    base: str
    kind: str
    status: str               # the deck's verdict on the defective design, or "REJECTED" at lowering
    named: tuple[str, ...]    # the fault's modes among the refuted requirements
    others: tuple[str, ...]   # other modes refuted or open

    @property
    def caught(self) -> bool:
        return self.status == "FAIL"

    @property
    def is_named(self) -> bool:
        return bool(self.named)


# --- Edits ------------------------------------------------------------------------------------

def _resistor(g: Generated, name: str, part: str, value: Fraction) -> Generated:
    lines = tuple((n, resistor_line(name, part, value) if n == name else line) for n, line in g.lines)
    return replace(g, lines=lines, parts={**g.parts, name: part}, values={**g.values, name: value})


def _supply(g: Generated, lo: Fraction, hi: Fraction) -> Generated:
    return replace(g, supply=(significant(lo), significant(hi), g.supply[2]))


def _most(g: Generated, sink: str, most: Fraction, least: Fraction | None = None) -> Generated:
    return replace(g, loads=tuple((s, least if s == sink and least is not None else a, significant(most) if s == sink else b)
                                  for s, a, b in g.loads))


def _input_limit(g: Generated, registry: Registry) -> Fraction:
    part = g.parts[g.roles["regulator"]]
    if part == FLOATING:
        return g.rails[g.roles["regulator"]] + fact(registry, part, "vdiff_max")
    return fact(registry, part, "vin_max")


def _string_resistor(g: Generated, registry: Registry, current: Fraction) -> Fraction:
    """The resistance that runs the LED string at `current` from its rail's nominal voltage."""
    led = g.parts[g.roles["led"]]
    v0 = (fact(registry, led, "v0_min") + fact(registry, led, "v0_max")) / 2
    rd = (fact(registry, led, "rd_min") + fact(registry, led, "rd_max")) / 2
    count = int(g.roles["led_count"])
    return (g.rails[g.roles["led_rail"]] - count * (v0 + rd * current)) / current


def led_overdriven(g: Generated, registry: Registry) -> Generated | None:
    if "led" not in g.roles:
        return None
    r = g.roles["led_resistor"]
    target = _string_resistor(g, registry, Fraction(3, 2) * fact(registry, g.parts[g.roles["led"]], "if_max"))
    return _resistor(g, r, g.parts[r], series_value(registry, g.parts[r], target))


def hot_divider(g: Generated, registry: Registry) -> Generated | None:
    top, bottom = g.roles["divider_top"], g.roles["divider_bottom"]
    part = g.parts[top]
    scale = g.supply[1] ** 2 / (3 * fact(registry, part, "p70")) / (g.values[top] + g.values[bottom])
    if scale >= 1:
        return None
    g = _resistor(g, top, part, series_value(registry, part, g.values[top] * scale))
    return _resistor(g, bottom, part, series_value(registry, part, g.values[bottom] * scale))


def high_voltage(g: Generated, registry: Registry) -> Generated | None:
    volts = 3 * fact(registry, g.parts[g.roles["divider_top"]], "lev")
    return _supply(g, volts, volts * (1 + TIGHT))


def no_headroom(g: Generated, registry: Registry) -> Generated | None:
    reg = g.roles["regulator"]
    volts = g.rails[reg] + fact(registry, g.parts[reg], "vdo_max") / 2
    return _supply(g, volts * (1 - TIGHT), volts * (1 + TIGHT))


def over_input(g: Generated, registry: Registry) -> Generated | None:
    limit = _input_limit(g, registry)
    return _supply(g, limit * Fraction(11, 10), limit * Fraction(23, 20))


def overload(g: Generated, registry: Registry) -> Generated | None:
    return _most(g, g.roles["sink"], fact(registry, g.parts[g.roles["regulator"]], "iout_max") * Fraction(5, 4))


def no_min_load(g: Generated, registry: Registry) -> Generated | None:
    top, bottom = g.roles["regulator_top"], g.roles["regulator_bottom"]
    for r in (top, bottom):
        g = _resistor(g, r, g.parts[r], series_value(registry, g.parts[r], g.values[r] * 10))
    sink = g.roles["sink"]
    return _most(g, sink, next(b for s, _, b in g.loads if s == sink), least=MILLI)


def hot_regulator(g: Generated, registry: Registry) -> Generated | None:
    limit = _input_limit(g, registry)
    g = _supply(g, limit * Fraction(9, 10), limit * Fraction(19, 20))
    return _most(g, g.roles["sink"], fact(registry, g.parts[g.roles["regulator"]], "iout_max") * Fraction(9, 10))


def small_supply(g: Generated, registry: Registry) -> Generated | None:
    return replace(g, supply=(g.supply[0], g.supply[1], Fraction(1, 10**6)))


def _loosen(g: Generated, registry: Registry, top: str, bottom: str) -> Generated | None:
    tight = [r for r in (top, bottom) if g.parts[r] != LOOSE]
    for r in tight:
        g = _resistor(g, r, LOOSE, series_value(registry, LOOSE, g.values[r]))
    return g if tight else None


def loose_divider(g: Generated, registry: Registry) -> Generated | None:
    top, bottom = g.roles["divider_top"], g.roles["divider_bottom"]
    if not g.claims or g.values[top] < g.values[bottom] / 2:     # an output that hardly moves with the resistors
        return None
    return _loosen(g, registry, top, bottom)


def drifting_rail(g: Generated, registry: Registry) -> Generated | None:
    return _loosen(g, registry, g.roles["regulator_top"], g.roles["regulator_bottom"]) if g.claims else None


def dim_led(g: Generated, registry: Registry) -> Generated | None:
    if "led" not in g.roles or not g.claims:
        return None
    r = g.roles["led_resistor"]
    return _resistor(g, r, g.parts[r], series_value(registry, g.parts[r], g.values[r] * Fraction(5, 4)))


def window(quantity: str, role: str, unit: str, sides: tuple[str, ...] = ("<=", ">=")) -> Callable[[Generated], tuple[Claim, ...]]:
    """Claims at the base's extremes, TIGHT past them on the safe side; none unless the deck
    measured every side."""
    def claims(g: Generated) -> tuple[Claim, ...]:
        if role not in g.roles:
            return ()
        subject = f"b.{g.roles[role]}.{quantity}"
        if any((subject, side) not in g.extremes for side in sides):
            return ()
        return tuple(Claim(f"t{i + 1}", subject, side,
                           significant(g.extremes[(subject, side)] * (1 + TIGHT if side == "<=" else 1 - TIGHT)), unit, "pass")
                     for i, side in enumerate(sides))
    return claims


FAULTS: tuple[Fault, ...] = (
    Fault("led_overdriven", "an LED's resistor sized for 1.5 times its maximum current", ("led", "chain"), led_overdriven,
          frozenset({"led_rating"})),
    Fault("hot_divider", "a divider's resistors so low that they dissipate 3 times a rating", ("divider",), hot_divider,
          frozenset({"resistor_power"})),
    Fault("high_voltage", "a divider across 3 times its resistors' limiting element voltage", ("divider",), high_voltage,
          frozenset({"resistor_voltage"})),
    Fault("no_headroom", "a regulator fed half its dropout above its output", REGULATED, no_headroom,
          frozenset({"regulator_headroom"})),
    Fault("over_input", "a regulator fed 10 % past its input limit", REGULATED, over_input,
          frozenset({"regulator_input"})),
    Fault("overload", "a regulator's sink drawing 1.25 times its maximum output current", REGULATED, overload,
          frozenset({"regulator_current"})),
    Fault("no_min_load", "an LM317's feedback resistors 10 times too high, with a 1 mA load", ("floating",), no_min_load,
          frozenset({"regulator_min_load"})),
    Fault("hot_regulator", "a regulator fed near its input limit at 0.9 of its maximum current", REGULATED,
          hot_regulator, frozenset({"regulator_thermal"})),
    Fault("small_supply", "a supply that can deliver 1 uA", KINDS, small_supply, frozenset({"supply_current"})),
    Fault("loose_divider", "a divider's 1 % resistors swapped for 5 % ones", ("divider", "chain"), loose_divider,
          frozenset({"divider_output"}), window("output", "divider", "V")),
    Fault("drifting_rail", "an adjustable regulator's 1 % feedback resistors swapped for 5 % ones",
          ("floating", "grounded"), drifting_rail, frozenset({"rail_voltage"}), window("voltage", "regulator", "V")),
    Fault("dim_led", "an LED's resistor 1.25 times its value", ("led", "chain"), dim_led, frozenset({"led_current"}),
          window("current", "led", "mA", (">=",))),
)


# --- Seeding ------------------------------------------------------------------------------------

def status_and_modes(card: str, text: str, registry: Registry) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """The verdict, the refuted modes and the open modes, each mode without its "dc." prefix."""
    try:
        report = check(card, text, registry, "fault.petra")
    except ComponentError:
        return "REJECTED", (), ()
    refuted, open_ = set(), set()
    for o in report.outcomes:
        kind = type(o).__name__
        if kind == "Refuted":
            refuted.add(o.obligation.requirement.mode.id.split(".", 1)[1])
        elif kind == "Open":
            open_.add(o.requirement.mode.id.split(".", 1)[1])
    return STATUS[type(report.verdict)], tuple(sorted(refuted)), tuple(sorted(open_))


def bases(registry: Registry, per_kind: int, seed: int) -> dict[str, list[Generated]]:
    """Generated designs, claims left out, that the deck passes: up to `per_kind` of each kind."""
    out: dict[str, list[Generated]] = {kind: [] for kind in KINDS}
    for g in generate(per_kind * len(KINDS) * 20, seed, registry):
        if len(out[g.kind]) < per_kind:
            bare = replace(g, claims=())
            if status_and_modes(*render(bare), registry)[0] == "PASS":
                out[g.kind].append(bare)
        if all(len(v) >= per_kind for v in out.values()):
            break
    return out


def seed_faults(registry: Registry, per_kind: int = 2, seed: int = 101) -> Iterator[Caught]:
    """Each fault in up to `per_kind` passing designs of each kind it applies to. A fault
    that states a claim goes only into a base that passes with that claim."""
    pool = bases(registry, per_kind, seed)
    for fault in FAULTS:
        for kind in fault.kinds:
            for g in pool[kind]:
                base = replace(g, claims=fault.claims(g))
                if base.claims and status_and_modes(*render(base), registry)[0] != "PASS":
                    continue
                faulty = fault.edit(base, registry)
                if faulty is None or render(faulty) == render(base):
                    continue
                status, refuted, open_ = status_and_modes(*render(faulty), registry)
                named = tuple(m for m in refuted if m in fault.modes)
                others = tuple(m for m in (*refuted, *open_) if m not in named)
                yield Caught(fault.name, g.name, kind, status, named, others)
