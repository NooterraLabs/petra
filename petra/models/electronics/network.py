"""DC worst-case physics of a board. Trusted; its source is part of the model premise's hash.

`Net` writes, inside one StatementBuilder, the kernel expressions for a board's rail
voltages, currents and part quantities. It records the parts a statement reads, so the
builder states the model's validity rows over the same parts (domain.py).

Spreads. Every part instance has its own variables for where it sits inside its spreads,
each a design hypothesis "dsg:<design>.<board>.<element>.<what>" over [-1, 1] for a
symmetric spread or [0, 1] for one read from its low end to its high end. Two parts of
one type therefore vary independently, and the registry gives only the spread's ends. A
refutation's point names each variable's value, so a FAIL is a worst-case corner.

Resistor (IEC 60115-1 and IEC 60115-8):
    R = Rn (1 + tol u) (1 + TCR w E)                        u, w in [-1, 1]
    Rn = m 10^k, m the IEC 60063 mantissa (a registry constant), 10^k a design value
    E = max(T_ref - Ta, T_hot - T_ref)                     the part's farthest temperature from T_ref
    T_hot = min(Ta + theta P_bound, T_upper)               an upper bound on the part's temperature
    theta = (T_upper - T_rated) / P70                      the derating line: rated power heats the part
                                                           from the rated ambient to the upper category
    R_floor, R_ceil = Rn (1 -+ tol)(1 -+ TCR max(T_ref - Ta, T_upper - T_ref))
P_bound bounds the dissipation from the resistances' floors and ceilings, so it does not
depend on the self-heating it bounds:
    to ground, or an LED's resistor    V^2 / R_floor            V the rail it hangs from
    in a divider                       V^2 R_ceil / (Rt_floor + Rb_floor)^2
    across a regulator's reference     Vref_max^2 / R_floor
    the other feedback resistor        (Vref_max / R_ref,floor + I_pin,max)^2 R_ceil
T_hot stops at the upper category temperature because a resistor hotter than that fails
dc.resistor_power, which coverage demands of every resistor; the design then fails
whatever this bound says. The dissipation that check reads is exact, so T_hot only widens
the temperature band the TCR acts over.

Derated power rating (IEC 60115-1 derating curve): P70 min(1, (T_upper - Ta) / (T_upper - T_rated)).

Regulator outputs, with z, g in [0, 1] (a grounded style's feedback current in [-1, 1]):
    fixed      Vout = Vout_min + (Vout_max - Vout_min) z
    floating   Vout = Vref (1 + Rb / Rt) + I_adj Rb            Vref across Rt, I_adj = I_adj,max g
    grounded   Vout = Vref (1 + Rt / Rb) + I_fb Rt             Vref across Rb, I_fb = I_fb,max g
    Vref = Vref_min + (Vref_max - Vref_min) z
Kirchhoff's current law on the regulator, with I_load the current drawn from its rail:
    fixed      I_out = I_load                 I_in = I_out + I_gnd,  I_gnd = I_q,max g
    floating   I_out = I_load + Vref / Rt     I_in = I_out + I_adj
    grounded   I_out = I_load + Vref / Rb + I_fb     I_in = I_load + Vref / Rb + I_gnd
Dissipation, input power less the power out of each other pin:
    fixed      P = (Vin - Vout) I_out + Vin I_gnd
    floating   P = (Vin - Vout) I_out + (Vin - Vout + Vref) I_adj     (the adjust pin sits at Vout - Vref)
    grounded   P = (Vin - Vout) I_out + Vin I_gnd - (Vin - Vref) I_fb
    Tj = Ta + theta_JA P

LED string of n in series with resistor R, forward voltage fitted as V0 + Rd I at T_ref:
    I = (V - n (V0 + TC (Tj - T_ref))) / (R + n Rd)
    V0, Rd, TC each between their registry ends; Tj = Ta + h theta IF_max (V0_max + Rd_max IF_max), h in [0, 1]
Derated current rating: IF_max min(1, (T_upper - Ta) / (T_upper - T_knee)).

Rail current: the sum of what each element on the rail draws: a sink its signed current,
a resistor to ground V / R, a divider V / (Rt + Rb), an LED string its I, a regulator its
I_in.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from ...ir import Design, Fixed, Input, ParamRef
from ...kernel import Const, Expr, Interval, Max, Min, Sym
from ...mechanics import add, div, mul, sq, sub
from ...registry import Registry
from ...units import DIMENSIONLESS, RESISTANCE, Quantity
from ..base import GapNeed, NeedsInputBound, StatementBuilder
from .board import Board, Divider, Element, Led, Regulator, Resistor, Sink, Supply

ONE = Const(Fraction(1))
ZERO = Const(Fraction(0))
SYMMETRIC = Interval(Fraction(-1), Fraction(1))
FROM_LOW = Interval(Fraction(0), Fraction(1))


class Missing(Exception):
    """An input the statement needs is not given. Internal: a builder catches it and
    returns a Gap naming `need`, so no exception leaves a builder."""

    def __init__(self, need: GapNeed) -> None:
        super().__init__(need)
        self.need = need


class MissingLoad(Missing):
    """The statement reads a sink's current, and no load case is chosen or the case does
    not give it."""


def between(lo: Expr, hi: Expr, z: Expr) -> Expr:
    return add(lo, mul(sub(hi, lo), z))


class Net:
    """One statement's view of a board under one load case (None: before a case is
    chosen). Memoised per element, so each quantity is one expression and each spread
    one hypothesis however often the statement reads it."""

    def __init__(self, sb: StatementBuilder, board: Board, design: Design, registry: Registry, case: str | None) -> None:
        self.sb, self.board, self.design, self.registry, self.case = sb, board, design, registry, case
        self.cold: dict[str, Expr] = {}
        """Element -> its lowest data temperature less the ambient (<= 0 where its data hold)."""
        self.led_range: dict[tuple[str, str], Expr] = {}
        """(LED, "low" | "high") -> how far its current is outside its fitted range (<= 0 inside)."""
        self._memo: dict[tuple[str, str], Expr] = {}

    # --- inputs and spreads ---------------------------------------------------------------

    def ambient(self) -> Expr:
        a = self.board.ambient
        if isinstance(a, Input):
            return self.sb.input(a)
        if isinstance(a, ParamRef):
            return self.sb.value(a, "ambient")
        if self.board.environment is not None:
            return self.sb.registry(self.board.environment, "ambient")
        raise Missing(NeedsInputBound((self.design.name,), "ambient", "degC"))

    def spread(self, element: str, what: str, span: Interval) -> Sym:
        return self.sb.value(Fixed(Quantity(span, DIMENSIONLESS)), f"{self.board.name}.{element}.{what}")

    def prop(self, element: Element, name: str) -> Expr:
        """A registry property of the element's part. Reading any of a part's data puts the
        part under the cold row, since its data hold only from its lowest temperature up."""
        self._read(element)
        return self.sb.registry(element.part, name)

    def _once(self, element: str, what: str, build) -> Expr:
        key = (element, what)
        if key not in self._memo:
            self._memo[key] = build()
        return self._memo[key]

    def _read(self, element: Element) -> None:
        """Record that the statement reads `element`'s data, which hold from its LOWEST
        temperature property up."""
        if element.name not in self.cold:
            self.cold[element.name] = sub(self.sb.registry(element.part, LOWEST[type(element)]), self.ambient())

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.cold)

    @property
    def leds(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(led for led, _ in self.led_range))

    # --- rails ------------------------------------------------------------------------------

    def volts(self, rail: str) -> Expr:
        e = self.board.elements[rail]
        if isinstance(e, Supply):
            if isinstance(e.voltage, Input):
                return self.sb.input(e.voltage)
            return self.sb.value(e.voltage, f"{self.board.name}.{e.name}.voltage")
        return self.vout(e)

    def drawn(self, rail: str) -> Expr:
        """The current every element on `rail` draws from it."""
        terms = tuple(self.draw(e) for e in self.board.on(rail))
        return add(*terms) if terms else ZERO

    def draw(self, e: Element) -> Expr:
        match e:
            case Sink():
                return self.sink(e)
            case Resistor():
                return div(self.volts(e.rail), self.resistance(e.name))
            case Divider():
                return div(self.volts(e.rail), add(self.resistance(e.top), self.resistance(e.bottom)))
            case Led():
                return self.led_current(e)
            case Regulator():
                return self.input_current(e)
        raise TypeError(f"{type(e).__name__} draws no current")

    def sink(self, e: Sink) -> Expr:
        drawn = e.draws.get(self.case) if self.case is not None else None
        if drawn is None:
            raise MissingLoad(NeedsInputBound((self.board.name, e.name), "current", "A"))
        return self.sb.input(drawn) if isinstance(drawn, Input) else self.sb.value(drawn, self.case)

    # --- resistors --------------------------------------------------------------------------

    def resistance(self, name: str) -> Expr:
        r = self.board.elements[name]
        return self._once(name, "R", lambda: self._resistance(r))

    def nominal(self, name: str) -> Expr:
        r = self.board.elements[name]

        def build() -> Expr:
            self._read(r)
            decade = Fixed(Quantity(Interval(r.decade, r.decade), RESISTANCE))
            return mul(self.sb.constant(r.mantissa), self.sb.value(decade, f"{self.board.name}.{name}.decade"))
        return self._once(name, "nominal", build)

    def extreme(self, name: str, sign: int) -> Expr:
        """R_floor (sign -1) or R_ceil (sign 1): the resistance at the end of its tolerance
        and its temperature coefficient over every temperature from the ambient to the upper
        category temperature."""
        r = self.board.elements[name]
        tol, tcr, t_ref = (self.prop(r, p) for p in ("tolerance", "tcr", "t_ref"))
        ta = self.ambient()
        band = Max((sub(t_ref, ta), sub(self.prop(r, "t_upper"), t_ref)))
        step = add if sign > 0 else sub
        return mul(self.nominal(name), step(ONE, tol), step(ONE, mul(tcr, band)))

    def heat_bound(self, name: str) -> Expr:
        """P_bound of the module docstring, by what places the resistor."""
        placer = self.board.elements[self.board.place[name]]
        floor = self.extreme(name, -1)
        match placer:
            case Resistor() | Led():
                return div(sq(self.volts(placer.rail)), floor)
            case Divider():
                both = add(self.extreme(placer.top, -1), self.extreme(placer.bottom, -1))
                return div(mul(sq(self.volts(placer.rail)), self.extreme(name, 1)), sq(both))
            case Regulator():
                ref = self.reference_resistor(placer)
                vref = self.prop(placer, "vref_max")
                if name == ref:
                    return div(sq(vref), floor)
                pin = self.prop(placer, "iadj_max" if placer.style == "floating" else "ifb_max")
                return mul(sq(add(div(vref, self.extreme(ref, -1)), pin)), self.extreme(name, 1))
        raise TypeError(f"{name} is placed by a {type(placer).__name__}")

    def _resistance(self, r: Resistor) -> Expr:
        ta = self.ambient()
        tol, tcr, t_ref, t_upper = (self.prop(r, p) for p in ("tolerance", "tcr", "t_ref", "t_upper"))
        theta = div(sub(t_upper, self.prop(r, "t_rated")), self.prop(r, "p70"))
        hot = Min((add(ta, mul(theta, self.heat_bound(r.name))), t_upper))
        reach = Max((sub(t_ref, ta), sub(hot, t_ref)))
        u = self.spread(r.name, "tolerance", SYMMETRIC)
        w = self.spread(r.name, "tcr", SYMMETRIC)
        return mul(self.nominal(r.name), add(ONE, mul(tol, u)), add(ONE, mul(tcr, w, reach)))

    @staticmethod
    def reference_resistor(g: Regulator) -> str:
        """The feedback resistor the reference voltage sits across."""
        return g.top if g.style == "floating" else g.bottom

    def stress(self, name: str) -> tuple[Expr, Expr]:
        """(voltage across the resistor, power it dissipates), by what places it."""
        r = self.board.elements[name]
        placer = self.board.elements[self.board.place[name]]
        R = self.resistance(name)
        match placer:
            case Resistor():
                v = self.volts(r.rail)
                return v, div(sq(v), R)
            case Divider():
                rail = self.volts(placer.rail)
                other = self.resistance(placer.bottom if name == placer.top else placer.top)
                v = div(rail, add(ONE, div(other, R)))
                return v, div(sq(v), R)
            case Led():
                i = self.led_current(placer)
                return mul(i, R), mul(sq(i), R)
            case Regulator():
                vref = self.vref(placer)
                across_ref = self.reference_resistor(placer)
                if name == across_ref:
                    return vref, div(sq(vref), R)
                i = add(div(vref, self.resistance(across_ref)), self.bias(placer))
                return mul(i, R), mul(sq(i), R)
        raise TypeError(f"{name} is placed by a {type(placer).__name__}")

    def resistor_rating(self, name: str) -> Expr:
        r = self.board.elements[name]
        t_upper = self.prop(r, "t_upper")
        slope = div(sub(t_upper, self.ambient()), sub(t_upper, self.prop(r, "t_rated")))
        return mul(self.prop(r, "p70"), Min((ONE, slope)))

    def divider_output(self, d: Divider) -> Expr:
        return div(self.volts(d.rail), add(ONE, div(self.resistance(d.top), self.resistance(d.bottom))))

    # --- regulators -------------------------------------------------------------------------

    def vref(self, g: Regulator) -> Expr:
        return self._once(g.name, "vref", lambda: between(self.prop(g, "vref_min"), self.prop(g, "vref_max"),
                                                           self.spread(g.name, "vref", FROM_LOW)))

    def bias(self, g: Regulator) -> Expr:
        """The adjust-pin current out of a floating regulator, or the feedback-pin current
        into a grounded one."""
        if g.style == "floating":
            return mul(self.prop(g, "iadj_max"), self.spread(g.name, "iadj", FROM_LOW))
        return mul(self.prop(g, "ifb_max"), self.spread(g.name, "ifb", SYMMETRIC))

    def ground(self, g: Regulator) -> Expr:
        return mul(self.prop(g, "iq_max"), self.spread(g.name, "iq", FROM_LOW))

    def vout(self, g: Regulator) -> Expr:
        return self._once(g.name, "vout", lambda: self._vout(g))

    def _vout(self, g: Regulator) -> Expr:
        self._read(g)
        if g.style == "fixed":
            return between(self.prop(g, "vout_min"), self.prop(g, "vout_max"), self.spread(g.name, "vout", FROM_LOW))
        vref, top, bottom = self.vref(g), self.resistance(g.top), self.resistance(g.bottom)
        if g.style == "floating":
            return add(mul(vref, add(ONE, div(bottom, top))), mul(self.bias(g), bottom))
        return add(mul(vref, add(ONE, div(top, bottom))), mul(self.bias(g), top))

    def output_current(self, g: Regulator) -> Expr:
        load = self.drawn(g.name)
        self.vout(g)
        if g.style == "fixed":
            return load
        if g.style == "floating":
            return add(load, div(self.vref(g), self.resistance(g.top)))
        return add(load, div(self.vref(g), self.resistance(g.bottom)), self.bias(g))

    def input_current(self, g: Regulator) -> Expr:
        self.vout(g)
        if g.style == "fixed":
            return add(self.output_current(g), self.ground(g))
        if g.style == "floating":
            return add(self.output_current(g), self.bias(g))
        return add(self.drawn(g.name), div(self.vref(g), self.resistance(g.bottom)), self.ground(g))

    def dissipation(self, g: Regulator) -> Expr:
        vin, vout = self.volts(g.source), self.vout(g)
        drop = mul(sub(vin, vout), self.output_current(g))
        if g.style == "fixed":
            return add(drop, mul(vin, self.ground(g)))
        if g.style == "floating":
            return add(drop, mul(add(sub(vin, vout), self.vref(g)), self.bias(g)))
        return sub(add(drop, mul(vin, self.ground(g))), mul(sub(vin, self.vref(g)), self.bias(g)))

    def junction(self, g: Regulator) -> Expr:
        return add(self.ambient(), mul(self.prop(g, "theta_ja"), self.dissipation(g)))

    # --- LEDs -----------------------------------------------------------------------------------

    def led_current(self, led: Led) -> Expr:
        return self._once(led.name, "I", lambda: self._led_current(led))

    def _led_current(self, led: Led) -> Expr:
        self._read(led)
        p = {name: self.prop(led, name) for name in ("v0_min", "v0_max", "rd_min", "rd_max", "tc_min", "tc_max",
                                                      "t_ref", "if_max", "theta", "i_min")}
        v0 = between(p["v0_min"], p["v0_max"], self.spread(led.name, "v0", FROM_LOW))
        rd = between(p["rd_min"], p["rd_max"], self.spread(led.name, "rd", FROM_LOW))
        tc = between(p["tc_min"], p["tc_max"], self.spread(led.name, "tc", FROM_LOW))
        hottest = mul(p["theta"], p["if_max"], add(p["v0_max"], mul(p["rd_max"], p["if_max"])))
        tj = add(self.ambient(), mul(hottest, self.spread(led.name, "heat", FROM_LOW)))
        count = Fixed(Quantity(Interval(Fraction(led.count), Fraction(led.count)), DIMENSIONLESS))
        n = self.sb.value(count, f"{self.board.name}.{led.name}.count")
        vf = add(v0, mul(tc, sub(tj, p["t_ref"])))
        i = div(sub(self.volts(led.rail), mul(n, vf)), add(self.resistance(led.resistor), mul(n, rd)))
        self.led_range[(led.name, "low")] = sub(p["i_min"], i)
        self.led_range[(led.name, "high")] = sub(i, p["if_max"])
        return i

    def led_rating(self, led: Led) -> Expr:
        t_upper = self.prop(led, "t_upper")
        slope = div(sub(t_upper, self.ambient()), sub(t_upper, self.prop(led, "t_knee")))
        return mul(self.prop(led, "if_max"), Min((ONE, slope)))


PARTS: Mapping[type, str] = {Resistor: "resistor", Led: "led", Regulator: "regulator"}
"""The elements that are registry parts."""

LOWEST: Mapping[type, str] = {Resistor: "t_lower", Led: "t_lower", Regulator: "tj_min"}
"""The property holding the lowest temperature a part's data hold at."""
