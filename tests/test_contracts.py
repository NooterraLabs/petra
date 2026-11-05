"""Port contracts: interval inclusion of what one port guarantees in what the port it
connects to assumes, through the circuit's ports, the R4 solver and kernel.check.
Owner: C.

Hand values (see tests/test_circuit.py for the heat balance): a 2.5 mm2 wire at 40 degC
ambient in still air (h = 5) runs at 55.1667 degC at 10 A and 76.6572 degC at 15 A. The
lever terminal is rated 75 degC and 32 A.
"""
import unittest
from fractions import Fraction
from pathlib import Path

from lola.ir import QoiRef, Span
from lola.kernel import Refutation, Theorem, check
from lola.lang import load_design
from lola.models import circuit, contracts
from lola.models.base import (
    PORT_CONTRACT,
    Connection,
    CoverageOrigin,
    Gap,
    NoRuleForQuantity,
    Obligation,
    PortQuantity,
    PortRef,
    PortSpec,
    Side,
)
from lola.registry import build_registry
from lola.solvers import r4_enclosure

from tests.test_circuit import AMBIENT, CURRENT, H, WORST, at, lowered, radial

REGISTRY = build_registry()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
TERMINAL = PortRef("lighting", "t1", "wire")


def contracts_of(design) -> dict:
    """{quantity: obligation or gap} for every contract the design's circuits state."""
    out = []
    for model in lowered(design).values():
        ports = circuit.ports(model, REGISTRY)
        out += contracts.contract_obligations(design, ports.connections, {s.ref: s for s in ports.specs}, REGISTRY)
    return {e.requirement.qoi.name: e for e in out}


def solved(ob: Obligation):
    (evidence,) = r4_enclosure.solve(ob.statement)
    return check(ob.statement, evidence), evidence


class WireIntoTerminal(unittest.TestCase):
    def test_the_example_states_two_contracts_at_the_terminal_and_both_hold(self):
        found = contracts_of(load_design(EXAMPLES / "circuit_pass.lola", REGISTRY))
        self.assertEqual(set(found), {"temperature", "current"})
        for quantity, ob in found.items():
            with self.subTest(quantity=quantity):
                req = ob.requirement
                self.assertEqual((req.subject, req.mode, req.origin), (("lighting", "t1", "wire"), PORT_CONTRACT, CoverageOrigin("port.contract")))
                self.assertEqual(req.qoi, QoiRef(("lighting", "t1", "wire"), quantity))
                self.assertIsInstance(solved(ob)[0], Theorem)

    def test_margins_at_the_worst_corner_match_the_hand_values(self):
        found = contracts_of(load_design(EXAMPLES / "circuit_pass.lola", REGISTRY))
        self.assertAlmostEqual(at(found["temperature"].statement, 0, WORST), 55.1667 - 75, places=3)
        self.assertEqual(at(found["current"].statement, 0, WORST), 10 - 32)

    def test_each_side_rests_on_the_model_that_computes_it(self):
        found = contracts_of(radial())
        self.assertEqual(found["temperature"].model, circuit.THERMAL)
        self.assertEqual(found["current"].model, circuit.SERIES)
        self.assertIn("reg:terminal.lever_4mm2_75C.temperature_max", {h.label for h in found["temperature"].statement.hyps})

    def test_15_A_overheats_the_terminal(self):
        ob = contracts_of(radial(("[0 A, 10 A]", "[0 A, 15 A]")))["temperature"]
        result, _ = solved(ob)
        self.assertIsInstance(result, Refutation)
        point = dict(result.point)
        self.assertEqual((point[CURRENT], point[AMBIENT], point[H]), (15, 40, 5))
        self.assertAlmostEqual(at(ob.statement, 0, point), 76.6572 - 75, places=3)

    def test_40_A_exceeds_the_terminal_rating(self):
        ob = contracts_of(radial(("[0 A, 10 A]", "[0 A, 40 A]")))["current"]
        result, _ = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(dict(result.point)[CURRENT], 40)
        self.assertEqual(at(ob.statement, 0, dict(result.point)), 40 - 32)

    def test_a_wire_past_thermal_runaway_guarantees_no_temperature(self):
        ob = contracts_of(radial(("[0 A, 10 A]", "[62 A, 70 A]")))["temperature"]
        self.assertEqual(tuple(r4_enclosure.solve(ob.statement, max_cells=200)), ())

    def test_with_no_ambient_nothing_guarantees_the_temperature(self):
        d = radial(('ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "survey"\n', ""),
                   ("  environment indoor_dry\n", ""))
        found = contracts_of(d)
        self.assertIsInstance(found["temperature"], Gap)
        (need,) = found["temperature"].needs
        self.assertIsInstance(need, NoRuleForQuantity)
        self.assertIn("lighting.t1.wire", need.reason)
        self.assertIsInstance(solved(found["current"])[0], Theorem)

    def test_with_no_signed_current_nothing_guarantees_either_quantity(self):
        load = 'load lamp_draw {\n  on lighting.lamps current in [0 A, 10 A]\n  signed "e.designer@example.org" source "schedule"\n}\n'
        found = contracts_of(radial((load, "")))
        self.assertEqual({q: type(e) for q, e in found.items()}, {"temperature": Gap, "current": Gap})


class Synthetic(unittest.TestCase):
    """Hand-built specs over the circuit_pass design's draw (0 A to 10 A): a guarantee of
    [draw, draw] checked against an assumption of [B6 rating, terminal rating] = [6, 32]."""

    def setUp(self):
        self.design = load_design(EXAMPLES / "circuit_pass.lola", REGISTRY)
        draw = lowered(self.design)["lighting"].elements["lamps"].draws[0].current
        self.draw = lambda sb: sb.input(draw)
        self.out, self.into = PortRef("x", "p", "out"), PortRef("x", "q", "in")
        self.connection = Connection(self.out, self.into, Span("t.lola", 1, 1))

    def obligations(self, assumes: Side, guarantees: Side | None) -> tuple:
        specs = {self.out: PortSpec(self.out, {PortQuantity.CURRENT: assumes}, {})}
        if guarantees is not None:
            specs[self.into] = PortSpec(self.into, {}, {PortQuantity.CURRENT: guarantees})
        return contracts.contract_obligations(self.design, (self.connection,), specs, REGISTRY)

    def test_an_upper_assumption_alone_holds_and_rests_on_the_contract_premise(self):
        (ob,) = self.obligations(Side(None, lambda sb: sb.registry("terminal.lever_4mm2_75C", "current_max"), None),
                                 Side(self.draw, self.draw, None))
        self.assertEqual(ob.requirement.subject, ("x", "p", "out"))
        self.assertIs(ob.model, contracts.CONTRACT)
        self.assertIsInstance(solved(ob)[0], Theorem)

    def test_a_lower_assumption_is_checked_against_the_lower_guarantee(self):
        (ob,) = self.obligations(Side(lambda sb: sb.registry("mcb.B6", "In"), lambda sb: sb.registry("terminal.lever_4mm2_75C", "current_max"), None),
                                 Side(self.draw, self.draw, None))
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        self.assertEqual(evidence.body.which, 1)
        self.assertEqual(dict(result.point)[CURRENT], 0)

    def test_an_assumption_the_other_end_does_not_guarantee_is_a_gap(self):
        (gap,) = self.obligations(Side(lambda sb: sb.registry("mcb.B6", "In"), None, None), Side(None, self.draw, None))
        self.assertIsInstance(gap, Gap)
        self.assertIn("lower bound on current at x.p.out from x.q.in", gap.needs[0].reason)
        (gap,) = self.obligations(Side(None, lambda sb: sb.registry("mcb.B6", "In"), None), None)
        self.assertIsInstance(gap, Gap)

    def test_a_guarantee_nobody_assumes_states_nothing(self):
        specs = {self.into: PortSpec(self.into, {}, {PortQuantity.CURRENT: Side(self.draw, self.draw, None)})}
        self.assertEqual(contracts.contract_obligations(self.design, (self.connection,), specs, REGISTRY), ())

    def test_the_draw_bounds_are_the_signed_range(self):
        (ob,) = self.obligations(Side(lambda sb: sb.registry("mcb.B6", "In"), lambda sb: sb.registry("terminal.lever_4mm2_75C", "current_max"), None),
                                 Side(self.draw, self.draw, None))
        self.assertEqual(at(ob.statement, 0, {CURRENT: 10}), 10 - 32)
        self.assertEqual(at(ob.statement, 1, {CURRENT: Fraction(0)}), 6 - 0)


if __name__ == "__main__":
    unittest.main()
