"""Pin-jointed trusses from .petra text to kernel results. Owner: T.

Statements are built from the lowered example IR, evidence comes from the truss solvers
(R1, R2; R4 goals over the R3 force lemmas through SolverSource), and the kernel decides.
Expected forces and margins are hand statics, kept in the messages.

Hand values used throughout, steel E in [200, 210] GPa, fy = 355 MPa:
  CHS 60.3x3.2  A = pi/4 (60.3^2 - 53.9^2) = 574.0 mm2,  I = pi/64 (60.3^4 - 53.9^4) = 23.47 cm4
  CHS 76.1x3.2  I = pi/64 (76.1^4 - 69.7^4) = 48.78 cm4
  CHS 48.3x3.2  A = pi/4 (48.3^2 - 41.9^2) = 453.4 mm2,  A fy = 160.95 kN
  Euler load of a 2.5 m CHS 60.3x3.2 diagonal at E = 200 GPa: pi^2 E I / L^2 = 74.12 kN
  Euler load of the 3 m CHS 76.1x3.2 top chord at E = 200 GPa: pi^2 E I / L^2 = 106.98 kN
  EN 1993-1-1 6.3.1.2, curve c (alpha 0.49), at E = 200 GPa:
    diagonal  lambda = sqrt(203.78 / 74.12) = 1.658, Phi = 2.232, chi = 0.2684, N_b = 54.69 kN
    top chord lambda = sqrt(260.17 / 106.98) = 1.559, Phi = 2.049, chi = 0.2960, N_b = 77.02 kN
  EN 1993-1-1 6.3.3 by Annex B lowers N_b for the self-weight bending M to
  N_c = N_b (1 - x) / (1 + 0.8 x), x = 0.95 M / (W_el fy), at the registry's top density
  8004.77 kg/m3 and g = 9.84 m/s2 (W_el = 2 I / D):
    diagonal  M = 45.21 N/m x 1.5 m x 2.5 m / 8 = 21.19 N m, x = 0.00729, N_c = 0.98696 N_b = 53.98 kN
    top chord M = 57.73 N/m x 3 m x 3 m / 8 = 64.94 N m, x = 0.01356, N_c = 0.97586 N_b = 75.16 kN
Footbridge statics (P_D, P_E node loads, downward negative):
  N_ad = 0.9375 P_D + 0.3125 P_E    N_ec = 0.3125 P_D + 0.9375 P_E
  N_ab = 0.75 (0.75 P_D + 0.25 P_E) N_de = 0.375 (P_D + P_E)    N_db = -N_be = 0.3125 (P_D - P_E)
  a downward load P_B at B: N_ad = N_ec = -0.625 P_B
Self-weight, steel 7850 kg/m3, g in [9.76, 9.84] m/s2 (at 9.84):
  CHS 60.3x3.2 weighs 44.34 N/m, CHS 76.1x3.2 56.61 N/m
  node loads W_D = W_E = 195.8 N (half the top chord and two diagonals), W_B = 243.9 N
  N_ad(weight) = -(1.25 x 195.8 + 0.625 x 243.9) = -397.1 N
  the force along diag_ad varies by g rho A |dy| / 2 = 44.3 N either side of N_ad
"""
import dataclasses
import unittest
from fractions import Fraction
from pathlib import Path

from petra import coverage
from petra.ir import Design
from petra.kernel import Const, Evidence, Matrix, Refutation, Rejection, Statement, Theorem, TooWeak, check, is_issued, statement_hash
from petra.kernel.rules.r1_linear import FarkasRay, FeasiblePoints, LinearFeasible
from petra.kernel.rules.r2_definite import GramPositiveDefinite
from petra.kernel.rules.r3_hypercircle import HypercircleFields
from petra.kernel.rules.r4_enclosure import AllNonpositive
from petra.lang import parse_design
from petra.models import truss
from petra.models.base import ClaimOrigin, ComponentError, Gap, NeedsInputBound, NoRuleForQuantity, Obligation, OutsideValidity
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource, r1_linear, r2_definite, r3_hypercircle
from petra.verdict import Fail, Pass, Unknown

REGISTRY = build_registry()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
PASS = (EXAMPLES / "truss_pass.petra").read_text(encoding="utf-8")
FAIL = (EXAMPLES / "truss_fail.petra").read_text(encoding="utf-8")
KN = 1000

HANGER = """petra 0

design "three-bar-hanger" {
  owner "a.reviewer@example.org"
  environment indoor_dry
}

truss frame {
  material steel.S355
  section chs.48_3x3_2

  node L at (-3 m, 4 m) support pinned
  node M at (0 m, 4 m) support pinned
  node R at (3 m, 4 m) support pinned
  node D at (0 m, 0 m)

  member left:   L -- D
  member middle: M -- D
  member right:  R -- D
}

load hang {
  on frame.D fy in [-100 kN, -80 kN]
  signed "client.structures@example.org" source "hanger brief"
}

claim strength:  frame.collapse_factor >= 4 under hang
claim stability: frame.stability_factor >= 3 under hang
claim stress:    frame.member(middle).stress <= 235 MPa under hang
"""
"""Three bars from pinned supports at (-3, 4), (0, 4), (3, 4) m to one free node: two
free DOFs, three members, so one degree of indeterminacy. Compatibility with equal E A:
the middle bar stretches by the drop d, the 5 m sides by 0.8 d, so N_m / N_s = (1/4) /
(0.8/5) = 25/16, and N_m + 2 (0.8) N_s = P gives N_m = 125 P / 253, N_s = 80 P / 253.
CHS 48.3x3.2 weighs 35.02 N/m at g = 9.84, so D carries W_D = 35.02 (4 + 5 + 5) / 2 =
245.2 N of the bars' weight on top of P."""

G1 = """petra 0

design "keystone-gap-g1" {{
  owner "task.owner@example.org"
  environment indoor_dry
}}

truss frame {{
  material steel.S355
  section chs.114_3x3_6

  node A at (0 m, 0 m) support pinned
  node B at (6 m, 0 m)
  node C at (12 m, 0 m) support roller_x
  node D at (3 m, 1.5 m)
  node E at (9 m, 1.5 m)

  member bottom_ab: A -- B
  member bottom_bc: B -- C
  member top_de:    D -- E section chs.48_3x3_2
  member diag_ad:   A -- D
  member diag_db:   D -- B
  member diag_be:   B -- E
  member diag_ec:   E -- C
}}

load crowd {{
  on frame.D fy in [-{p} kN, -{p} kN]
  on frame.E fy in [-{p} kN, -{p} kN]
  signed "task.owner@example.org" source "keystone probe"
}}

claim strength:  frame.collapse_factor >= 1.5 under crowd
claim stability: frame.stability_factor >= 1.5 under crowd
"""
"""Registered gap G1 of docs/keystone_protocol.md: a 12 m Warren girder of two panels whose
top chord D-E is one horizontal 6 m CHS 48.3x3.2, every other member CHS 114.3x3.6, under P
at D and E. Statics: N_de = -2 P, plus 2.721 kN of compression from the members' weight at
g = 9.84 m/s2 and 78.77 kN/m3 (the top of the registry's ranges). At E = 200 GPa the chord's
EN 1993-1-1 6.3.1 resistance is N_b = 5.791 kN (lambda = 5.03, chi = 0.0360). Its weight,
35.71 N/m, bends it by M = 160.7 N m at midspan, M / (W_el fy) = 0.0944 with W_el = 4.797 cm3.
The 6.3.3 member check by Annex B, N / N_b + 0.95 (1 + 0.8 N / N_b) M / (W_el fy) <= 1, holds
up to N = 0.8494 N_b = 4.919 kN, so the claimed factor 1.5 holds up to
P = (4.919 - 2.721) / (1.5 x 2) = 0.733 kN. Without the bending it held up to 1.023 kN."""

SOLVERS = {LinearFeasible: r1_linear.solve, GramPositiveDefinite: r2_definite.solve}


def design(text: str, *edits: tuple[str, str]) -> Design:
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"edit target {old!r} is not in the text")
        text = text.replace(old, new)
    return parse_design(text, "t.petra", REGISTRY)


def lowered(d: Design) -> truss.Truss:
    return truss.lower_truss(d.components["frame"], d, REGISTRY)


def elaborate(d: Design) -> dict[str, tuple]:
    """Requirement id -> what the truss builder made of it, for every requirement."""
    model = lowered(d)
    return {req.id: truss.DOMAIN.builders[req.mode](req, model, d, REGISTRY) for req in coverage.generate(d, {"frame": model}, REGISTRY)}


def candidates(statement) -> list[Evidence]:
    if isinstance(statement.goal, AllNonpositive):
        return list(SolverSource().offer(statement, statement_hash(statement)))
    return list(SOLVERS[type(statement.goal)](statement))


def decide(statement):
    """The first issued result over the solver's candidates, else the last rejection."""
    result = None
    for evidence in candidates(statement):
        result = check(statement, evidence)
        if is_issued(result):
            return result
    return result


def solved(statement):
    """The first issued result over SolverSource's candidates, as the pipeline settles it."""
    for evidence in SolverSource().offer(statement, statement_hash(statement)):
        result = check(statement, evidence)
        if is_issued(result):
            return result
    return None


def buckling(d: Design, member: str):
    (obligation,) = elaborate(d)[f"frame.{member}/truss.member_buckling/coverage.truss.axial_member"]
    return obligation.statement


def claimed(d: Design, claim: str) -> Obligation:
    (found,) = [o for out in elaborate(d).values() for o in out if o.requirement.origin == ClaimOrigin(claim)]
    return found


def forces(statement, part: str = "N_load") -> dict[str, tuple[Fraction, Fraction]]:
    """Member name -> the R3 lemma range the solver proposes for one part of its force:
    "N_load" in newtons, or "N_per_down.<node>" in newtons per newton downward at node."""
    return {r.sym.split(".")[1]: (r.lo, r.hi) for r in r3_hypercircle.defined_ranges(statement) if r.sym.split(".", 2)[2] == part}


def validity(obligation: Obligation, row) -> object:
    (found,) = [v for v in obligation.validity if v.row == row]
    return found.statement


class Lowering(unittest.TestCase):
    def test_the_footbridge_lowers_as_drawn(self):
        model = lowered(design(PASS))
        nodes = {n.name: n for n in model.nodes}
        self.assertEqual((nodes["D"].x, nodes["D"].y), (Fraction(3, 2), Fraction(2)), "node D is drawn at (1.5 m, 2 m)")
        self.assertEqual(
            {n: nodes[n].support for n in "ABCDE"},
            {"A": truss.Support.PINNED, "B": truss.Support.FREE, "C": truss.Support.ROLLER_X, "D": truss.Support.FREE, "E": truss.Support.FREE},
        )
        sections = {m.name: m.section for m in model.members}
        self.assertEqual(sections.pop("top_de"), "chs.76_1x3_2", "the top chord overrides the default section")
        self.assertEqual(set(sections.values()), {"chs.60_3x3_2"})
        self.assertEqual({m.material for m in model.members}, {"steel.S355"})

    def test_malformed_trusses_are_refused(self):
        cases = [
            (("member diag_ad:   A -- D", "member diag_ad:   A -- Z"), "member diag_ad names unknown node Z"),
            (("  member diag_ec:   E -- C\n", "  member diag_ec:   E -- C\n  node F at (9 m, 0 m)\n"), "node F has no member"),
            (("node E at (4.5 m, 2 m)", "node E at (1.5 m, 2 m)"), "member top_de has zero length"),
            (("node D at (1.5 m, 2 m)", "node D at (1.5 m, 2 kN)"), "node D: coordinates must be exact lengths"),
            (("node B at (3 m, 0 m)", "node B at (3 m, 0 m)\n  node B at (3 m, 1 m)"), "node B is declared twice"),
            (("support roller_x", "support hinged"), "unknown support hinged"),
            (("section chs.60_3x3_2", "section cable.cu_pvc_2_5"), "cable.cu_pvc_2_5 is a cable, not a section"),
            (("material steel.S355", "material stainless.A4"), "stainless.A4 is not a structural material: it has no fy, E"),
            (("on frame.D fy", "on frame.D fz"), "a truss node takes fx and fy"),
            (("on frame.D fy", "on frame.Q fy"), "frame.Q, which is not a node of frame"),
            (("frame.member(diag_ad).stress", "frame.member(nope).stress"), "stress is claimed on frame.member(<member>)"),
            (("collapse_factor >= 1.5 under", "collapse_factor >= 1.5 kN under"), "collapse_factor is bounded by a dimensionless quantity"),
            (("frame.stability_factor >= 3", "frame.sway <= 3"), "frame has no quantity sway"),
        ]
        for edit, problem in cases:
            with self.subTest(problem=problem):
                with self.assertRaises(ComponentError) as raised:
                    lowered(design(PASS, edit))
                self.assertTrue(any(problem in p for p in raised.exception.problems), raised.exception.problems)


class Statics(unittest.TestCase):
    def test_hand_forces_balance_the_crowd_load(self):
        model = lowered(design(PASS))
        geometry = truss.geometry(model)
        hand = {"bottom_ab": 18, "bottom_bc": 18, "top_de": -18, "diag_ad": -30, "diag_db": 0, "diag_be": 0, "diag_ec": -30}
        lengths = {"bottom_ab": 3, "bottom_bc": 3, "top_de": 3, "diag_ad": Fraction(5, 2), "diag_db": Fraction(5, 2), "diag_be": Fraction(5, 2), "diag_ec": Fraction(5, 2)}
        load = {("D", "y"): -24 * KN, ("E", "y"): -24 * KN}

        def residual(kn: dict) -> list:
            q = [Fraction(kn[m.name] * KN) / lengths[m.name] for m in model.members]
            f = [Fraction(load.get(dof, 0)) for dof in geometry.dofs]
            for i, j, v in geometry.B.entries:
                f[i] -= v * q[j]
            return f

        self.assertEqual(residual(hand), [0] * len(geometry.dofs), "24 kN at D and E: N_ad = N_ec = -30, N_ab = N_bc = 18, N_de = -18 kN")
        self.assertNotEqual(residual({**hand, "diag_ad": 30}), [0] * len(geometry.dofs), "the end diagonal must be in compression")
        self.assertEqual(geometry.length_sq, tuple(Fraction(lengths[m.name]) ** 2 for m in model.members))


class Coverage(unittest.TestCase):
    def test_the_footbridge_owes_ten_obligations(self):
        built = elaborate(design(PASS))
        expected = {
            "frame/truss.plastic_collapse/claim.strength",
            "frame/truss.global_stability/claim.stability",
            "frame.diag_ad/truss.elastic_stress/claim.stress",
            *(f"frame.{m}/truss.member_buckling/coverage.truss.axial_member" for m in ("bottom_ab", "bottom_bc", "top_de", "diag_ad", "diag_db", "diag_be", "diag_ec")),
        }
        self.assertEqual(set(built), expected, "the claims settle the default collapse and stability coverage")
        self.assertTrue(all(len(out) == 1 and isinstance(out[0], Obligation) for out in built.values()), "one load case, one obligation each")

    def test_a_weaker_claim_leaves_the_default_coverage_in_place(self):
        built = elaborate(design(PASS, ("collapse_factor >= 1.5", "collapse_factor >= 0.5")))
        self.assertIn("frame/truss.plastic_collapse/coverage.truss.frame", built, "a claimed 0.5 does not settle the default 1")

    def test_every_load_case_gets_its_own_obligation(self):
        wind = 'load wind {\n  on frame.E fx in [-5 kN, 5 kN]\n  signed "client.structures@example.org" source "wind study"\n}\n\nclaim strength'
        built = elaborate(design(PASS, ("claim strength", wind)))
        self.assertEqual(len(built["frame.diag_ad/truss.member_buckling/coverage.truss.axial_member"]), 2, "crowd and wind")
        self.assertEqual(len(built["frame/truss.plastic_collapse/claim.strength"]), 1, "the claim names crowd only")


class Footbridge(unittest.TestCase):
    """examples/truss_pass.petra: 16 to 24 kN at D and E."""

    @classmethod
    def setUpClass(cls):
        cls.design = design(PASS)
        cls.built = elaborate(cls.design)

    def statement(self, requirement: str):
        (obligation,) = self.built[requirement]
        return obligation.statement

    def test_every_obligation_is_a_theorem(self):
        for requirement, (obligation,) in self.built.items():
            with self.subTest(requirement=requirement):
                result = decide(obligation.statement)
                self.assertIsInstance(result, Theorem, getattr(result, "reason", ""))
                self.assertEqual(result.statement, obligation.statement)

    def test_premise_numbers_enter_as_labelled_hypotheses(self):
        result = decide(self.statement("frame/truss.plastic_collapse/claim.strength"))
        for label in (
            "reg:steel.S355.fy",
            "reg:const.steel.E",
            "reg:const.en10219_2.60_3x3_2.D",
            "reg:const.en10219_2.76_1x3_2.t",
            "in:warren-footbridge-panel.crowd.frame.D.fy",
            "dsg:warren-footbridge-panel.frame.D.x",
            "reg:const.steel.density",
            "reg:const.earth.gravity",
        ):
            self.assertIn(label, result.labels)

    def test_the_weight_enters_through_unit_loads_at_the_free_y_dofs(self):
        """B, D and E move in y; A and C carry their share straight into the supports."""
        statement = self.statement("frame/truss.global_stability/claim.stability")
        for node, hand in (("B", Fraction(-5, 8)), ("D", Fraction(-15, 16)), ("E", Fraction(-5, 16))):
            with self.subTest(node=node):
                lo, hi = forces(statement, f"N_per_down.{node}")["diag_ad"]
                self.assertTrue(lo <= hand <= hi and hi - lo < Fraction(1, 10**6), f"diag_ad per newton down at {node}: {hand}, lemma [{lo}, {hi}]")
        self.assertFalse(forces(statement, "N_per_down.A"), "a node restrained in y takes no unit load")

    def test_the_buckling_check_carries_the_weight_and_its_gradient(self):
        """diag_ad at 24 kN: 30 kN of load, 405.2 N of weight and 45.2 N along the member at the
        registry's top density, against N_c = 53.979 kN with the self-weight bending (6.3.3)."""
        found = solved(claimed(design(PASS + "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.565 under crowd\n"), "slender").statement)
        self.assertIsInstance(found, Theorem, "30.450 kN / 53.979 kN = 0.5641")
        found = solved(claimed(design(PASS + "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.563 under crowd\n"), "slender").statement)
        self.assertIsInstance(found, Refutation, "30.450 kN against 0.563 x 53.979 kN = 30.390 kN; without the weight 30 kN would pass")

    def test_lemma_ranges_hold_the_hand_forces(self):
        found = forces(self.statement("frame/truss.global_stability/claim.stability"))
        hand = {
            "diag_ad": (-30, -20), "diag_ec": (-30, -20), "bottom_ab": (12, 18), "bottom_bc": (12, 18),
            "top_de": (-18, -12), "diag_db": (-2.5, 2.5), "diag_be": (-2.5, 2.5),
        }
        for member, (lo, hi) in hand.items():
            got = found[member]
            self.assertTrue(got[0] <= lo * KN and hi * KN <= got[1], f"{member}: statics gives [{lo}, {hi}] kN over the load box, lemma {got}")
            self.assertLess(got[1] - got[0], (hi - lo) * KN + 1, f"{member}: a determinate truss's forces do not depend on E, so the range stays tight")

    def test_an_answer_off_equilibrium_is_rejected(self):
        statement = self.statement("frame/truss.plastic_collapse/claim.strength")
        (evidence,) = r1_linear.solve(statement)
        x = evidence.body.x
        nudged = Evidence(FeasiblePoints(((x[0][0] + Fraction(1, 10**6), *x[0][1:]), *x[1:])))
        result = check(statement, nudged)
        self.assertIsInstance(result, Rejection)
        self.assertIn("A x != b", result.reason)

    def test_a_field_off_equilibrium_is_rejected(self):
        statement = self.statement("frame.diag_ad/truss.elastic_stress/claim.stress")
        (evidence,) = [e for e in candidates(statement) if isinstance(check(statement, e), Theorem)]
        first, *rest = evidence.defined
        s = ((first.proof.s[0][0] + Fraction(1, 1000), *first.proof.s[0][1:]), *first.proof.s[1:])
        nudged = dataclasses.replace(first, proof=HypercircleFields(s, first.proof.u))
        result = check(statement, Evidence(evidence.body, (nudged, *rest)))
        self.assertIsInstance(result, Rejection)
        self.assertIn("B s != f", result.reason)

    def test_a_reference_weight_above_its_lower_bound_is_rejected(self):
        statement = self.statement("frame/truss.global_stability/claim.stability")
        (evidence,) = r2_definite.solve(statement)
        weights = evidence.body.reference_weights
        raised = dataclasses.replace(evidence.body, reference_weights=(weights[0] + 1, *weights[1:]))
        result = check(statement, Evidence(raised, evidence.defined))
        self.assertIsInstance(result, Rejection)
        self.assertIn("above the weight's lower bound", result.reason)

    def test_a_too_strict_stress_claim_is_refuted(self):
        obligation = claimed(design(PASS, ("stress <= 235 MPa", "stress <= 40 MPa")), "stress")
        result = decide(obligation.statement)
        self.assertIsInstance(result, Refutation, "diag_ad at 24 kN: 30 kN / 574.0 mm2 = 52.3 MPa > 40 MPa")

    def test_the_stress_claim_reads_the_weight_and_the_bending_it_causes(self):
        """diag_ad at 24 kN: (30 kN + 397.1 N + 44.3 N) / 574.03 mm2 = 53.03 MPa axial, plus
        M / W_el, M = 44.34 N/m x 1.5 m x 2.5 m / 8 = 20.78 N m, W_el = 2 I / D = 7.784 cm3:
        2.67 MPa. 55.70 MPa in all."""
        held = decide(claimed(design(PASS, ("stress <= 235 MPa", "stress <= 55.8 MPa")), "stress").statement)
        self.assertIsInstance(held, Theorem, "55.70 MPa <= 55.8 MPa")
        broken = decide(claimed(design(PASS, ("stress <= 235 MPa", "stress <= 55.6 MPa")), "stress").statement)
        self.assertIsInstance(broken, Refutation, "55.70 MPa > 55.6 MPa")

    def test_a_too_strict_buckling_claim_is_not_proved(self):
        slender = "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.5 under crowd\n"
        obligation = claimed(design(PASS + slender), "slender")
        result = decide(obligation.statement)
        self.assertIsInstance(result, Refutation, "diag_ad: 30.45 kN / 53.98 kN = 0.564 > 0.5")

    def test_a_generous_buckling_claim_is_proved(self):
        slender = "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.57 under crowd\n"
        result = decide(claimed(design(PASS + slender), "slender").statement)
        self.assertIsInstance(result, Theorem, "diag_ad: 30.45 kN / 53.98 kN = 0.564 <= 0.57")

    def test_the_bare_euler_load_would_have_passed_a_claim_the_buckling_curve_refutes(self):
        slender = "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.41 under crowd\n"
        result = solved(claimed(design(PASS + slender), "slender").statement)
        self.assertIsInstance(result, Refutation, "30 kN / 74.12 kN = 0.405 passed the bare Euler load; 30.45 / 53.98 = 0.564 > 0.41")

    def test_the_footbridge_is_statically_determinate(self):
        strength = claimed(design(PASS), "strength")
        self.assertIsInstance(solved(validity(strength, truss.NO_SELF_STRESS)), Theorem, "7 free DOFs, 7 members, B invertible")


class Overload(unittest.TestCase):
    """examples/truss_fail.petra: 40 to 60 kN at D and E."""

    def test_collapse_is_refuted_by_a_mechanism(self):
        obligation = claimed(design(FAIL), "strength")
        result = decide(obligation.statement)
        self.assertIsInstance(result, Refutation, "diag_ad needs 1.5 x 1.25 x 60 = 112.5 kN against a 53.98 kN compression resistance")
        self.assertEqual(result.statement, obligation.statement)

    def test_the_footbridge_load_admits_no_mechanism(self):
        (ray,) = r1_linear.solve(claimed(design(FAIL), "strength").statement)
        light = claimed(design(PASS), "strength").statement
        point = tuple((sym, Fraction(-24 * KN) if sym.startswith("crowd.") else value) for sym, value in ray.body.point)
        result = check(light, Evidence(FarkasRay(point, ray.body.y)))
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, TooWeak, "at 1.5 x 24 kN diag_ad needs 45 kN, inside 53.98 kN, so a static field exists")

    def test_the_end_diagonals_buckle_under_the_heaviest_crowd_on_the_softest_steel(self):
        hand = "N_ad = N_ec = 0.9375 (-60) + 0.3125 (-60) = -75 kN, past the 53.98 kN compression resistance at E = 200 GPa"
        heavy = design(FAIL)
        for member in ("diag_ad", "diag_ec"):
            with self.subTest(member=member):
                result = solved(buckling(heavy, member))
                self.assertIsInstance(result, Refutation, hand)
                point = dict(result.point)
                self.assertEqual((point["crowd.frame.D.fy"], point["crowd.frame.E.fy"], point["const.steel.E"]), (-60 * KN, -60 * KN, 200 * 10 ** 9), hand)

    def test_the_lighter_crowd_and_the_top_chord_do_not_buckle(self):
        self.assertIsInstance(solved(buckling(design(PASS), "diag_ad")), Theorem, "N_ad = 1.25 (-24) = -30 kN, inside 53.98 kN")
        self.assertIsInstance(solved(buckling(design(FAIL), "top_de")), Theorem, "N_de = 0.375 (-120) = -45 kN, inside 75.16 kN")


class Mechanism(unittest.TestCase):
    """The footbridge without diag_be: 6 members over 7 free DOFs, a mechanism."""

    def test_a_mechanism_has_no_self_stress_and_does_not_pass(self):
        text = PASS.replace("  member diag_be:   B -- E\n", "")
        self.assertNotEqual(text, PASS)
        strength = claimed(design(text), "strength")
        self.assertIsInstance(solved(validity(strength, truss.NO_SELF_STRESS)), Theorem, "6 independent members, no self-stress")
        verdict = check_design(design(text), REGISTRY, (SolverSource(),))
        self.assertNotIsInstance(verdict.verdict, Pass, "a mechanism is refused by collapse or by global stability")


class Hanger(unittest.TestCase):
    """Statically indeterminate: see HANGER."""

    def test_forces_follow_compatibility(self):
        found = forces(claimed(design(HANGER), "stability").statement)
        for member, share in (("middle", Fraction(125, 253)), ("left", Fraction(80, 253)), ("right", Fraction(80, 253))):
            lo, hi = share * 80 * KN, share * 100 * KN
            got = found[member]
            self.assertTrue(got[0] <= lo and hi <= got[1], f"{member}: N = {share} P over P in [80, 100] kN is [{float(lo):.1f}, {float(hi):.1f}] N, lemma {got}")
            self.assertLess(got[1] - got[0], hi - lo + 1, f"{member}: one modulus cancels from the weights, so the hypercircle stays tight")

    def test_every_obligation_is_a_theorem(self):
        for requirement, (obligation,) in elaborate(design(HANGER)).items():
            with self.subTest(requirement=requirement):
                self.assertIsInstance(decide(obligation.statement), Theorem)

    def test_collapse_past_the_three_bar_mechanism_is_refuted(self):
        hand = ("all three bars yield: the middle one at A fy less the 70 N its weight varies along it, 160.88 kN; "
                "each 5 m side also gives up its self-weight bending, A M / W_el = 6.21 kN (M = 65.66 N m, "
                "W_el = 4.797 cm3), so 154.67 kN. P_c = 160.88 + 2 x 0.8 x 154.67 = 408.35 kN, less the 0.245 kN "
                "of weight at D: a factor of 4.081 on 100 kN")
        held = decide(claimed(design(HANGER, ("collapse_factor >= 4", "collapse_factor >= 4.07")), "strength").statement)
        self.assertIsInstance(held, Theorem, f"{hand} >= 4.07")
        broken = decide(claimed(design(HANGER, ("collapse_factor >= 4", "collapse_factor >= 4.1")), "strength").statement)
        self.assertIsInstance(broken, Refutation, f"{hand} < 4.1")

    def test_an_indeterminate_truss_is_outside_the_plastic_model(self):
        """The plastic model's static field is the truss's own only when equilibrium fixes it:
        here 2 free DOFs hold 3 members, so a state of self-stress exists. The exact LDL^T
        of B^T B stops at its third pivot, and the direction there refutes the row."""
        strength = claimed(design(HANGER), "strength")
        row = solved(validity(strength, truss.NO_SELF_STRESS))
        self.assertIsInstance(row, Refutation)
        verdict = check_design(design(HANGER), REGISTRY, (SolverSource(),))
        (entry,) = [e for e in verdict.entries if e.claim == "strength"]
        self.assertIsInstance(entry.verdict, Unknown, "the claim statement is proved, but on a model used outside its range")
        (item,) = entry.verdict.open
        self.assertTrue(any(isinstance(n, OutsideValidity) and n.row == truss.NO_SELF_STRESS.id for n in item.needs))

    def test_compliance_takes_the_softest_modulus(self):
        hand = ("C = P^2 / k, k = E A (1/4 + 2 x 0.8^2 / 5) = 253 E A / 500: 217.9 J at P = 100 kN, E = 200 GPa, "
                "A = 453.4 mm2; with the 245.2 N of weight at D, 219.0 J")
        held = decide(claimed(design(HANGER + "claim stiffness: frame.compliance <= 220 J under hang\n"), "stiffness").statement)
        self.assertIsInstance(held, Theorem, f"{hand} <= 220 J")
        broken = decide(claimed(design(HANGER + "claim stiffness: frame.compliance <= 210 J under hang\n"), "stiffness").statement)
        self.assertIsInstance(broken, Refutation, f"{hand} > 210 J, though only 208.6 J at E = 210 GPa")


class SelfWeight(unittest.TestCase):
    """judges/canaries/truss_600m_span.petra: the footbridge scaled by 100 under 1 to 2 N."""

    @classmethod
    def setUpClass(cls):
        cls.design = design((Path(__file__).resolve().parents[1] / "judges" / "canaries" / "truss_600m_span.petra").read_text(encoding="utf-8"))

    def test_a_truss_that_cannot_carry_its_own_weight_fails_collapse(self):
        """250 m diagonals of CHS 60.3x3.2 weigh 11.1 kN each, and N_ad(weight) = 39.7 kN of
        compression against a buckling resistance of 7.4 N: no static field carries the
        weight even alone."""
        result = solved(claimed(self.design, "strength").statement)
        self.assertIsInstance(result, Refutation)

    def test_the_end_diagonals_buckle_under_their_own_weight(self):
        result = solved(buckling(self.design, "diag_ad"))
        self.assertIsInstance(result, Refutation, "39.7 kN of compression against 7.4 N")

    def test_the_weight_alone_is_a_load_case_of_the_collapse_claim(self):
        """An upward load can relieve the weight's compression at the claimed factor and not
        at factor 0: the goal states both copies of the system, so it reads the weight alone."""
        goal = claimed(design(PASS), "strength").statement.goal
        rows = truss.geometry(lowered(design(PASS))).B.rows
        self.assertEqual(goal.A.rows, 2 * rows)
        self.assertTrue(all(isinstance(b, Const) and b.value == 0 for b in goal.b[rows:]), "the second copy carries no load")


class SelfWeightBending(unittest.TestCase):
    """G1: the 6 m chord at the load Petra passed before its buckling resistance met its own
    weight's bending."""

    def test_the_chord_fails_where_its_bending_lowers_its_buckling_resistance(self):
        result = decide(claimed(design(G1.format(p="1.0231")), "strength").statement)
        self.assertIsInstance(result, Refutation, "1.5 x 2 x 1.0231 + 2.721 = 5.790 kN against the 4.919 kN that 6.3.3 leaves")

    def test_the_failure_names_the_chord_and_the_interaction(self):
        report = check_design(design(G1.format(p="1.0231")), REGISTRY, (SolverSource(),))
        self.assertEqual(type(report.verdict), Fail)
        (collapse,) = [f for f in report.findings if f.requirement == "frame/truss.plastic_collapse/claim.strength"]
        self.assertIn("top_de", collapse.governing.what)
        self.assertIn("6.3.3", collapse.governing.what)

    def test_the_claim_holds_up_to_the_hand_limit(self):
        self.assertIsInstance(decide(claimed(design(G1.format(p="0.73")), "strength").statement), Theorem, "0.73 kN < 0.733 kN")
        self.assertIsInstance(decide(claimed(design(G1.format(p="0.74")), "strength").statement), Refutation, "0.74 kN > 0.733 kN")


class Solvers(unittest.TestCase):
    """The two solver cases the self-weight and the determinacy row reach."""

    def test_r1_refutes_bounds_that_cross(self):
        """x = 0 with 2 <= x <= 1: the alternative LP would run unbounded along both
        bounds at once, which the kernel does not credit; a pinned coordinate gives the
        ray y = -1, whose cap 2 x (-1) = -2 lies below y^T b = 0."""
        statement = Statement((), LinearFeasible(Matrix(1, 1, ((0, 0, Fraction(1)),)), (Const(Fraction(0)),),
                                                 (Const(Fraction(2)),), (Const(Fraction(1)),)))
        (ray,) = r1_linear.solve(statement)
        self.assertIsInstance(ray.body, FarkasRay)
        self.assertIsInstance(check(statement, ray), Refutation)

    def test_r2_stops_where_the_exact_ldl_meets_a_zero_pivot(self):
        """[[1, 1], [1, 1]]: d_0 = 1, L_10 = 1, d_1 = 0, so v = L^-T e_1 = (-1, 1) and v^T M v = 0."""
        self.assertEqual(r2_definite.stop_direction({(0, 0): 1, (0, 1): 1, (1, 1): 1}, 2), (Fraction(-1), Fraction(1)))
        self.assertIsNone(r2_definite.stop_direction({(0, 0): 2, (0, 1): 1, (1, 1): 2}, 2), "positive definite")


class Gaps(unittest.TestCase):
    def test_bounds_v0_cannot_state_are_gaps(self):
        edits = [
            ("collapse_factor >= 1.5", "collapse_factor <= 2"),
            ("stability_factor >= 3", "stability_factor <= 3"),
            ("stress <= 235 MPa", "stress >= 1 MPa"),
        ]
        for edit in edits:
            with self.subTest(edit=edit[1]):
                (out,) = [out for rid, out in elaborate(design(PASS, edit)).items() if "/claim." in rid and isinstance(out[0], Gap)]
                self.assertIsInstance(out[0].needs[0], NoRuleForQuantity)

    def test_an_unloaded_truss_needs_a_signed_load(self):
        unloaded = PASS.split("load crowd")[0]
        built = elaborate(design(unloaded))
        self.assertTrue(built, "coverage still demands every mode")
        for requirement, (out,) in built.items():
            with self.subTest(requirement=requirement):
                self.assertEqual(out, Gap(out.requirement, (NeedsInputBound(("frame",), "load", "N"),)))

    def test_a_loaded_truss_has_no_gap(self):
        self.assertFalse([o for out in elaborate(design(PASS)).values() for o in out if isinstance(o, Gap)])


class Models(unittest.TestCase):
    def test_compression_capacity_is_the_en_1993_buckling_resistance(self):
        for mode in (truss.MEMBER_BUCKLING, truss.PLASTIC_COLLAPSE):
            with self.subTest(mode=mode.id):
                premise = truss.MODELS[mode].premise()
                self.assertIn("EN 1993-1-1", premise.source)
                self.assertIn("chi A fy", premise.statement)
                self.assertIn("6.3.3 with Annex B", premise.statement, "the self-weight bending lowers the resistance")
                self.assertIn("Annex B", premise.source)
                self.assertIn(truss.SECTION_CLASS, truss.MODELS[mode].rows, "chi A fy needs a section that reaches A fy")

    def test_no_premise_discloses_the_closed_bending_gap(self):
        """Gap G1 of docs/keystone_protocol.md: the premises once said the bending's effect on
        buckling was not checked. It is checked now, so none may say so."""
        for mode, spec in truss.MODELS.items():
            with self.subTest(mode=mode.id):
                self.assertNotIn("not checked", spec.premise().statement)

    def test_models_on_elastic_forces_check_the_elastic_rows(self):
        for mode in (truss.ELASTIC_STRESS, truss.COMPLIANCE, truss.GLOBAL_STABILITY, truss.MEMBER_BUCKLING):
            with self.subTest(mode=mode.id):
                self.assertEqual(truss.MODELS[mode].rows[:2], (truss.BELOW_YIELD, truss.SMALL_STRAIN))

    def test_the_plastic_model_holds_only_for_a_determinate_truss(self):
        self.assertIn(truss.NO_SELF_STRESS, truss.MODELS[truss.PLASTIC_COLLAPSE].rows)
        self.assertNotIn("indeterminate truss may exceed", truss.MODELS[truss.PLASTIC_COLLAPSE].premise().statement)

    def test_every_premise_states_gravity_and_the_models_on_buckling_state_the_bracing(self):
        for mode, spec in truss.MODELS.items():
            with self.subTest(mode=mode.id):
                self.assertIn("gravity acts in -y", spec.premise().statement)
        for mode in (truss.PLASTIC_COLLAPSE, truss.MEMBER_BUCKLING):
            with self.subTest(mode=mode.id):
                self.assertIn("buckling length about every axis is its length L", truss.MODELS[mode].premise().statement)

    def test_every_built_mode_rests_on_a_model_premise(self):
        self.assertEqual(set(truss.MODELS), set(truss.DOMAIN.builders))
        self.assertTrue(all(spec.premise().label.startswith(f"model:{spec.id}@") for spec in truss.MODELS.values()))


if __name__ == "__main__":
    unittest.main()
