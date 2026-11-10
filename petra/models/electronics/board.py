"""The `board` component kind: its typed model, its lowering and its grammar. Trusted.

A board is a set of rails and the parts that hang from them, checked at DC. Its lines,
one per line inside the block, are GRAMMAR below (`petra kinds board` prints them):

    supply    a rail fed from outside, with a signed voltage range and an optional capacity
    regulator a linear regulator from one rail; its name is its output rail
    resistor  a chip resistor; with `from <rail>` it runs from that rail to ground
    divider   two resistors in series from a rail to ground
    led       a string of LEDs and its current-limit resistor, from a rail to ground
    sink      a load whose current each load case signs

Rails and elements share one namespace. Every resistor is placed exactly once: by its own
`from`, or by the one divider, LED or adjustable regulator that names it. A regulator's
input rail is a supply or another regulator, and the chain of regulators has no loop.

A resistor's value is one of its part's preferred values (IEC 60063, the part's E24 or E96
series) inside the part's range; lowering refuses any other value and names the series
values beside it. Load field: current on `<board>.<sink>`. Claim paths:
`<board>.<rail>.voltage`, `<board>.<divider>.output`, `<board>.<led>.current`,
`<board>.<resistor>.power_utilisation`, `<board>.<regulator>.junction_temperature`.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Callable, Mapping, Union

from ...ir import Arg, Bound, Component, Design, Exceeds, Fixed, Input, ParamRef, Ref, Span
from ...registry import Registry
from ...registry.electronics import neighbours, preferred
from ...kernel import Interval
from ...units import CURRENT, DIMENSIONLESS, RESISTANCE, TEMPERATURE, VOLTAGE, Dim, Quantity, readable_text
from ..base import GIVEN_BOUND, ComponentError, Field, Grammar

# --- Typed model ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Supply:
    name: str
    voltage: Input | ParamRef
    capacity: Input | ParamRef | None     # None -> the supply-current check needs it


@dataclass(frozen=True, slots=True)
class Regulator:
    """`name` is also the output rail. `style` is the part's family less "regulator_":
    fixed, floating (the reference sits between output and adjust, as on an LM317) or
    grounded (the reference sits between feedback and ground, as on an adjustable LDO).
    An adjustable regulator names its feedback resistors: `top` from the output, `bottom`
    to ground."""

    name: str
    part: str
    style: str
    source: str
    top: str | None
    bottom: str | None


@dataclass(frozen=True, slots=True)
class Resistor:
    """Nominal value = the series constant `mantissa` times `decade`. `rail` is set when
    the resistor runs from that rail to ground on its own."""

    name: str
    part: str
    mantissa: str
    decade: Fraction
    rail: str | None


@dataclass(frozen=True, slots=True)
class Divider:
    name: str
    rail: str
    top: str
    bottom: str


@dataclass(frozen=True, slots=True)
class Led:
    name: str
    part: str
    rail: str
    resistor: str
    count: int


@dataclass(frozen=True, slots=True)
class Sink:
    """`draws`: load case -> the signed current the sink draws in it."""

    name: str
    rail: str
    draws: Mapping[str, Input | ParamRef]


Element = Union[Supply, Regulator, Resistor, Divider, Led, Sink]


@dataclass(frozen=True)
class Board:
    """`ambient` and `environment` repeat the design's. `place` gives, per resistor, the
    element that places it: itself when it runs to ground on its own, else the divider,
    LED or regulator that names it."""

    name: str
    elements: Mapping[str, Element]
    place: Mapping[str, str]
    span: Span
    ambient: Input | ParamRef | None
    environment: str | None

    def on(self, rail: str) -> tuple[Element, ...]:
        """The elements that draw current from `rail`, in declaration order."""
        return tuple(e for e in self.elements.values() if _draws_from(e) == rail)


def _draws_from(e: Element) -> str | None:
    match e:
        case Regulator():
            return e.source
        case Resistor():
            return e.rail
        case Divider() | Led() | Sink():
            return e.rail
    return None


FAMILIES: Mapping[str, str] = {
    "resistor": "resistor",
    "led": "led",
    "regulator_fixed": "regulator",
    "regulator_floating": "regulator",
    "regulator_grounded": "regulator",
}
"""Registry material family -> the line that takes it."""

ADJUSTABLE = frozenset({"floating", "grounded"})

QOI_ELEMENT: Mapping[str, tuple[type, ...]] = {
    "voltage": (Supply, Regulator),
    "output": (Divider,),
    "current": (Led,),
    "power_utilisation": (Resistor,),
    "junction_temperature": (Regulator,),
}
"""Claimable quantity -> the elements it is a quantity of."""

QOI_BOUND_DIMS: Mapping[str, Dim] = {
    "voltage": VOLTAGE,
    "output": VOLTAGE,
    "current": CURRENT,
    "power_utilisation": DIMENSIONLESS,
    "junction_temperature": TEMPERATURE,
}

QOI_DIMS: Mapping[str, str] = {
    "voltage": "a voltage",
    "output": "a voltage",
    "current": "a current",
    "power_utilisation": "a fraction of the derated rating",
    "junction_temperature": "a temperature",
}


# --- Lowering ---------------------------------------------------------------------------

Say = Callable[[str], None]


def _reporter(problems: list[str], span: Span, what: str) -> Say:
    return lambda message: problems.append(f"{span.path}:{span.line}:{span.col}: {what}: {message}")


def _options(args: tuple[Arg, ...], allowed: frozenset[str], say: Say) -> dict[str, Arg]:
    """Keyword-value pairs: `part res.0603_1pct value 4.99 kohm from v3`."""
    found: dict[str, Arg] = {}
    if len(args) % 2:
        say("expects keyword-value pairs")
    for key, value in zip(args[::2], args[1::2]):
        word = key.parts[0] if isinstance(key, Ref) and len(key.parts) == 1 else None
        if word not in allowed:
            say(f"expects one of {', '.join(sorted(allowed))}")
        elif word in found:
            say(f"gives {word} twice")
        else:
            found[word] = value
    return found


def _name(arg: Arg | None) -> str | None:
    return arg.parts[0] if isinstance(arg, Ref) and len(arg.parts) == 1 else None


def _signed(arg: Arg | None, path: str, dim: Dim, design: Design) -> Input | ParamRef | None:
    if isinstance(arg, Bound) and arg.range.dim == dim:
        return Input(path, arg.range, arg.signature, arg.kind, arg.span, arg.mean)
    if isinstance(arg, ParamRef) and arg.name in design.params and design.params[arg.name].range.dim == dim:
        return arg
    return None


def _part(arg: Arg | None, line: str, registry: Registry, say: Say) -> str | None:
    pid = ".".join(arg.parts) if isinstance(arg, Ref) else None
    ids = [m for m, mat in registry.materials.items() if FAMILIES.get(mat.family) == line]
    if pid is None:
        say(f"needs part <registry {line} id>")
    elif pid not in registry.materials or FAMILIES.get(registry.materials[pid].family) != line:
        say(registry.unknown(pid, line, ids))
    else:
        return pid
    return None


def _supply(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Supply | None:
    opts = _options(args, frozenset({"voltage", "capacity"}), say)
    voltage = _signed(opts.get("voltage"), f"{path}.voltage", VOLTAGE, design)
    capacity = _signed(opts.get("capacity"), f"{path}.capacity", CURRENT, design)
    if voltage is None:
        say(f"needs voltage {GIVEN_BOUND} in V, or param <name>")
    if "capacity" in opts and capacity is None:
        say(f"capacity needs {GIVEN_BOUND} in A, or param <name>")
    if voltage is None or "capacity" in opts and capacity is None:
        return None
    return Supply(name, voltage, capacity)


def _regulator(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Regulator | None:
    opts = _options(args, frozenset({"part", "from", "top", "bottom"}), say)
    part = _part(opts.get("part"), "regulator", registry, say)
    source = _name(opts.get("from"))
    if source is None:
        say("needs from <rail>")
    top, bottom = _name(opts.get("top")), _name(opts.get("bottom"))
    if part is None or source is None:
        return None
    style = registry.materials[part].family.removeprefix("regulator_")
    if style in ADJUSTABLE and (top is None or bottom is None):
        say(f"{part} is adjustable, so it needs top <resistor> bottom <resistor>")
        return None
    if style not in ADJUSTABLE and ("top" in opts or "bottom" in opts):
        say(f"{part} has a fixed output, so it takes no top or bottom resistor")
        return None
    return Regulator(name, part, style, source, top, bottom)


def _resistor(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Resistor | None:
    opts = _options(args, frozenset({"part", "value", "from"}), say)
    part = _part(opts.get("part"), "resistor", registry, say)
    value = opts.get("value")
    rail = _name(opts.get("from"))
    if "from" in opts and rail is None:
        say("from needs a rail name")
    if not (isinstance(value, Fixed) and value.quantity.dim == RESISTANCE and value.quantity.value.lo == value.quantity.value.hi):
        say("needs value <resistance>, one value such as 4.99 kohm")
        return None
    if part is None or "from" in opts and rail is None:
        return None
    r = value.quantity.value.lo
    steps = int(registry.property(part, "steps").value.lo)
    low, high = registry.property(part, "r_min").value.lo, registry.property(part, "r_max").value.hi
    found = preferred(r, steps, registry.constants)
    if found is None:
        below, above = neighbours(r, steps, registry.constants) if r > 0 else (low, low)
        say(f"{_ohms(r)} is not an E{steps} value, the series {part} is made in; the nearest are "
            f"{_ohms(below)} and {_ohms(above)}")
        return None
    if not low <= r <= high:
        say(f"{part} is made from {_ohms(low)} to {_ohms(high)}, not {_ohms(r)}")
        return None
    return Resistor(name, part, found[0], found[1], rail)


def _ohms(r: Fraction) -> str:
    return readable_text(Quantity(Interval(r, r), RESISTANCE))


def _divider(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Divider | None:
    opts = _options(args, frozenset({"from", "top", "bottom"}), say)
    rail, top, bottom = (_name(opts.get(k)) for k in ("from", "top", "bottom"))
    if None in (rail, top, bottom):
        say("reads `divider <name> from <rail> top <resistor> bottom <resistor>`")
        return None
    if top == bottom:
        say("top and bottom are two different resistors")
        return None
    return Divider(name, rail, top, bottom)


def _led(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Led | None:
    opts = _options(args, frozenset({"part", "from", "resistor", "count"}), say)
    part = _part(opts.get("part"), "led", registry, say)
    rail, resistor = _name(opts.get("from")), _name(opts.get("resistor"))
    if rail is None or resistor is None:
        say("needs from <rail> resistor <resistor>")
    count = opts.get("count")
    n = 1
    if count is not None:
        q = count.quantity if isinstance(count, Fixed) else None
        if q is None or q.dim != DIMENSIONLESS or q.value.lo != q.value.hi or q.value.lo.denominator != 1 or q.value.lo < 1:
            say("count needs a whole number of LEDs in series, at least one")
            return None
        n = int(q.value.lo)
    if part is None or rail is None or resistor is None:
        return None
    return Led(name, part, rail, resistor, n)


def _sink(path: str, name: str, args, design: Design, registry: Registry, say: Say) -> Sink | None:
    rail = _name(_options(args, frozenset({"from"}), say).get("from"))
    if rail is None:
        say("needs from <rail>")
        return None
    return Sink(name, rail, {})


_READERS = {"supply": _supply, "regulator": _regulator, "resistor": _resistor, "divider": _divider,
            "led": _led, "sink": _sink}

GRAMMAR = Grammar(
    required=(
        Field("supply", f"<name> voltage {GIVEN_BOUND} [capacity {GIVEN_BOUND}]", "voltage, current", (),
              "a rail fed from outside the board, named by the supply; capacity is the most current it can "
              "deliver, and without it the supply-current check is UNKNOWN"),
    ),
    optional=(
        Field("regulator", "<name> part <registry regulator id> from <rail> [top <resistor> bottom <resistor>]",
              "", ("reg.",),
              "a linear regulator fed from a rail; its name is its output rail; an adjustable one names its "
              "feedback resistors, top from the output and bottom to ground"),
        Field("resistor", "<name> part <registry resistor id> value <resistance> [from <rail>]", "resistance",
              ("res.",),
              "a chip resistor whose value is in its part's E24 or E96 series; with from, it runs from that rail "
              "to ground, and otherwise one divider, LED or regulator names it"),
        Field("divider", "<name> from <rail> top <resistor> bottom <resistor>", "", (),
              "two resistors in series from a rail to ground; its output is the node between them"),
        Field("led", "<name> part <registry led id> from <rail> resistor <resistor> [count <n>]", "", ("led.",),
              "a string of count LEDs (one by default) in series with its current-limit resistor, from a rail "
              "to ground"),
        Field("sink", "<name> from <rail>", "", (),
              "a load on a rail; each load case signs the current it draws"),
    ),
    target="<board>.<sink>",
    loads=("current",),
)


def lower_board(component: Component, design: Design, registry: Registry) -> Board:
    """Parse the lines in the module docstring. Rejects (ComponentError): an unknown line,
    a name declared twice, a part of the wrong kind, a value outside the part's series or
    range, an unknown rail or resistor, a resistor placed twice or never, a regulator loop,
    a load field other than current on a sink, and a claim on a quantity the element does
    not have."""
    problems: list[str] = []
    name = component.name
    elements: dict[str, Element] = {}
    for attr in component.attrs:
        say = _reporter(problems, attr.span, f"{name}.{attr.key}")
        reader = _READERS.get(attr.key)
        head = attr.args[0] if attr.args else None
        if reader is None:
            say(f"unknown line; a board takes {', '.join(sorted(GRAMMAR.names))}")
        elif _name(head) is None:
            say("starts with the element's name")
        elif _name(head) in elements:
            say(f"'{_name(head)}' is declared twice")
        else:
            element = reader(f"{name}.{_name(head)}", _name(head), attr.args[1:], design, registry, say)
            if element is not None:
                elements[element.name] = element
    if not any(isinstance(e, Supply) for e in elements.values()) and not problems:
        _reporter(problems, component.span, name)(f"a board needs a supply line: supply {GRAMMAR.required[0].form}")
    place = _connect(name, component.span, elements, problems)
    draws = _draws(name, design, elements, problems)
    elements = {n: Sink(n, e.rail, MappingProxyType(draws.get(n, {}))) if isinstance(e, Sink) else e
                for n, e in elements.items()}
    _check_references(name, design, elements, problems)
    if problems:
        raise ComponentError(tuple(problems))
    return Board(name, MappingProxyType(elements), MappingProxyType(place), component.span,
                 design.ambient, design.environment)


def _connect(board: str, span: Span, elements: Mapping[str, Element], problems: list[str]) -> dict[str, str]:
    """Resistor -> the element placing it, and every problem with the rails and resistors
    the elements name."""
    say = _reporter(problems, span, board)
    rails = {n for n, e in elements.items() if isinstance(e, (Supply, Regulator))}
    place: dict[str, str] = {}

    def rail(element: str, named: str) -> None:
        if named not in rails:
            say(f"{element} draws from '{named}', which is not a supply or regulator of {board}")

    def placed(element: str, resistor: str) -> None:
        if not isinstance(elements.get(resistor), Resistor):
            say(f"{element} names '{resistor}', which is not a resistor of {board}")
        elif resistor in place:
            say(f"{resistor} is placed by both {place[resistor]} and {element}; a resistor is placed once")
        else:
            place[resistor] = element

    for n, e in elements.items():
        match e:
            case Regulator():
                rail(n, e.source)
                if e.top is not None:
                    placed(n, e.top)
                    placed(n, e.bottom)
            case Resistor() if e.rail is not None:
                rail(n, e.rail)
                placed(n, n)
            case Divider():
                rail(n, e.rail)
                placed(n, e.top)
                placed(n, e.bottom)
            case Led():
                rail(n, e.rail)
                placed(n, e.resistor)
            case Sink():
                rail(n, e.rail)
    for n, e in elements.items():
        if isinstance(e, Resistor) and n not in place:
            say(f"{n} is not placed: give it from <rail>, or name it in a divider, an LED or a regulator")
    for n, e in elements.items():
        seen, at = [n], e
        while isinstance(at, Regulator) and at.source in rails:
            if at.source in seen:
                say(f"the regulators {' -> '.join(seen)} feed each other in a loop")
                break
            seen.append(at.source)
            at = elements[at.source]
    return place


def _draws(board: str, design: Design, elements: Mapping[str, Element],
           problems: list[str]) -> dict[str, dict[str, Input | ParamRef]]:
    found: dict[str, dict[str, Input | ParamRef]] = {}
    for case in design.loads.values():
        say = _reporter(problems, case.span, f"load {case.name}")
        for entry in case.entries:
            if entry.target[0] != board:
                continue
            target = ".".join(entry.target)
            value = entry.value
            dim = value.range.dim if isinstance(value, Input) else design.params[value.name].range.dim
            if len(entry.target) != 2 or not isinstance(elements.get(entry.target[1]), Sink):
                say(f"{target}: a board load acts on one of its sinks")
            elif entry.field not in GRAMMAR.loads:
                say(f"{target}: a sink's load field is {', '.join(GRAMMAR.loads)}, not {entry.field}")
            elif dim != CURRENT:
                say(f"{target}: current needs a current range")
            elif case.name in found.get(entry.target[1], {}):
                say(f"{target}: the sink's current is given twice")
            else:
                found.setdefault(entry.target[1], {})[case.name] = value
    return found


def _check_references(board: str, design: Design, elements: Mapping[str, Element], problems: list[str]) -> None:
    for claim in design.claims:
        if claim.qoi.path[0] != board:
            continue
        say = _reporter(problems, claim.span, f"claim {claim.name}")
        kinds = QOI_ELEMENT.get(claim.qoi.name)
        element = elements.get(claim.qoi.path[1]) if len(claim.qoi.path) == 2 else None
        if kinds is None:
            say(f"unknown board quantity '{claim.qoi.name}'; known: {', '.join(sorted(QOI_ELEMENT))}")
        elif element is None or not isinstance(element, kinds):
            what = " or ".join(k.__name__.lower() for k in kinds)
            say(f"{claim.qoi.name} is a quantity of a {what}, as in {board}.<{what.split()[0]}>.{claim.qoi.name}")
        elif claim.bound.dim != QOI_BOUND_DIMS[claim.qoi.name]:
            say(f"{claim.qoi.name} is bounded by {QOI_DIMS[claim.qoi.name]}")
    for claim in design.probability_claims:
        path = claim.event.qoi.path if isinstance(claim.event, Exceeds) else claim.event.subject
        if path[0] == board:
            _reporter(problems, claim.span, f"claim {claim.name}")("v0 states no probability claim on a board")
    for tests in design.tests.values():
        if tests.subject[0] == board:
            _reporter(problems, tests.span, f"tests {tests.name}")("v0 reads no tests records on a board")
    for waiver in design.waivers:
        if waiver.subject[0] == board and len(waiver.subject) > 1 and waiver.subject[1] not in elements:
            _reporter(problems, waiver.span, "waiver")(f"'{waiver.subject[1]}' is not an element of {board}")

