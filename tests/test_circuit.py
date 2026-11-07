"""Wire circuits: lowering, the four wire obligations, coverage features, and the R4
search, each checked through the elaborator, the solver and kernel.check against margins
worked by hand from the formulas in petra/models/circuit.py and the registry. Owner: C.

Hand values, 2.5 mm2 Cu/PVC (insulation 0.8 mm) clipped direct, h = 5 W/(m2 K):
    R20 = rho20 / A = 1 / 145 ohm/m;  d = 1.78412 mm, D = 3.38412 mm
    T1 = 5 / (2 pi) ln(D / d) = 0.509429;  T4 = 1 / (pi D h) = 18.81195 K m/W
    theta(I, 40 degC) = (40 + a (1 - 20 alpha)) / (1 - a alpha),  a = I^2 R20 (T1 + T4)
        theta(10 A) = 55.1667 degC,  a alpha = 0.052368
        theta(15 A) = 76.6572 degC,  theta(16 A) = 82.4897 degC
    runaway at a alpha = 1: 43.70 A for h = 5; at 62 A, h = 10: a alpha - 1 = 0.033043
    k = sqrt(qc (beta + 20) / rho20 ln((beta + 160) / (beta + 70))) = 114.835 A s^0.5 / mm2
        k^2 S^2 = 82419.04 A2s at 2.5 mm2, 29670.85 A2s at 1.5 mm2
    drop over 18 m at 10 A = 2 L I R20 (1 + alpha 50) = 2.970621 V
"""
import dataclasses
import unittest
from fractions import Fraction
from pathlib import Path

from petra import coverage
from petra.kernel import (
    Add,
    Const,
    Evidence,
    Interval,
    Leaf,
    Mul,
    Neg,
    RangeHyp,
    Refutation,
    Rejection,
    Split,
    Statement,
    Sym,
    Theorem,
    check,
    enclose,
)
from petra.kernel.rules.r4_enclosure import MAX_DEPTH, AllNonpositive, Enclosure, PointWitness
from petra.lang import load_design, parse_design
from petra.models import circuit
from petra.models import contracts as port_contracts
from petra.models.base import ComponentError, CoverageOrigin, Gap, NeedsInputBound, NoRuleForQuantity, Obligation
from petra.pipeline import check_design
from petra.premises import Tag
from petra.registry import build_registry
from petra.solvers import SolverSource, r4_enclosure
from petra.verdict import Fail, Pass

REGISTRY = build_registry()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

CURRENT = "lamp_draw.lighting.lamps.current"
AMBIENT = "ambient"
H = "const.install.clipped_direct.h"
WORST = {CURRENT: 10, AMBIENT: 40, H: 5}

RADIAL = """petra 0
design "radial" {
  owner "e.designer@example.org"
  environment indoor_dry
}
ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "survey"
circuit lighting {
  supply mains voltage 230 V fault_current in [0 kA, 6 kA] signed "dno@example.org" source "letter"
  breaker cb1 part mcb.B10
  wire w1 cable cable.cu_pvc_2_5 length 18 m install install.clipped_direct
  terminal t1 part terminal.lever_4mm2_75C
  consumer lamps
  connect mains.out -> cb1.in
  connect cb1.out -> w1.a
  connect w1.b -> t1.wire
  connect t1.out -> lamps.in
}
load lamp_draw {
  on lighting.lamps current in [0 A, 10 A]
  signed "e.designer@example.org" source "schedule"
}
"""

TWO_WIRES = """petra 0
design "two-runs" {
  owner "e.designer@example.org"
  environment indoor_dry
}
circuit lighting {
  supply mains voltage 230 V
  breaker cb1 part mcb.B10
  wire w1 cable cable.cu_pvc_2_5 length 18 m install install.clipped_direct
  terminal t1 part terminal.lever_4mm2_75C
  wire w2 cable cable.cu_pvc_2_5 length 18 m install install.clipped_direct
  consumer lamps
  connect mains.out -> cb1.in
  connect cb1.out -> w1.a
  connect w1.b -> t1.wire
  connect t1.out -> w2.a
  connect w2.b -> lamps.in
}
load lamp_draw {
  on lighting.lamps current in [0 A, 10 A]
  signed "e.designer@example.org" source "schedule"
}
"""

FAMILY = """petra 0
design "family" {
  owner "petra.library@example.org"
}
param size in [2.5 mm2, 16 mm2]
param ins in [0.8 mm, 1.0 mm]
param draw in [0 A, 10 A]
param amb in [10 degC, 40 degC]
ambient param amb
circuit c {
  supply mains voltage 230 V
  wire w1 cable cable.cu_pvc area param size insulation param ins length 10 m install install.clipped_direct
  consumer load
  connect mains.out -> w1.a
  connect w1.b -> load.in
}
load demand {
  on c.load current param draw
  signed "petra.library@example.org" source "family definition"
}
"""


def radial(*edits: tuple[str, str], text: str = RADIAL, extra: str = ""):
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"{old!r} is not in the template")
        text = text.replace(old, new)
    return parse_design(text + extra, "radial.petra", REGISTRY)


def lowered(design) -> dict:
    return {name: circuit.lower_circuit(c, design, REGISTRY) for name, c in design.components.items()}


def elaborate(design) -> list:
    models = lowered(design)
    out = []
    for req in coverage.generate(design, models, REGISTRY):
        out += circuit.DOMAIN.builders[req.mode](req, models[req.subject[0]], design, REGISTRY)
    return out


def one(design, mode, origin: str | None = None):
    found = [e for e in elaborate(design) if e.requirement.mode == mode and (origin is None or _origin(e) == origin)]
    if len(found) != 1:
        raise AssertionError(f"{len(found)} results for {mode.id} {origin}")
    return found[0]


def _origin(elaborated) -> str:
    origin = elaborated.requirement.origin
    return origin.rule if isinstance(origin, CoverageOrigin) else origin.claim


def solved(ob: Obligation):
    """(kernel result, evidence) for the solver's one piece of evidence."""
    offered = tuple(r4_enclosure.solve(ob.statement))
    if len(offered) != 1:
        raise AssertionError(f"the solver offered {len(offered)} pieces of evidence")
    return check(ob.statement, offered[0]), offered[0]


def at(statement: Statement, k: int, point: dict) -> float:
    """Goal expression k at a point; hyps the point does not name must be points."""
    box = {}
    for h in statement.hyps:
        value = Fraction(point[h.sym]) if h.sym in point else h.lo
        if h.sym not in point and h.lo != h.hi:
            raise AssertionError(f"{h.sym} spans [{h.lo}, {h.hi}]; name its value")
        box[h.sym] = Interval(value, value)
    return float(enclose(statement.goal.exprs[k], box).midpoint())


def labels(statement: Statement) -> set[str]:
    return {h.label for h in statement.hyps}


class CircuitPass(unittest.TestCase):
    def setUp(self):
        self.design = load_design(EXAMPLES / "circuit_pass.petra", REGISTRY)

    def test_every_wire_obligation_is_a_theorem(self):
        results = elaborate(self.design)
        self.assertEqual(
            sorted((e.requirement.mode.id, _origin(e)) for e in results),
            [
                ("wire.overload_protection", "wire.conductor"),
                ("wire.short_circuit", "wire.conductor"),
                ("wire.steady_temperature", "hot"),
                ("wire.steady_temperature", "wire.conductor"),
                ("wire.voltage_drop", "drop"),
            ],
        )
        for ob in results:
            with self.subTest(requirement=ob.requirement.id):
                self.assertIsInstance(ob, Obligation)
                self.assertIsInstance(solved(ob)[0], Theorem)

    def test_margins_at_the_worst_corner_match_the_hand_values(self):
        hot = one(self.design, circuit.STEADY_TEMPERATURE, "hot").statement
        self.assertAlmostEqual(at(hot, 0, WORST), 55.1667 - 70, places=3)
        self.assertAlmostEqual(at(hot, 1, WORST), 0.052368 - 1, places=5)
        drop = one(self.design, circuit.VOLTAGE_DROP).statement
        self.assertAlmostEqual(at(drop, 0, WORST), 2.970621 - 6.9, places=5)
        fault = one(self.design, circuit.SHORT_CIRCUIT).statement
        self.assertAlmostEqual(at(fault, 0, {"lighting.mains.fault_current": 6000}), 35000 - 82419.04, places=1)
        self.assertEqual(at(fault, 1, {"lighting.mains.fault_current": 6000}), 0)
        overload = one(self.design, circuit.OVERLOAD_PROTECTION).statement
        expected = [0, 55.1667 - 70, 0.052368 - 1, 55.1667 - 70, 0.052368 - 1]
        for k, margin in enumerate(expected):
            self.assertAlmostEqual(at(overload, k, WORST), margin, places=3)

    def test_each_obligation_rests_on_its_wire_model(self):
        models = {e.requirement.mode: e.model for e in elaborate(self.design)}
        self.assertEqual(models[circuit.STEADY_TEMPERATURE].id, "wire.thermal")
        self.assertEqual(models[circuit.OVERLOAD_PROTECTION].id, "wire.thermal")
        self.assertEqual(models[circuit.SHORT_CIRCUIT].id, "wire.adiabatic")
        self.assertEqual(models[circuit.VOLTAGE_DROP].id, "wire.drop")


class SteadyTemperature(unittest.TestCase):
    def test_a_50_degC_claim_is_refuted_at_full_current_hot_ambient_and_still_air(self):
        ob = one(radial(extra="claim cool: lighting.w1.temperature <= 50 degC under lamp_draw\n"), circuit.STEADY_TEMPERATURE, "cool")
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        point = dict(result.point)
        self.assertEqual((point[CURRENT], point[AMBIENT], point[H]), (10, 40, 5))
        self.assertAlmostEqual(at(ob.statement, evidence.body.which, point), 55.1667 - 50, places=3)

    def test_the_coverage_limit_is_the_insulation_rating_and_a_claim_states_its_own(self):
        d = radial(extra="claim hot: lighting.w1.temperature <= 70 degC under lamp_draw\n")
        default = one(d, circuit.STEADY_TEMPERATURE, "wire.conductor").statement
        claimed = one(d, circuit.STEADY_TEMPERATURE, "hot").statement
        self.assertIn("reg:const.pvc.theta_max", labels(default))
        self.assertNotIn("reg:const.pvc.theta_max", labels(claimed))

    def test_every_physical_input_enters_as_a_labelled_hypothesis(self):
        ob = one(radial(), circuit.STEADY_TEMPERATURE)
        self.assertEqual(labels(ob.statement), {
            "in:radial.ambient",
            "in:radial.lamp_draw.lighting.lamps.current",
            "dsg:radial.cable.cu_pvc_2_5.area",
            "dsg:radial.cable.cu_pvc_2_5.insulation",
            "reg:const.cu.alpha20",
            "reg:const.cu.rho20",
            "reg:const.install.clipped_direct.h",
            "reg:const.pvc.thermal_resistivity",
            "reg:const.pvc.theta_max",
        })

    def test_past_thermal_runaway_the_side_condition_refutes(self):
        ob = one(radial(("[0 A, 10 A]", "[62 A, 70 A]")), circuit.STEADY_TEMPERATURE)
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 1)
        self.assertAlmostEqual(at(ob.statement, 1, {CURRENT: 62, AMBIENT: 40, H: 10}), 0.033043, places=5)

    def test_short_of_runaway_the_side_condition_holds(self):
        ob = one(radial(("[0 A, 10 A]", "[0 A, 43 A]")), circuit.STEADY_TEMPERATURE)
        self.assertLess(at(ob.statement, 1, {CURRENT: 43, AMBIENT: 40, H: 5}), 0)
        self.assertGreater(at(ob.statement, 1, {CURRENT: 44, AMBIENT: 40, H: 5}), 0)

    def test_the_environment_class_gives_the_ambient_when_none_is_signed(self):
        ob = one(radial(('ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "survey"\n', "")), circuit.STEADY_TEMPERATURE)
        (hyp,) = [h for h in ob.statement.hyps if h.label == "reg:indoor_dry.ambient"]
        self.assertEqual((hyp.lo, hyp.hi), (5, 40))
        self.assertIsInstance(solved(ob)[0], Theorem)

    def test_with_no_ambient_at_all_the_obligation_is_a_gap(self):
        d = radial(('ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "survey"\n', ""),
                   ("  environment indoor_dry\n", ""))
        gap = one(d, circuit.STEADY_TEMPERATURE)
        self.assertIsInstance(gap, Gap)
        self.assertEqual(gap.needs, (NeedsInputBound(("radial",), "ambient", "degC"),))

    def test_with_no_signed_current_the_obligation_is_a_gap(self):
        d = radial(('load lamp_draw {\n  on lighting.lamps current in [0 A, 10 A]\n  signed "e.designer@example.org" source "schedule"\n}\n', ""))
        gap = one(d, circuit.STEADY_TEMPERATURE)
        self.assertEqual(gap.needs, (NeedsInputBound(("lighting", "lamps"), "current", "A"),))

    def test_a_lower_bound_on_temperature_is_a_gap(self):
        gap = one(radial(extra="claim warm: lighting.w1.temperature >= 10 degC under lamp_draw\n"), circuit.STEADY_TEMPERATURE, "warm")
        self.assertIsInstance(gap, Gap)
        self.assertIsInstance(gap.needs[0], NoRuleForQuantity)


class ShortCircuit(unittest.TestCase):
    def test_a_1_5_mm2_wire_cannot_absorb_the_let_through_energy(self):
        ob = one(radial(("cable.cu_pvc_2_5", "cable.cu_pvc_1_5")), circuit.SHORT_CIRCUIT)
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 0)
        self.assertAlmostEqual(at(ob.statement, 0, dict(result.point)), 35000 - 29670.85, places=1)

    def test_a_fault_beyond_the_breaking_capacity_is_refuted_at_its_top(self):
        ob = one(radial(("[0 kA, 6 kA]", "[0 kA, 10 kA]")), circuit.SHORT_CIRCUIT)
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 1)
        self.assertEqual(dict(result.point)["lighting.mains.fault_current"], 10000)

    def test_k_is_derived_from_copper_constants(self):
        ob = one(radial(), circuit.SHORT_CIRCUIT)
        self.assertTrue({"reg:const.cu.qc", "reg:const.cu.beta", "reg:const.cu.rho20", "reg:const.pvc.theta_sc",
                         "reg:mcb.B10.I2t", "reg:mcb.B10.Icn"} <= labels(ob.statement))

    def test_without_a_signed_fault_current_it_is_a_gap(self):
        gap = one(radial((' fault_current in [0 kA, 6 kA] signed "dno@example.org" source "letter"', "")), circuit.SHORT_CIRCUIT)
        self.assertEqual(gap.needs, (NeedsInputBound(("lighting", "mains"), "fault_current", "A"),))

    def test_without_a_breaker_nothing_limits_the_energy(self):
        d = radial(("  breaker cb1 part mcb.B10\n", ""), ("  connect mains.out -> cb1.in\n  connect cb1.out -> w1.a\n", "  connect mains.out -> w1.a\n"))
        gap = one(d, circuit.SHORT_CIRCUIT)
        self.assertEqual([type(n) for n in gap.needs], [NoRuleForQuantity])


class VoltageDrop(unittest.TestCase):
    def test_a_1_percent_claim_is_refuted_at_full_current(self):
        ob = one(radial(extra="claim drop: lighting.w1.voltage_drop <= 1 % under lamp_draw\n"), circuit.VOLTAGE_DROP)
        result, _ = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(dict(result.point)[CURRENT], 10)
        self.assertAlmostEqual(at(ob.statement, 0, dict(result.point)), 2.970621 - 2.3, places=5)

    def test_coverage_allows_5_percent(self):
        ob = one(radial(), circuit.VOLTAGE_DROP)
        self.assertAlmostEqual(at(ob.statement, 0, WORST), 2.970621 - 11.5, places=5)
        self.assertIsInstance(solved(ob)[0], Theorem)

    def test_a_downstream_wire_carries_the_drop_of_every_wire_before_it(self):
        claims = ("claim near: lighting.w1.voltage_drop <= 2 % under lamp_draw\n"
                  "claim far: lighting.w2.voltage_drop <= 2 % under lamp_draw\n")
        d = radial(text=TWO_WIRES, extra=claims)
        near, far = one(d, circuit.VOLTAGE_DROP, "near"), one(d, circuit.VOLTAGE_DROP, "far")
        self.assertAlmostEqual(at(near.statement, 0, WORST), 2.970621 - 4.6, places=5)
        self.assertAlmostEqual(at(far.statement, 0, WORST), 2 * 2.970621 - 4.6, places=5)
        self.assertIsInstance(solved(near)[0], Theorem)
        self.assertIsInstance(solved(far)[0], Refutation)


class OverloadProtection(unittest.TestCase):
    def test_a_16_A_breaker_does_not_protect_2_5_mm2_in_still_air(self):
        ob = one(radial(("mcb.B10", "mcb.B16")), circuit.OVERLOAD_PROTECTION)
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 1)
        point = dict(result.point)
        self.assertEqual((point[AMBIENT], point[H]), (40, 5))
        self.assertAlmostEqual(at(ob.statement, 1, point), 82.4897 - 70, places=3)

    def test_a_design_current_above_the_rating_is_refuted(self):
        ob = one(radial(("[0 A, 10 A]", "[0 A, 12 A]")), circuit.OVERLOAD_PROTECTION)
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 0)
        self.assertEqual(dict(result.point)[CURRENT], 12)

    def test_the_tripping_current_comes_from_the_breaker_standard(self):
        ob = one(radial(), circuit.OVERLOAD_PROTECTION)
        self.assertTrue({"reg:mcb.B10.In", "reg:const.iec60898_1.trip_factor"} <= labels(ob.statement))

    def test_the_overload_verdict_names_the_iec_60364_4_43_factor_in_its_footprint(self):
        d = radial(extra="claim protected: lighting.w1.overload_protection <= 1 under lamp_draw\n"
                         "claim hot: lighting.w1.temperature <= 70 degC under lamp_draw\n")
        verdicts = {e.claim: e.verdict for e in check_design(d, REGISTRY, (SolverSource(),)).entries}
        self.assertIsInstance(verdicts["protected"], Pass)
        label = "reg:const.iec60364_4_43.overload_factor"
        (factor,) = [p for p in verdicts["protected"].footprint.premises if p.label == label]
        self.assertEqual((factor.tag, factor.owner, factor.range), (Tag.SANCTIONED, "IEC", Interval(Fraction(29, 20), Fraction(29, 20))))
        self.assertIn("60364-4-43", factor.source)
        self.assertIsInstance(verdicts["hot"], Pass)
        self.assertNotIn(label, verdicts["hot"].footprint.labels, "the steady-temperature verdict does not rest on the overload rule")

    def test_without_a_breaker_overload_protection_is_a_gap(self):
        d = radial(("  breaker cb1 part mcb.B10\n", ""), ("  connect mains.out -> cb1.in\n  connect cb1.out -> w1.a\n", "  connect mains.out -> w1.a\n"))
        gap = one(d, circuit.OVERLOAD_PROTECTION)
        self.assertEqual([type(n) for n in gap.needs], [NoRuleForQuantity])


class Family(unittest.TestCase):
    """A series cable over a range of sizes: the root box over-estimates, so the solver
    must split. Worst corner: 2.5 mm2, 0.8 mm, 10 A, 40 degC, h = 5, theta 55.1667 degC."""

    def obligation(self, limit: str) -> Obligation:
        d = parse_design(FAMILY + f"claim hot: c.w1.temperature <= {limit} degC under demand\n", "family.petra", REGISTRY)
        return one(d, circuit.STEADY_TEMPERATURE, "hot")

    def test_a_claim_just_above_the_worst_corner_needs_a_partition(self):
        ob = self.obligation("55.2")
        self.assertIsInstance(check(ob.statement, Evidence(Enclosure(Leaf()))), Rejection)
        result, evidence = solved(ob)
        self.assertIsInstance(result, Theorem)
        self.assertIsInstance(evidence.body.partition, Split)

    def test_a_claim_just_below_the_worst_corner_is_refuted_there(self):
        ob = self.obligation("55.1")
        result, _ = solved(ob)
        self.assertIsInstance(result, Refutation)
        point = dict(result.point)
        self.assertEqual((point["size"], point["ins"], point["draw"], point["amb"], point[H]),
                         (Fraction(1, 400000), Fraction(1, 1250), 10, 40, 5))

    def test_the_series_parameters_are_the_family_params(self):
        ob = self.obligation("70")
        self.assertTrue({"par:family.size", "par:family.ins", "par:family.draw", "par:family.amb"} <= labels(ob.statement))


class Lowering(unittest.TestCase):
    def test_the_example_lowers_to_its_elements_and_one_series_path(self):
        model = lowered(load_design(EXAMPLES / "circuit_pass.petra", REGISTRY))["lighting"]
        self.assertEqual(model.elements["cb1"], circuit.Breaker("cb1", "mcb.B10"))
        self.assertEqual(model.elements["t1"], circuit.Terminal("t1", "terminal.lever_4mm2_75C"))
        wire = model.elements["w1"]
        self.assertEqual((wire.cable, wire.install, wire.area, wire.insulation), ("cable.cu_pvc_2_5", "install.clipped_direct", None, None))
        self.assertEqual(model.elements["mains"].fault_current.name, "lighting.mains.fault_current")
        (draw,) = model.elements["lamps"].draws
        self.assertEqual((draw.case, draw.current.name), ("lamp_draw", CURRENT))
        self.assertEqual(circuit.topology(model), (circuit.SeriesPath("mains", "cb1", ("w1", "t1"), "lamps"),))

    def assertRejected(self, *edits, extra: str = "", fragment: str, text: str = RADIAL):
        d = radial(*edits, text=text, extra=extra)
        with self.assertRaises(ComponentError) as ctx:
            lowered(d)
        self.assertTrue(any(fragment in p for p in ctx.exception.problems), ctx.exception.problems)

    def test_rejects_a_connection_to_an_unknown_element(self):
        self.assertRejected(("connect t1.out -> lamps.in", "connect t1.out -> lamp.in"), fragment="'lamp' is not an element")

    def test_rejects_a_connection_to_the_wrong_port(self):
        self.assertRejected(("connect w1.b -> t1.wire", "connect w1.a -> t1.wire"), fragment="use w1.b")

    def test_rejects_an_element_declared_twice(self):
        self.assertRejected(("  consumer lamps\n", "  consumer lamps\n  consumer lamps\n"), fragment="declared twice")

    def test_rejects_a_registry_id_of_the_wrong_kind(self):
        self.assertRejected(("part mcb.B10", "part terminal.lever_4mm2_75C"), fragment="not a breaker")

    def test_rejects_a_series_cable_without_its_size(self):
        self.assertRejected(("cable.cu_pvc_2_5", "cable.cu_pvc"), fragment="area needs")

    def test_rejects_a_size_given_a_second_area(self):
        self.assertRejected(("length 18 m", "area 4 mm2 insulation 1 mm length 18 m"), fragment="is a size")

    def test_rejects_a_load_field_other_than_current(self):
        self.assertRejected(("on lighting.lamps current", "on lighting.lamps power"), fragment="load field is current")

    def test_rejects_an_unknown_wire_quantity(self):
        self.assertRejected(extra="claim c: lighting.w1.sag <= 1 % under lamp_draw\n", fragment="unknown wire quantity")

    def test_rejects_a_claim_bound_of_the_wrong_dimension(self):
        self.assertRejected(extra="claim c: lighting.w1.temperature <= 3 % under lamp_draw\n", fragment="bounded by a temperature")

    def test_rejects_an_element_on_no_path(self):
        self.assertRejected(("  consumer lamps\n", "  consumer lamps\n  terminal t2 part terminal.lever_4mm2_75C\n"), fragment="t2 is not on a path")

    def test_rejects_a_wire_upstream_of_its_breaker(self):
        self.assertRejected(
            ("  connect mains.out -> cb1.in\n  connect cb1.out -> w1.a\n  connect w1.b -> t1.wire\n  connect t1.out -> lamps.in\n",
             "  connect mains.out -> w1.a\n  connect w1.b -> cb1.in\n  connect cb1.out -> t1.wire\n  connect t1.out -> lamps.in\n"),
            fragment="cannot protect it")

    def test_rejects_two_breakers_on_one_path(self):
        self.assertRejected(
            ("  breaker cb1 part mcb.B10\n", "  breaker cb1 part mcb.B10\n  breaker cb2 part mcb.B6\n"),
            ("connect cb1.out -> w1.a", "connect cb1.out -> cb2.in\n  connect cb2.out -> w1.a"),
            fragment="one breaker per path")


class Features(unittest.TestCase):
    def test_a_wire_is_a_conductor_and_each_connection_of_parts_a_contact_pair(self):
        d = load_design(EXAMPLES / "circuit_pass.petra", REGISTRY)
        found = circuit.features(lowered(d)["lighting"], d, REGISTRY)
        self.assertEqual([(f.subject, f.kind, f.materials) for f in found], [
            (("lighting", "w1"), circuit.CONDUCTOR, ("copper.cu_etp",)),
            (("lighting", "cb1", "w1"), "contact_pair", ("copper.cu_etp", "copper.cu_etp")),
            (("lighting", "w1", "t1"), "contact_pair", ("copper.cu_etp", "copper.cu_etp")),
        ])

    def test_a_coated_terminal_shows_its_coating_to_the_wire(self):
        terminal = REGISTRY.parts["terminal.lever_4mm2_75C"]
        plated = dataclasses.replace(REGISTRY, parts={**REGISTRY.parts, terminal.id: dataclasses.replace(terminal, process="process.zinc_plate")})
        d = load_design(EXAMPLES / "circuit_pass.petra", REGISTRY)
        found = circuit.features(lowered(d)["lighting"], d, plated)
        self.assertEqual([f.materials for f in found if f.kind == "contact_pair"],
                         [("copper.cu_etp", "copper.cu_etp"), ("copper.cu_etp", "zinc.electroplate")])

    def test_a_voltage_drop_claim_settles_the_coverage_demand_and_its_absence_does_not(self):
        claimed = load_design(EXAMPLES / "circuit_pass.petra", REGISTRY)
        demanded = [r.mode for r in coverage.generate(claimed, lowered(claimed), REGISTRY) if isinstance(r.origin, CoverageOrigin)]
        self.assertEqual(demanded, [circuit.STEADY_TEMPERATURE, circuit.SHORT_CIRCUIT, circuit.OVERLOAD_PROTECTION])
        bare = radial()
        demanded = [r.mode for r in coverage.generate(bare, lowered(bare), REGISTRY) if isinstance(r.origin, CoverageOrigin)]
        self.assertEqual(demanded, [circuit.STEADY_TEMPERATURE, circuit.SHORT_CIRCUIT, circuit.OVERLOAD_PROTECTION, circuit.VOLTAGE_DROP])


class TerminalFit(unittest.TestCase):
    """A terminal clamps every wire connected at either of its ports, and the wire's
    conductor area must lie in the clamp's range (registry conductor_min to
    conductor_max): 0.2 to 4 mm2 for the lever terminal, 1.5 to 16 mm2 for the screw one."""

    FIT = "conductor_area"

    def contracts(self, design) -> dict:
        """{(port, quantity): obligation or gap} for every contract the circuits state."""
        out = []
        for model in lowered(design).values():
            ports = circuit.ports(model, REGISTRY)
            out += port_contracts.contract_obligations(design, ports.connections, {s.ref: s for s in ports.specs}, REGISTRY)
        return {(".".join(e.requirement.subject), e.requirement.qoi.name): e for e in out}

    def test_the_example_conductor_fits_its_terminal(self):
        ob = self.contracts(load_design(EXAMPLES / "circuit_pass.petra", REGISTRY))[("lighting.t1.wire", self.FIT)]
        self.assertIsInstance(solved(ob)[0], Theorem)
        self.assertAlmostEqual(at(ob.statement, 0, {}), 2.5e-6 - 4e-6)
        self.assertAlmostEqual(at(ob.statement, 1, {}), 0.2e-6 - 2.5e-6)
        self.assertIn("reg:terminal.lever_4mm2_75C.conductor_max", labels(ob.statement))

    def test_a_16_mm2_conductor_in_a_4_mm2_terminal_fails_its_contract(self):
        report = check_design(radial(("cable.cu_pvc_2_5", "cable.cu_pvc_16")), REGISTRY, (SolverSource(),))
        self.assertIsInstance(report.verdict, Fail)
        self.assertEqual(report.verdict.obligation.requirement.id, f"lighting.t1.wire/port.contract/coverage.port.contract/{self.FIT}")
        self.assertAlmostEqual(at(report.verdict.obligation.statement, 0, {}), 16e-6 - 4e-6)

    def test_a_terminal_clamps_a_wire_at_its_out_port_too(self):
        found = self.contracts(radial(("cable.cu_pvc_2_5 length 18 m install install.clipped_direct\n  consumer",
                                       "cable.cu_pvc_16 length 18 m install install.clipped_direct\n  consumer"), text=TWO_WIRES))
        self.assertIsInstance(solved(found[("lighting.t1.wire", self.FIT)])[0], Theorem, "w1 is 2.5 mm2")
        result, _ = solved(found[("lighting.t1.out", self.FIT)])
        self.assertIsInstance(result, Refutation, "w2 is 16 mm2")
        self.assertEqual({q for port, q in found if port == "lighting.t1.out"}, {"temperature", "current", self.FIT},
                         "the terminal's ratings hold for the conductor on each side")

    def test_a_port_that_clamps_no_wire_states_no_fit(self):
        found = self.contracts(load_design(EXAMPLES / "circuit_pass.petra", REGISTRY))
        self.assertFalse([key for key in found if key[0] == "lighting.t1.out"], "t1.out joins the consumer, not a wire")

    def test_a_conductor_below_the_clamp_fails_at_the_small_end(self):
        family = FAMILY.replace("param size in [2.5 mm2, 16 mm2]", "param size in [1 mm2, 16 mm2]").replace(
            "  consumer load\n  connect mains.out -> w1.a\n  connect w1.b -> load.in\n",
            "  terminal t1 part terminal.screw_16mm2_75C\n  consumer load\n  connect mains.out -> w1.a\n"
            "  connect w1.b -> t1.wire\n  connect t1.out -> load.in\n")
        ob = self.contracts(parse_design(family, "f.petra", REGISTRY))[("c.t1.wire", self.FIT)]
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 1, "the lower end of the clamp's range")
        self.assertEqual(dict(result.point)["size"], Fraction(1, 10**6))


def parabola(c: Fraction) -> Statement:
    """x (1 - x) - c <= 0 on [0, 1]; the true maximum is 1/4 - c at x = 1/2."""
    x = Sym("x")
    expr = Add((Mul((x, Add((Const(Fraction(1)), Neg(x))))), Const(-c)))
    return Statement((RangeHyp("x", Fraction(0), Fraction(1), "in:t.x"),), AllNonpositive((expr,)))


class Search(unittest.TestCase):
    """The R4 solver alone, on a goal whose root enclosure is loose because x appears
    twice: [0, 1] (1 - [0, 1]) - c reaches 1 - c."""

    def test_a_true_goal_gets_a_partition_the_kernel_accepts(self):
        st = parabola(Fraction(13, 50))
        (evidence,) = r4_enclosure.solve(st)
        self.assertIsInstance(evidence.body.partition, Split)
        self.assertIsInstance(check(st, evidence), Theorem)
        self.assertLessEqual(r4_enclosure.search_stats()["max_depth"], MAX_DEPTH)

    def test_a_false_goal_gets_the_point_where_it_fails(self):
        st = parabola(Fraction(6, 25))
        (evidence,) = r4_enclosure.solve(st)
        self.assertEqual(evidence.body, PointWitness((("x", Fraction(1, 2)),), 0))
        self.assertIsInstance(check(st, evidence), Refutation)

    def test_a_goal_that_holds_with_no_margin_is_left_open(self):
        self.assertEqual(tuple(r4_enclosure.solve(parabola(Fraction(1, 4)), max_cells=300)), ())
        self.assertLessEqual(r4_enclosure.search_stats()["cells"], 300)

    def test_search_takes_bare_expressions_and_a_box(self):
        st = parabola(Fraction(13, 50))
        box = {"x": Interval(Fraction(0), Fraction(1))}
        self.assertIsInstance(r4_enclosure.search(st.goal.exprs, box, 1000), Split)
        self.assertEqual(r4_enclosure.search(parabola(Fraction(6, 25)).goal.exprs, box, 1000), {"x": Fraction(1, 2)})


if __name__ == "__main__":
    unittest.main()
