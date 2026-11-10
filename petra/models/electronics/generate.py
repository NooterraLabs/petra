"""Generated boards for the electronics deck's gate (docs/electronics_dc.md, the gate).
Tooling: nothing here changes a verdict.

`generate(n, seed, registry, start)` yields designs round-robin over KINDS. Each is a
design with one board named b, fed by one supply named vin, and a card in environment
indoor_dry that gives the supply's voltage and capacity, with one load case named run
when the board has a sink:

    divider    a divider from the supply, with a window claim on its output
    led        a string of LEDs and its resistor, with a claim on the least current
    fixed      a fixed regulator and a sink, with a claim on the junction temperature
    floating   an LM317-style regulator, its two resistors and a sink, with a window claim
    grounded   an adjustable LDO, its two resistors and a sink, with a window claim
    chain      a fixed regulator feeding an LED string, a divider and a sink

Parts, values and loads are drawn at random: each resistor from its part's series and
range, each supply from common rails with a stated spread, each load from a range that
sometimes passes a part's rating. So a design may pass or fail its coverage. The gate
wants each one decided.

Each design stays inside the deck's validity. indoor_dry's coldest ambient is above every
part's lowest temperature. An LED string is drawn so that its least current, by a float
estimate here, is at least LED_FLOOR times the LED's lowest fitted current. A draw that
cannot meet this, or that the deck's lowering rejects, is drawn again, and
`Generated.redraws` counts the draws. Nothing else is redrawn.

Claims carry a margin measured with the deck, as the steel gate measures its loads. A
probe run claims each quantity at a bound it cannot meet. The refutation, moved to the
worst corner, gives the quantity's extreme. The claim then sits at extreme (1 + DELTA k)
on the safe side (target "pass") or extreme (1 - DELTA k) past it (target "fail"), with k
drawn from [1, 4]. A probe the deck does not refute gives no claim.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction
from typing import Callable, Iterator, Mapping

from ...lang import parse_design
from ...pipeline import check_design
from ...registry import Registry
from ...registry.electronics import RESISTORS, neighbours
from ...solvers import SolverSource
from ..base import ComponentError

DELTA = Fraction(1, 50)
PASS_SHARE = 0.85
"""The share of claims aimed at the safe side."""
LED_FLOOR = 2
MAX_REDRAWS = 200
SIGNATURE = 'signed "gate@petra.dev" source "electronics gate generator"'
KINDS = ("divider", "led", "fixed", "floating", "grounded", "chain")
RAILS = (Fraction(33, 10), Fraction(5), Fraction(9), Fraction(12), Fraction(24))
SPREADS = (Fraction(1, 200), Fraction(1, 100), Fraction(1, 50), Fraction(1, 20))
CAPACITIES = (Fraction(1, 2), Fraction(1), Fraction(2), Fraction(3))
FIXED = ("reg.ldo1117_3v3_sot223", "reg.ldo1117_5v0_sot223")
FLOATING = "reg.lm317_to220"
GROUNDED = "reg.ldo_adj_sot23_5"
LEDS = ("led.red_0603", "led.white_0603")
TOLERANCE = {"F": Fraction(1, 100), "J": Fraction(1, 20)}
REACH = 135
"""K: the most the deck moves a resistor's temperature from its reference (155 - 20)."""
COLD = 20
"""K: an LED junction at indoor_dry's coldest ambient sits this far below its 25 degC reference."""
MILLI = Fraction(1, 1000)
IMPOSSIBLE = {("<=", "V"): Fraction(1, 1000), (">=", "V"): Fraction(1000), (">=", "mA"): Fraction(10**6),
              ("<=", "degC"): Fraction(1)}
"""A probe's bound, which no design meets."""
SCALE = {"V": Fraction(1), "mA": Fraction(1000), "degC": Fraction(1)}
"""A finding's number in SI -> the claim's unit."""


def decimal(x: Fraction) -> str:
    """The exact decimal text of a terminating fraction."""
    text = format((Decimal(x.numerator) / Decimal(x.denominator)).normalize(), "f")
    if Fraction(text) != x:
        raise ValueError(f"{x} has no short decimal text")
    return text


def significant(x: Fraction, digits: int = 4) -> Fraction:
    """x rounded to `digits` significant figures."""
    if x == 0:
        return x
    q = Fraction(10) ** (math.floor(math.log10(abs(x))) - digits + 1)
    return round(x / q) * q


def ohms(value: Fraction) -> str:
    for scale, unit in ((Fraction(10**6), "Mohm"), (Fraction(1000), "kohm")):
        if value >= scale:
            return f"{decimal(value / scale)} {unit}"
    return f"{decimal(value)} ohm"


def resistor_line(name: str, part: str, value: Fraction) -> str:
    return f"resistor {name} part {part} value {ohms(value)}"


@dataclass(frozen=True)
class Claim:
    name: str
    subject: str          # "b.<element>.<quantity>"
    side: str             # "<=" or ">="
    bound: Fraction       # in `unit`
    unit: str
    target: str           # "pass" | "fail"

    def line(self) -> str:
        return f"claim {self.name}: {self.subject} {self.side} {decimal(self.bound)} {self.unit}"


@dataclass(frozen=True)
class Generated:
    name: str
    kind: str
    supply: tuple[Fraction, Fraction, Fraction]           # vin's least and most voltage, its capacity in A
    lines: tuple[tuple[str, str], ...]                     # (element, its board line), in order
    loads: tuple[tuple[str, Fraction, Fraction], ...]      # (sink, least and most current in A) of load case run
    roles: Mapping[str, str]                               # "led", "led_resistor", "divider", "regulator", ...
    parts: Mapping[str, str]                               # element -> registry id
    values: Mapping[str, Fraction]                         # resistor -> ohm
    rails: Mapping[str, Fraction]                          # rail -> its nominal voltage, by a float estimate
    claims: tuple[Claim, ...]
    extremes: Mapping[tuple[str, str], Fraction]           # (subject, side) -> the deck's extreme, in the claim's unit
    redraws: int

    @property
    def card(self) -> str:
        return render(self)[0]

    @property
    def text(self) -> str:
        return render(self)[1]


def render(g: Generated) -> tuple[str, str]:
    """The card's text and the design's."""
    lo, hi, capacity = g.supply
    card = ["petra 0", "", f'card "{g.name}" {{', '  owner "gate@petra.dev"', "  environment indoor_dry", "}", "",
            f"given voltage in [{decimal(lo)} V, {decimal(hi)} V] {SIGNATURE}",
            f"given capacity in [{decimal(capacity)} A, {decimal(capacity)} A] {SIGNATURE}"]
    if g.loads:
        card += ["", "load run {"]
        card += [f"  on b.{sink} current in [{decimal(a / MILLI)} mA, {decimal(b / MILLI)} mA]" for sink, a, b in g.loads]
        card += [f"  {SIGNATURE}", "}"]
    if g.claims:
        card += [""] + [c.line() for c in g.claims]
    out = ["petra 0", "", "board b {", "  supply vin voltage given voltage capacity given capacity"]
    out += [f"  {line}" for _, line in g.lines]
    out.append("}")
    return "\n".join(card) + "\n", "\n".join(out) + "\n"


def fact(registry: Registry, part: str, prop: str) -> Fraction:
    return registry.fact(f"{part}.{prop}").value.lo


def series_value(registry: Registry, part: str, target: Fraction) -> Fraction:
    """The value of the part's series nearest `target`, inside the part's range."""
    steps = RESISTORS[part][1]
    lo, hi = fact(registry, part, "r_min"), fact(registry, part, "r_max")
    t = min(max(target, lo), hi)
    below, above = neighbours(t, steps, registry.constants)
    return min(max(below if t - below <= above - t else above, lo), hi)


def led_least(registry: Registry, led: str, count: int, rail_low: Fraction, part: str, value: Fraction) -> Fraction:
    """A lower estimate of an LED string's least current: the highest forward voltage at the
    coldest junction, the most resistance."""
    drop = count * (fact(registry, led, "v0_max") - fact(registry, led, "tc_min") * COLD)
    tolerance = TOLERANCE[RESISTORS[part][2]]
    r = value * (1 + tolerance) * (1 + fact(registry, part, "tcr") * REACH)
    return (rail_low - drop) / (r + count * fact(registry, led, "rd_max"))


class _Redraw(Exception):
    """The sample cannot be built as drawn."""


class _Draw:
    def __init__(self, rng: random.Random, registry: Registry):
        self.rng, self.registry = rng, registry
        self.supply: tuple[Fraction, Fraction, Fraction] | None = None
        self.lines: list[tuple[str, str]] = []
        self.loads: list[tuple[str, Fraction, Fraction]] = []
        self.roles: dict[str, str] = {}
        self.parts: dict[str, str] = {}
        self.values: dict[str, Fraction] = {}
        self.rails: dict[str, Fraction] = {}
        self.probes: list[tuple[str, str, str]] = []      # (subject, side, unit)
        self.counts: dict[str, int] = {}

    def fact(self, part: str, prop: str) -> Fraction:
        return fact(self.registry, part, prop)

    def uniform(self, a: float, b: float) -> Fraction:
        return Fraction(self.rng.uniform(a, b)).limit_denominator(1000)

    def next(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}{self.counts[prefix]}"

    def draw_supply(self, choices: tuple[Fraction, ...] = RAILS) -> tuple[Fraction, Fraction]:
        nominal, spread = self.rng.choice(choices), self.rng.choice(SPREADS)
        self.supply = (nominal * (1 - spread), nominal * (1 + spread), self.rng.choice(CAPACITIES))
        self.rails["vin"] = nominal
        return self.supply[0], self.supply[1]

    def resistor(self, target: Fraction, part: str | None = None) -> str:
        part = part or self.rng.choice(tuple(RESISTORS))
        value = series_value(self.registry, part, target)
        name = self.next("r")
        self.parts[name], self.values[name] = part, value
        self.lines.append((name, resistor_line(name, part, value)))
        return name

    def regulator(self, part: str, rail: str, top: str | None = None, bottom: str | None = None) -> str:
        name = self.next("v")
        feedback = f" top {top} bottom {bottom}" if top is not None else ""
        self.lines.append((name, f"regulator {name} part {part} from {rail}{feedback}"))
        self.parts[name] = part
        self.roles["regulator"] = name
        if top is not None:
            self.roles["regulator_top"], self.roles["regulator_bottom"] = top, bottom
        return name

    def sink(self, rail: str, least_ma: int, most_ma: int) -> str:
        name = self.next("s")
        self.lines.append((name, f"sink {name} from {rail}"))
        self.loads.append((name, least_ma * MILLI, most_ma * MILLI))
        self.roles["sink"] = name
        return name

    def probe(self, subject: str, side: str, unit: str) -> None:
        self.probes.append((subject, side, unit))


def _divider(d: _Draw, rail: str = "vin") -> None:
    part = d.rng.choice(tuple(RESISTORS))
    k = d.uniform(0.1, 0.9)
    bottom_target = Fraction(10 ** d.rng.uniform(2, 5)).limit_denominator(10)
    top = d.resistor(bottom_target * (1 - k) / k, part)
    bottom = d.resistor(bottom_target, part)
    name = d.next("div")
    d.lines.append((name, f"divider {name} from {rail} top {top} bottom {bottom}"))
    d.roles.update(divider=name, divider_top=top, divider_bottom=bottom, divider_rail=rail)
    d.probe(f"b.{name}.output", "<=", "V")
    d.probe(f"b.{name}.output", ">=", "V")


def _string(d: _Draw, rail: str, rail_low: Fraction, rail_high: Fraction) -> None:
    led = d.rng.choice(LEDS)
    v0_max = d.fact(led, "v0_max")
    most = int((rail_low - 1) / (v0_max + Fraction(1, 5)))
    if most < 1:
        raise _Redraw
    count = d.rng.randint(1, min(most, 6))
    current = d.uniform(2, 12) * MILLI
    v0 = (d.fact(led, "v0_min") + v0_max) / 2
    rd = (d.fact(led, "rd_min") + d.fact(led, "rd_max")) / 2
    target = ((rail_low + rail_high) / 2 - count * (v0 + rd * current)) / current
    if target <= 0:
        raise _Redraw
    resistor = d.resistor(target)
    if led_least(d.registry, led, count, rail_low, d.parts[resistor], d.values[resistor]) < LED_FLOOR * d.fact(led, "i_min"):
        raise _Redraw
    name = d.next("d")
    d.lines.append((name, f"led {name} part {led} from {rail} resistor {resistor}" + (f" count {count}" if count > 1 else "")))
    d.parts[name] = led
    d.roles.update(led=name, led_resistor=resistor, led_rail=rail, led_count=str(count))
    d.probe(f"b.{name}.current", ">=", "mA")


def _kind_divider(d: _Draw) -> None:
    d.draw_supply()
    _divider(d)


def _kind_led(d: _Draw) -> None:
    lo, hi = d.draw_supply()
    _string(d, "vin", lo, hi)


def _kind_fixed(d: _Draw) -> None:
    part = d.rng.choice(FIXED)
    vout = (d.fact(part, "vout_min") + d.fact(part, "vout_max")) / 2
    d.draw_supply(tuple(r for r in RAILS if vout + d.fact(part, "vdo_max") < r <= d.fact(part, "vin_max")))
    reg = d.regulator(part, "vin")
    d.rails[reg] = vout
    least = d.rng.randint(1, 50)
    d.sink(reg, least, least + d.rng.randint(10, 400))
    d.probe(f"b.{reg}.junction_temperature", "<=", "degC")


def _adjustable(d: _Draw, part: str, top_ohm: Fraction, bottom_ohm: Fraction, vout: Fraction, headroom: Fraction,
                load: tuple[int, int]) -> None:
    limit = vout + d.fact(part, "vdiff_max") if part == FLOATING else d.fact(part, "vin_max")
    rails = tuple(r for r in RAILS if vout + headroom <= r <= limit)
    if not rails:
        raise _Redraw
    d.draw_supply(rails)
    pair = d.rng.choice(tuple(RESISTORS))
    top, bottom = d.resistor(top_ohm, pair), d.resistor(bottom_ohm, pair)
    reg = d.regulator(part, "vin", top, bottom)
    d.rails[reg] = vout
    least = d.rng.randint(1, load[0])
    d.sink(reg, least, least + d.rng.randint(5, load[1]))
    d.probe(f"b.{reg}.voltage", "<=", "V")
    d.probe(f"b.{reg}.voltage", ">=", "V")


def _kind_floating(d: _Draw) -> None:
    vref = (d.fact(FLOATING, "vref_min") + d.fact(FLOATING, "vref_max")) / 2
    top, vout = d.uniform(100, 240), d.uniform(1.5, 15)
    _adjustable(d, FLOATING, top, top * (vout / vref - 1), vout, d.fact(FLOATING, "vdo_max"), (20, 500))


def _kind_grounded(d: _Draw) -> None:
    vref = (d.fact(GROUNDED, "vref_min") + d.fact(GROUNDED, "vref_max")) / 2
    bottom = Fraction(10 ** d.rng.uniform(4, 5)).limit_denominator(10)
    vout = d.uniform(1.5, 5.5)
    _adjustable(d, GROUNDED, bottom * (vout / vref - 1), bottom, vout, d.fact(GROUNDED, "vdo_max"), (10, 100))


def _kind_chain(d: _Draw) -> None:
    part = d.rng.choice(FIXED)
    d.draw_supply((Fraction(9), Fraction(12)))
    reg = d.regulator(part, "vin")
    low, high = d.fact(part, "vout_min"), d.fact(part, "vout_max")
    d.rails[reg] = (low + high) / 2
    _string(d, reg, low, high)
    _divider(d, d.rng.choice(("vin", reg)))
    least = d.rng.randint(1, 50)
    d.sink(reg, least, least + d.rng.randint(10, 200))


BUILDERS: Mapping[str, Callable[[_Draw], None]] = {
    "divider": _kind_divider, "led": _kind_led, "fixed": _kind_fixed, "floating": _kind_floating,
    "grounded": _kind_grounded, "chain": _kind_chain,
}


def check(card: str, text: str, registry: Registry, name: str = "gate.petra"):
    return check_design(parse_design(card, text, name, registry), registry, (SolverSource(),))


def extremes_of(g: Generated, probes: list[tuple[str, str, str]], registry: Registry) -> dict[tuple[str, str], Fraction]:
    """The deck's extreme of each probed quantity, from the worst-corner refutation of a
    claim it cannot meet; a probe the deck does not refute is left out."""
    claims = tuple(Claim(f"probe{j}", subject, side, IMPOSSIBLE[(side, unit)], unit, "fail")
                   for j, (subject, side, unit) in enumerate(probes))
    report = check(*render(replace(g, claims=claims)), registry)
    out: dict[tuple[str, str], Fraction] = {}
    for c in claims:
        found = [f.governing for f in report.findings if f.entry == c.name and f.outcome == "refuted" and f.governing]
        if not found:
            continue
        # a refuted `q <= b` reports q as its demand; a refuted `q >= b` reports q as its capacity
        values = [Fraction(v.demand if c.side == "<=" else v.capacity) for v in found]
        out[(c.subject, c.side)] = (max(values) if c.side == "<=" else min(values)) * SCALE[c.unit]
    return out


def claimed(g: Generated, probes: list[tuple[str, str, str]], rng: random.Random, registry: Registry) -> Generated:
    extremes = extremes_of(g, probes, registry) if probes else {}
    units = {(subject, side): unit for subject, side, unit in probes}
    claims = []
    for (subject, side), x in extremes.items():
        target = "pass" if rng.random() < PASS_SHARE else "fail"
        k = DELTA * Fraction(rng.uniform(1, 4)).limit_denominator(100)
        up = (side == "<=") == (target == "pass")
        claims.append(Claim(f"c{len(claims) + 1}", subject, side, significant(x * (1 + k) if up else x * (1 - k)),
                            units[(subject, side)], target))
    return replace(g, claims=tuple(claims), extremes=extremes)


def draw(index: int, seed: int, registry: Registry) -> Generated:
    kind = KINDS[index % len(KINDS)]
    rng = random.Random(seed * 1_000_003 + index)
    for redraws in range(MAX_REDRAWS):
        d = _Draw(rng, registry)
        try:
            BUILDERS[kind](d)
            g = Generated(f"gate-{seed}-{index:05d}", kind, d.supply, tuple(d.lines), tuple(d.loads), dict(d.roles),
                          dict(d.parts), dict(d.values), dict(d.rails), (), {}, redraws)
            return claimed(g, d.probes, rng, registry)
        except (_Redraw, ComponentError):
            continue
    raise RuntimeError(f"no {kind} design drawn in {MAX_REDRAWS} tries")


def generate(n: int, seed: int, registry: Registry, start: int = 0) -> Iterator[Generated]:
    for index in range(start, start + n):
        yield draw(index, seed, registry)
