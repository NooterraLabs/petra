"""Pin-jointed trusses from .lola text to kernel results. Owner: T.

Statements are built from the lowered example IR, evidence comes from the truss solvers
(R1, R2, R3; R4 buckling uses a one-leaf Enclosure with the R3 lemma ranges), and the
kernel decides. Expected forces and margins are hand statics, kept in the messages.

Hand values used throughout, steel E in [200, 210] GPa, fy = 355 MPa:
  CHS 60.3x3.2  A = pi/4 (60.3^2 - 53.9^2) = 574.0 mm2,  I = pi/64 (60.3^4 - 53.9^4) = 23.47 cm4
  CHS 48.3x3.2  A = pi/4 (48.3^2 - 41.9^2) = 453.4 mm2,  A fy = 160.95 kN
  Euler load of a 2.5 m CHS 60.3x3.2 diagonal at E = 200 GPa: pi^2 E I / L^2 = 74.12 kN
Footbridge statics (P_D, P_E node loads, downward negative):
  N_ad = 0.9375 P_D + 0.3125 P_E    N_ec = 0.3125 P_D + 0.9375 P_E
  N_ab = 0.75 (0.75 P_D + 0.25 P_E) N_de = 0.375 (P_D + P_E)    N_db = -N_be = 0.3125 (P_D - P_E)
"""
import dataclasses
import unittest
from fractions import Fraction
from pathlib import Path

from lola import coverage
from lola.ir import Design
from lola.kernel import Evidence, Leaf, Refutation, Rejection, Theorem, TooWeak, check, is_issued
from lola.kernel.rules.r1_linear import FarkasRay, FeasiblePoints, LinearFeasible
from lola.kernel.rules.r2_definite import GramPositiveDefinite, LDLFactor
from lola.kernel.rules.r3_hypercircle import Hypercircle, HypercircleFields, MinimizerBound
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure
from lola.lang import parse_design
from lola.models import truss
from lola.models.base import ClaimOrigin, ComponentError, Gap, NeedsInputBound, NoRuleForQuantity, Obligation
from lola.registry import build_registry
from lola.solvers import r1_linear, r2_definite, r3_hypercircle

REGISTRY = build_registry()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
PASS = (EXAMPLES / "truss_pass.lola").read_text(encoding="utf-8")
FAIL = (EXAMPLES / "truss_fail.lola").read_text(encoding="utf-8")
KN = 1000

HANGER = """lola 0

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
(0.8/5) = 25/16, and N_m + 2 (0.8) N_s = P gives N_m = 125 P / 253, N_s = 80 P / 253."""

SOLVERS = {LinearFeasible: r1_linear.solve, GramPositiveDefinite: r2_definite.solve, MinimizerBound: r3_hypercircle.solve}


def design(text: str, *edits: tuple[str, str]) -> Design:
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"edit target {old!r} is not in the text")
        text = text.replace(old, new)
    return parse_design(text, "t.lola", REGISTRY)


def lowered(d: Design) -> truss.Truss:
    return truss.lower_truss(d.components["frame"], d, REGISTRY)


def elaborate(d: Design) -> dict[str, tuple]:
    """Requirement id -> what the truss builder made of it, for every requirement."""
    model = lowered(d)
    return {req.id: truss.DOMAIN.builders[req.mode](req, model, d, REGISTRY) for req in coverage.generate(d, {"frame": model}, REGISTRY)}


def candidates(statement) -> list[Evidence]:
    if isinstance(statement.goal, AllNonpositive):
        return [Evidence(Enclosure(Leaf()), r3_hypercircle.defined_ranges(statement))]
    return list(SOLVERS[type(statement.goal)](statement))


def decide(statement):
    """The first issued result over the solver's candidates, else the last rejection."""
    result = None
    for evidence in candidates(statement):
        result = check(statement, evidence)
        if is_issued(result):
            return result
    return result


def claimed(d: Design, claim: str) -> Obligation:
    (found,) = [o for out in elaborate(d).values() for o in out if o.requirement.origin == ClaimOrigin(claim)]
    return found


def forces(statement) -> dict[str, tuple[Fraction, Fraction]]:
    """Member name -> the R3 lemma range the solver proposes for its force, in newtons."""
    return {r.sym.split(".")[1]: (r.lo, r.hi) for r in r3_hypercircle.defined_ranges(statement)}


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
    def test_the_footbridge_owes_eleven_obligations(self):
        built = elaborate(design(PASS))
        expected = {
            "frame/truss.plastic_collapse/claim.strength",
            "frame/truss.global_stability/claim.stability",
            "frame.diag_ad/truss.elastic_stress/claim.stress",
            "frame/truss.small_strain/coverage.truss.frame",
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
    """examples/truss_pass.lola: 16 to 24 kN at D and E."""

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
        ):
            self.assertIn(label, result.labels)

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
        evidence = next(iter(r3_hypercircle.solve(statement)))
        fields = evidence.body.fields
        s = ((fields.s[0][0] + Fraction(1, 1000), *fields.s[0][1:]), *fields.s[1:])
        result = check(statement, Evidence(Hypercircle(HypercircleFields(s, fields.u))))
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

    def test_a_too_strict_buckling_claim_is_not_proved(self):
        slender = "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.3 under crowd\n"
        obligation = claimed(design(PASS + slender), "slender")
        result = decide(obligation.statement)
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, TooWeak, "diag_ad: 30 kN / 74.12 kN = 0.405 > 0.3")

    def test_a_generous_buckling_claim_is_proved(self):
        slender = "claim slender: frame.member(diag_ad).buckling_utilisation <= 0.41 under crowd\n"
        result = decide(claimed(design(PASS + slender), "slender").statement)
        self.assertIsInstance(result, Theorem, "diag_ad: 30 kN / 74.12 kN = 0.405 <= 0.41")


class Overload(unittest.TestCase):
    """examples/truss_fail.lola: 40 to 60 kN at D and E."""

    def test_collapse_is_refuted_by_a_mechanism(self):
        obligation = claimed(design(FAIL), "strength")
        result = decide(obligation.statement)
        self.assertIsInstance(result, Refutation, "diag_ad needs 1.5 x 1.25 x 60 = 112.5 kN against a 74.12 kN Euler load")
        self.assertEqual(result.statement, obligation.statement)

    def test_the_footbridge_load_admits_no_mechanism(self):
        (ray,) = r1_linear.solve(claimed(design(FAIL), "strength").statement)
        light = claimed(design(PASS), "strength").statement
        point = tuple((sym, Fraction(-24 * KN) if sym.startswith("crowd.") else value) for sym, value in ray.body.point)
        result = check(light, Evidence(FarkasRay(point, ray.body.y)))
        self.assertIsInstance(result, Rejection)
        self.assertIsInstance(result.fault, TooWeak, "at 1.5 x 24 kN diag_ad needs 45 kN, inside 74.12 kN, so a static field exists")


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
        hand = "all three bars yield at A fy = 160.95 kN: P_c = 160.95 (1 + 2 x 0.8) = 418.5 kN"
        held = decide(claimed(design(HANGER, ("collapse_factor >= 4", "collapse_factor >= 4.15")), "strength").statement)
        self.assertIsInstance(held, Theorem, f"{hand} >= 4.15 x 100 kN")
        broken = decide(claimed(design(HANGER, ("collapse_factor >= 4", "collapse_factor >= 4.2")), "strength").statement)
        self.assertIsInstance(broken, Refutation, f"{hand} < 4.2 x 100 kN")

    def test_compliance_takes_the_softest_modulus(self):
        hand = "C = P^2 / k, k = E A (1/4 + 2 x 0.8^2 / 5) = 253 E A / 500: 217.9 J at P = 100 kN, E = 200 GPa, A = 453.4 mm2"
        held = decide(claimed(design(HANGER + "claim stiffness: frame.compliance <= 220 J under hang\n"), "stiffness").statement)
        self.assertIsInstance(held, Theorem, f"{hand} <= 220 J")
        broken = decide(claimed(design(HANGER + "claim stiffness: frame.compliance <= 210 J under hang\n"), "stiffness").statement)
        self.assertIsInstance(broken, Refutation, f"{hand} > 210 J, though only 207.6 J at E = 210 GPa")


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
    def test_euler_premises_say_no_imperfection_reduction_is_applied(self):
        for mode in (truss.MEMBER_BUCKLING, truss.PLASTIC_COLLAPSE):
            with self.subTest(mode=mode.id):
                self.assertIn("no imperfection reduction", truss.MODELS[mode].premise().statement)

    def test_every_built_mode_rests_on_a_model_premise(self):
        self.assertEqual(set(truss.MODELS), set(truss.DOMAIN.builders))
        self.assertTrue(all(spec.premise().label.startswith(f"model:{spec.id}@") for spec in truss.MODELS.values()))


if __name__ == "__main__":
    unittest.main()
