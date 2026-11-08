"""Domain: electronics at DC, worst case over every part's spreads. Trusted; footprint
premises "model:dc.*@<hash>". docs/electronics_dc.md is the specification.

Failure modes. Each is checked on one element as one R4 goal, `quantity - limit <= 0`
(for a lower bound, `limit - quantity <= 0`); network.py writes each quantity:

    dc.rail_voltage         claim only: a rail's voltage, from above or below
    dc.divider_output       claim only: a divider's output, from above or below
    dc.led_current          claim only: an LED string's current, from above or below
    dc.resistor_power       P <= u P70 min(1, (T_upper - Ta) / (T_upper - T_rated))   IEC 60115-1 derating
    dc.resistor_voltage     the voltage across a resistor <= its limiting element voltage   IEC 60115-1
    dc.led_rating           I <= IF_max min(1, (T_upper - Ta) / (T_upper - T_knee))   the LED datasheet
    dc.regulator_headroom   Vout + V_dropout,max <= Vin                               the regulator datasheet
    dc.regulator_input      Vin <= Vin,max; for the floating style Vin - Vout <= its differential limit
    dc.regulator_current    I_out <= I_out,max
    dc.regulator_min_load   I_out >= I_out,min: a floating regulator leaves regulation below it
    dc.regulator_thermal    Ta + theta_JA P <= Tj,max, or a claimed junction temperature
    dc.supply_current       the current drawn from a supply <= its signed capacity

u is 1 for coverage and a claimed fraction for a power_utilisation claim.

Coverage demands every rating a part holds, whatever the claims ask: RATINGS maps each
rating property to the mode that checks it, and one coverage rule per mode applies to
every element whose registry part holds one of its properties. Every supply owes
dc.supply_current.

A limit past which the design has failed is a mode of its own, not a validity row
(docs/design.md decision 12): a regulator in dropout or past its current fails its own
mode, so the design fails whatever else holds. The rows are the limits past which the
data say nothing while the part still works: an ambient colder than a part's data, and an
LED current outside its fitted range. The LED rating's own check leaves out its LED's
upper current term. Past the fit's top the true current is above the top too, because the
forward voltage only rises with current, and the fit's top is the maximum current, so the
failure stands.

A quantity that reads a sink's current is stated once per load case; any other is stated
once. A missing ambient, sink current or supply capacity is a Gap needing NeedsInputBound.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Mapping

from ... import mechanics
from ...ir import Design, Input, Rel
from ...kernel import Const, Expr, Interval
from ...kernel.rules.r4_enclosure import AllNonpositive
from ...mechanics import add, mul, sub
from ...registry import Registry
from ...units import DIMENSIONLESS, Quantity, readable_text
from ..base import (
    NO_PORTS,
    CoverageRule,
    Criterion,
    DomainSpec,
    Elaborated,
    EnergyDomain,
    FailureMode,
    Feature,
    FeatureKind,
    Gap,
    GapNeed,
    ModelSpec,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
    Requirement,
    StatementBuilder,
    ValidityRow,
    validity_obligation,
)
from .board import FAMILIES, GRAMMAR, Board, Element, Led, Regulator, Resistor, Supply, lower_board
from .network import PARTS, Missing, MissingLoad, Net

# --- Modes ------------------------------------------------------------------------------

RAIL_VOLTAGE = FailureMode("dc.rail_voltage")
DIVIDER_OUTPUT = FailureMode("dc.divider_output")
LED_CURRENT = FailureMode("dc.led_current")
RESISTOR_POWER = FailureMode("dc.resistor_power")
RESISTOR_VOLTAGE = FailureMode("dc.resistor_voltage")
LED_RATING = FailureMode("dc.led_rating")
REGULATOR_HEADROOM = FailureMode("dc.regulator_headroom")
REGULATOR_INPUT = FailureMode("dc.regulator_input")
REGULATOR_CURRENT = FailureMode("dc.regulator_current")
REGULATOR_MIN_LOAD = FailureMode("dc.regulator_min_load")
REGULATOR_THERMAL = FailureMode("dc.regulator_thermal")
SUPPLY_CURRENT = FailureMode("dc.supply_current")

QOIS: Mapping[str, FailureMode] = {
    "voltage": RAIL_VOLTAGE,
    "output": DIVIDER_OUTPUT,
    "current": LED_CURRENT,
    "power_utilisation": RESISTOR_POWER,
    "junction_temperature": REGULATOR_THERMAL,
}

RATINGS: Mapping[FailureMode, tuple[str, tuple[str, ...]]] = {
    RESISTOR_POWER: ("resistor", ("p70", "t_upper")),
    RESISTOR_VOLTAGE: ("resistor", ("lev",)),
    LED_RATING: ("led", ("if_max", "t_upper")),
    REGULATOR_HEADROOM: ("regulator", ("vdo_max",)),
    REGULATOR_INPUT: ("regulator", ("vin_max", "vdiff_max")),
    REGULATOR_CURRENT: ("regulator", ("iout_max",)),
    REGULATOR_MIN_LOAD: ("regulator", ("iout_min",)),
    REGULATOR_THERMAL: ("regulator", ("tj_max",)),
}
"""Mode -> (the kind of part, the rating properties it checks). A part of that kind
holding any of them owes the mode."""

PROPERTIES: Mapping[str, Mapping[str, frozenset[str]]] = {
    "resistor": {
        "rating": frozenset({"p70", "t_upper", "lev"}),
        "validity": frozenset({"t_lower"}),
        "spread": frozenset({"tolerance", "tcr"}),
        "parameter": frozenset({"t_ref", "t_rated", "r_min", "r_max", "steps"}),
    },
    "led": {
        "rating": frozenset({"if_max", "t_upper"}),
        "validity": frozenset({"t_lower", "i_min"}),
        "spread": frozenset({"v0_min", "v0_max", "rd_min", "rd_max", "tc_min", "tc_max"}),
        "parameter": frozenset({"t_ref", "t_knee", "theta"}),
    },
    "regulator": {
        "rating": frozenset({"vdo_max", "vin_max", "vdiff_max", "iout_max", "iout_min", "tj_max"}),
        "validity": frozenset({"tj_min"}),
        "spread": frozenset({"vout_min", "vout_max", "vref_min", "vref_max", "iadj_max", "ifb_max", "iq_max"}),
        "parameter": frozenset({"theta_ja"}),
    },
}
"""Every property a part may hold, by what the model does with it: a rating some mode
checks (RATINGS), a validity row's limit, a spread's end, or a formula's parameter.
tests/test_electronics.py holds every shipped part to this table, so no rating a part
states goes unchecked."""

# --- Model premises -----------------------------------------------------------------------

TRUSTED = ("board", "network", "domain")
HASHED = (*(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py") for name in TRUSTED),
          *mechanics.SOURCES)
"""The files the premise hash reads: the trusted modules, then the mechanics layer."""


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in HASHED:
        with open(path, encoding="utf-8") as f:
            digest.update(f.read().encode("utf-8"))
    return digest.hexdigest()[:16]


SOURCE_HASH = _source_hash()
OWNER = "petra-maintainers"
STANDARDS = "IEC 60115-1; IEC 60115-8; the parts' datasheets"

COLD = ValidityRow(
    "dc.cold",
    "the ambient is at or above the lowest temperature of every part the statement reads: a resistor's lower "
    "category temperature, an LED's lowest operating temperature, a regulator's lowest junction temperature",
    "IEC 60115-8 climatic categories; the LED and regulator datasheets",
)
LED_RANGE = ValidityRow(
    "dc.led_range",
    "every LED the statement reads carries a current inside the range its forward-voltage fit holds over, from "
    "its lowest fitted current to its maximum current",
    "the LED datasheet's forward-voltage curves",
)

FORM = ("DC worst case over each part's spreads: chip resistors by tolerance and temperature coefficient over the "
        "temperatures their ambient and self-heating allow, regulator outputs inside their stated ranges, LED "
        "forward voltage as a threshold plus a slope resistance with a temperature coefficient; currents summed by "
        "Kirchhoff's current law")
WORDS = ("steady state; each part's temperature uniform; every regulator in regulation, which its own modes check; "
         "the board's copper and contacts carry no voltage drop")
UNCHECKED = (
    "a resistor's drift over its life (load-life and damp-heat stability), which the registry does not hold",
    "a regulator's line and load transients and its output noise",
)

SOURCE = ModelSpec(
    "dc.source", "signed supply voltages and signed sink currents, summed by Kirchhoff's current law",
    "steady state; every sink draws the current its load case signs. Unbounded: the statement reads no part, so no "
    "part's data have a limit to state",
    OWNER, "Kirchhoff's current law", SOURCE_HASH)
NETWORK = ModelSpec("dc.network", FORM, WORDS, OWNER, STANDARDS, SOURCE_HASH, (COLD,), UNCHECKED)
NETWORK_LED = ModelSpec("dc.network_led", FORM, WORDS, OWNER, STANDARDS, SOURCE_HASH, (COLD, LED_RANGE), UNCHECKED)
MODEL_SPECS = (SOURCE, NETWORK, NETWORK_LED)


def model_of(net: Net) -> ModelSpec:
    """The model a statement rests on, by what it reads."""
    if net.leds:
        return NETWORK_LED
    return NETWORK if net.parts else SOURCE


def row_terms(row: ValidityRow, net: Net, req: Requirement) -> tuple[Expr, ...]:
    """The row's terms over the parts `net` read. An LED's rating check leaves out its own
    upper current term (module docstring)."""
    if row is COLD:
        return tuple(net.cold.values())
    skip = (req.subject[1], "high") if req.mode == LED_RATING else None
    return tuple(e for key, e in net.led_range.items() if key != skip)


# --- Checks -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    """One mode on one element. `quantity` is what the mode bounds and `limit` the rating
    coverage checks it against, from above when `upper` and from below otherwise; None
    for a claim-only mode. With `scaled`, a criterion's bound is a fraction of the limit;
    otherwise it bounds the quantity itself. `both` lets a claim bound the quantity from
    below as well as above. `what` names the quantity in a report."""

    quantity: Callable[[Net, Element], Expr]
    limit: Callable[[Net, Element], Expr] | None
    upper: bool
    scaled: bool
    both: bool
    what: str


def _capacity(net: Net, s: Supply) -> Expr:
    if s.capacity is None:
        raise Missing(NeedsInputBound((net.board.name, s.name), "capacity", "A"))
    if isinstance(s.capacity, Input):
        return net.sb.input(s.capacity)
    return net.sb.value(s.capacity, f"{net.board.name}.{s.name}.capacity")


def _input(net: Net, g: Regulator) -> Expr:
    if g.style == "floating":
        return sub(net.volts(g.source), net.vout(g))
    return net.volts(g.source)


def _input_limit(net: Net, g: Regulator) -> Expr:
    return net.prop(g, "vdiff_max" if g.style == "floating" else "vin_max")


CHECKS: Mapping[FailureMode, Check] = {
    RAIL_VOLTAGE: Check(lambda net, e: net.volts(e.name), None, True, False, True, "voltage"),
    DIVIDER_OUTPUT: Check(lambda net, d: net.divider_output(d), None, True, False, True, "output voltage"),
    LED_CURRENT: Check(lambda net, d: net.led_current(d), None, True, False, True, "current"),
    RESISTOR_POWER: Check(lambda net, r: net.stress(r.name)[1], lambda net, r: net.resistor_rating(r.name),
                          True, True, False, "dissipation against its derated power rating"),
    RESISTOR_VOLTAGE: Check(lambda net, r: net.stress(r.name)[0], lambda net, r: net.prop(r, "lev"),
                            True, False, False, "voltage against its limiting element voltage"),
    LED_RATING: Check(lambda net, d: net.led_current(d), lambda net, d: net.led_rating(d),
                      True, False, False, "current against its derated maximum current"),
    REGULATOR_HEADROOM: Check(lambda net, g: add(net.vout(g), net.prop(g, "vdo_max")),
                              lambda net, g: net.volts(g.source), True, False, False,
                              "output plus its dropout against its input"),
    REGULATOR_INPUT: Check(_input, _input_limit, True, False, False, "input against its maximum input or differential"),
    REGULATOR_CURRENT: Check(lambda net, g: net.output_current(g), lambda net, g: net.prop(g, "iout_max"),
                             True, False, False, "output current against its rating"),
    REGULATOR_MIN_LOAD: Check(lambda net, g: net.output_current(g), lambda net, g: net.prop(g, "iout_min"),
                              False, False, False, "output current against its minimum load"),
    REGULATOR_THERMAL: Check(lambda net, g: net.junction(g), lambda net, g: net.prop(g, "tj_max"),
                             True, False, False, "junction temperature"),
    SUPPLY_CURRENT: Check(lambda net, s: net.drawn(s.name), _capacity, True, False, False,
                          "current drawn against its capacity"),
}


def goal_term(check: Check, net: Net, element: Element, criterion: Criterion | None) -> Expr:
    """The check as one expression that is <= 0 exactly where it holds."""
    quantity = check.quantity(net, element)
    if criterion is None:
        limit = check.limit(net, element)
        return sub(quantity, limit) if check.upper else sub(limit, quantity)
    if criterion.rel is Rel.LE:
        bound = Const(criterion.bound.value.lo)
        return sub(quantity, mul(bound, check.limit(net, element)) if check.scaled else bound)
    return sub(Const(criterion.bound.value.hi), quantity)


def _describe(req: Requirement, check: Check, case: str | None) -> str:
    criterion = req.criterion
    if criterion is None:
        bound = "within its rating"
    elif check.scaled:
        bound = f"at most {float(criterion.bound.value.lo):g} of its rating"
    else:
        side = "at most" if criterion.rel is Rel.LE else "at least"
        bound = f"{side} {readable_text(criterion.bound)}"
    under = f" under {case}" if case is not None else ""
    return f"{'.'.join(req.subject)}: {check.what} {bound}{under}"


# --- Builders -----------------------------------------------------------------------------


def _cases(req: Requirement, board: Board, design: Design) -> tuple[str, ...]:
    """The load cases a load-dependent requirement is checked under: those it names, else
    every case that loads the board."""
    if req.under:
        return tuple(req.under)
    return tuple(case.name for case in design.loads.values() if any(e.target[0] == board.name for e in case.entries))


def builder(mode: FailureMode) -> Callable[[Requirement, Board, Design, Registry], tuple[Elaborated, ...]]:
    check = CHECKS[mode]

    def build(req: Requirement, board: Board, design: Design, registry: Registry) -> tuple[Elaborated, ...]:
        element = board.elements[req.subject[1]]
        criterion = req.criterion
        if isinstance(criterion, Criterion) and criterion.rel is Rel.GE and not check.both:
            qoi = req.qoi.name if req.qoi is not None else mode.id
            return (Gap(req, (NoRuleForQuantity(qoi, f"a {type(element).__name__.lower()}'s {qoi} is bounded from "
                                                     "above only"),)),)

        def make(case: str | None) -> tuple[StatementBuilder, Net, Expr]:
            sb = StatementBuilder(design, registry)
            net = Net(sb, board, design, registry, case)
            return sb, net, goal_term(check, net, element, criterion)

        needs: list[GapNeed] = []
        made: list[tuple[str | None, tuple[StatementBuilder, Net, Expr]]] = []
        try:
            made.append((None, make(None)))
        except MissingLoad as first:
            cases = _cases(req, board, design)
            if not cases:
                needs.append(first.need)
            for case in cases:
                try:
                    made.append((case, make(case)))
                except Missing as m:
                    needs.append(m.need)
        except Missing as m:
            needs.append(m.need)
        if needs:
            return (Gap(req, tuple(dict.fromkeys(needs))),)
        out: list[Elaborated] = []
        for case, (sb, net, expr) in made:
            model = model_of(net)
            validity = []
            for row in model.rows:
                row_sb, row_net, _ = make(case)
                validity.append(validity_obligation(req, model, row, row_sb.finish(AllNonpositive(row_terms(row, row_net, req))),
                                                    f"{'.'.join(req.subject)}: {row.text}" + (f" under {case}" if case else "")))
            out.append(Obligation(req, sb.finish(AllNonpositive((expr,))), model, _describe(req, check, case), tuple(validity)))
        return tuple(out)

    return build


BUILDERS = {mode: builder(mode) for mode in CHECKS}

# --- Coverage ------------------------------------------------------------------------------

PART = FeatureKind("dc.part")
SOURCE_FEATURE = FeatureKind("dc.supply")


def features(board: Board, design: Design, registry: Registry) -> tuple[Feature, ...]:
    """One feature per supply, and one per part with its registry part as its material."""
    out = []
    for e in board.elements.values():
        if isinstance(e, Supply):
            out.append(Feature((board.name, e.name), SOURCE_FEATURE, (), frozenset({EnergyDomain.ELECTRICAL}),
                               design.environment))
        elif type(e) in PARTS:
            out.append(Feature((board.name, e.name), PART, (e.part,),
                               frozenset({EnergyDomain.ELECTRICAL, EnergyDomain.THERMAL}), design.environment))
    return tuple(out)


def _holds_rating(mode: FailureMode) -> Callable[[Feature, Registry], bool]:
    line, props = RATINGS[mode]

    def when(feature: Feature, registry: Registry) -> bool:
        if feature.kind != PART:
            return False
        part = registry.materials[feature.materials[0]]
        return FAMILIES[part.family] == line and any(p in part.props for p in props)
    return when


def _default(mode: FailureMode, feature: Feature) -> Criterion | None:
    """A resistor's power is a utilisation, at most 1 of its derated rating; every other
    mode reads its limit from the registry or the design (None)."""
    if mode == RESISTOR_POWER:
        one = Fraction(1)
        return Criterion(Rel.LE, Quantity(Interval(one, one), DIMENSIONLESS))
    return None


COVERAGE: tuple[CoverageRule, ...] = (
    *(CoverageRule(mode.id, _holds_rating(mode), (mode,), _default,
                   f"every {line} rated by {' or '.join(props)} owes {mode.id}") for mode, (line, props) in RATINGS.items()),
    CoverageRule("dc.supply", lambda f, registry: f.kind == SOURCE_FEATURE, (SUPPLY_CURRENT,), _default,
                 "every supply must deliver what the board draws from it"),
)


def absent(board: Board, design: Design) -> Mapping[FailureMode, str]:
    """Why a rated mode cannot arise on a board that does not owe it."""
    kinds = {type(e) for e in board.elements.values()}
    out: dict[FailureMode, str] = {}
    if Resistor not in kinds:
        out.update({m: "the board has no resistor" for m in (RESISTOR_POWER, RESISTOR_VOLTAGE)})
    if Led not in kinds:
        out[LED_RATING] = "the board has no LED"
    regulators = [e for e in board.elements.values() if isinstance(e, Regulator)]
    if not regulators:
        out.update({m: "the board has no regulator" for m in (REGULATOR_HEADROOM, REGULATOR_INPUT, REGULATOR_CURRENT,
                                                              REGULATOR_MIN_LOAD, REGULATOR_THERMAL)})
    elif all(g.style != "floating" for g in regulators):
        out[REGULATOR_MIN_LOAD] = "no regulator on the board is of the floating style, the one whose data state a minimum load"
    return out


DOMAIN = DomainSpec(
    name="electronics",
    kinds={"board": lower_board},
    builders=BUILDERS,
    unmodelled=frozenset(),
    qois=QOIS,
    probability={},
    coverage=COVERAGE,
    models={mode: NETWORK_LED if mode in (LED_CURRENT, LED_RATING) else NETWORK for mode in CHECKS},
    features=features,
    ports=lambda board, registry: NO_PORTS,
    grammars={"board": GRAMMAR},
    absent=absent,
)
