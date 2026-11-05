"""The strict JSON codec, canonical text and hashes. Owner: K.

The bolt-tension statement is rebuilt by hand from docs/design.md, which states its hash.
"""
import copy
import json
import unittest
from fractions import Fraction as F

from lola.kernel import (
    TAGS,
    Abs,
    Add,
    Const,
    DecodeError,
    DefinedHyp,
    DefinedRange,
    Div,
    Evidence,
    Exp,
    Instance,
    Leaf,
    Ln,
    Matrix,
    Max,
    Min,
    Mul,
    Neg,
    Pi,
    PowInt,
    RangeHyp,
    Split,
    Sqrt,
    Statement,
    Sym,
    canonical_text,
    decode_evidence,
    decode_statement,
    encode_evidence,
    encode_statement,
    evidence_hash,
    statement_hash,
)
from lola.kernel.rules.r1_linear import FarkasRay, FeasiblePoints, LinearFeasible
from lola.kernel.rules.r2_definite import GramPositiveDefinite, GramTerm, LDLFactor, NegativeDirection
from lola.kernel.rules.r3_hypercircle import (
    ComponentBound,
    Hypercircle,
    HypercircleFields,
    HypercircleViolation,
    MinimizerBound,
    MinimizerComponent,
    QuadraticProblem,
)
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure, PointWitness
from lola.kernel.rules.r5_moment import MomentBound, MomentConstraint, MomentDual, RandomVar
from lola.kernel.rules.r6_scenario import Arithmetic, BinomialTail

DESIGN_HASH = "sha256:f7e4f42637918874eba38b225d8fa66cdb692d6dedb2f1b9c20dc5a8e324bc53"


def c(v) -> Const:
    return Const(F(v))


def s(name: str) -> Sym:
    return Sym(name)


def bolt_statement() -> Statement:
    """T/(K d) + phi F - 0.9 Rp02 (pi/4)((d2 + d3)/2)^2 <= 0, as docs/design.md spells it."""
    d2 = Add((s("d"), Neg(Mul((s("c2"), s("P"))))))
    d3 = Add((s("d"), Neg(Mul((s("c3"), s("P"))))))
    stress_area = Mul((Div(Pi(), c(4)), PowInt(Div(Add((d2, d3)), c(2)), 2)))
    margin = Add((Div(s("T"), Mul((s("K"), s("d")))), Mul((s("phi"), s("F"))), Neg(Mul((c(F(9, 10)), s("Rp02"), stress_area)))))
    hyps = (
        RangeHyp("F", F(0), F(12000), "in:mast-bracket-coastal.wind.bracket.force"),
        RangeHyp("K", F(4, 25), F(11, 50), "in:mast-bracket-coastal.bracket.nut_factor"),
        RangeHyp("P", F(7, 4000), F(7, 4000), "reg:const.iso261.M12.pitch"),
        RangeHyp("Rp02", F(450000000), F(450000000), "reg:bolt.M12_A4_70.Rp02_min"),
        RangeHyp("T", F(40), F(50), "in:mast-bracket-coastal.bracket.torque"),
        RangeHyp("c2", F(649519, 1000000), F(649519, 1000000), "reg:const.iso724.d2_coefficient"),
        RangeHyp("c3", F(1226869, 1000000), F(1226869, 1000000), "reg:const.iso724.d3_coefficient"),
        RangeHyp("d", F(3, 250), F(3, 250), "reg:const.iso261.M12.d"),
        RangeHyp("phi", F(1, 10), F(1, 4), "in:mast-bracket-coastal.bracket.load_share"),
    )
    return Statement(hyps=hyps, goal=AllNonpositive(exprs=(margin,)))


BOLT_EVIDENCE = Evidence(body=Enclosure(partition=Split("F", F(6000), Leaf(), Leaf())))
BOLT_EVIDENCE_JSON = {"t": "evidence", "defined": [], "body": {"t": "enclosure", "partition": {"t": "split", "sym": "F", "at": "6000", "left": {"t": "leaf"}, "right": {"t": "leaf"}}}}


def samples() -> tuple[list[Statement], list[Evidence]]:
    """One statement per goal and one evidence per body, together using every tag. The
    last evidence is an Instance of the AllNonpositive statement."""
    every_expr = Add((c(1), s("x"), Pi(), Mul((s("x"), c(F(-1, 2)))), Neg(s("x")), Div(s("x"), c(3)), PowInt(s("x"), 2), Sqrt(s("x")), Ln(s("x")), Exp(s("x")), Abs(s("x")), Min((s("x"), c(0))), Max((s("x"), c(0)))))
    m = Matrix(2, 2, ((0, 0, F(1)), (1, 0, F(-1, 3)), (1, 1, F(1))))
    problem = QuadraticProblem(B=Matrix(1, 2, ((0, 0, F(1)), (0, 1, F(1)))), f=(s("x"),), w=(c(1), c(3)))
    hyps = (RangeHyp("x", F(0), F(1), "in:x"), DefinedHyp("y", MinimizerComponent(problem, 0, c(1))))
    goals = [
        LinearFeasible(A=m, b=(every_expr, c(0)), lower=(None, c(0)), upper=(c(1), None)),
        GramPositiveDefinite(dim=2, terms=(GramTerm(weight=s("x"), factor=m),)),
        MinimizerBound(problem=problem, bounds=(ComponentBound(0, c(1), None, c(2)),), energy_hi=None),
        AllNonpositive(exprs=(every_expr,)),
        MomentBound(random=(RandomVar("u", c(0), s("x")),), moments=(MomentConstraint(s("u"), c(1), c(1)),), fail=s("u"), p=F(1, 3)),
        BinomialTail(n=c(300), k=c(0), eps=c(F(1, 100)), beta=c(F(1, 20))),
    ]
    point = (("x", F(1)),)
    fields = HypercircleFields(s=((F(3), F(1)), (F(6), F(2))), u=((F(3),), (F(6),)))
    bodies = [
        FeasiblePoints(x=((F(1), F(2)),)), FarkasRay(point=point, y=(F(1), F(-1))),
        LDLFactor(reference_weights=(F(1),), L=m, d=(F(3, 4), F(2, 3))), NegativeDirection(point=point, v=(F(1), F(1))),
        Hypercircle(fields=fields), HypercircleViolation(point=point, s=(F(1), F(0)), u=(F(0),), which=-1),
        Enclosure(partition=Split("x", F(1, 2), Leaf(), Leaf())), PointWitness(point=point, which=0),
        MomentDual(y0=F(0), y=(F(1, 36),), partition=Leaf()), Arithmetic(),
    ]
    statements = [Statement(hyps=hyps, goal=g) for g in goals]
    evidences = [Evidence(body=b, defined=(DefinedRange("y", F(0), F(1), fields),)) for b in bodies]
    evidences.append(Evidence(body=Instance(statements[3], evidences[6], (("x", "a"), ("y", "b")))))
    return statements, evidences


def tags_in(obj) -> set:
    if isinstance(obj, dict):
        return {obj.get("t")} | set().union(*map(tags_in, obj.values()))
    if isinstance(obj, list):
        return set().union(*map(tags_in, obj))
    return set()


class RoundTrip(unittest.TestCase):
    def test_bolt_statement_hashes_as_the_design_states(self):
        self.assertEqual(statement_hash(bolt_statement()), DESIGN_HASH)

    def test_bolt_evidence_matches_the_design_json(self):
        self.assertEqual(encode_evidence(BOLT_EVIDENCE), BOLT_EVIDENCE_JSON)
        self.assertEqual(decode_evidence(BOLT_EVIDENCE_JSON), BOLT_EVIDENCE)

    def test_every_term_class_round_trips(self):
        statements, evidences = samples()
        seen = set()
        for st in statements:
            obj = json.loads(canonical_text(encode_statement(st)))
            self.assertEqual(decode_statement(obj), st)
            seen |= tags_in(obj)
        for ev in evidences:
            obj = json.loads(canonical_text(encode_evidence(ev)))
            self.assertEqual(decode_evidence(obj), ev)
            seen |= tags_in(obj)
        self.assertEqual(seen, set(TAGS), "the samples use every tag")

    def test_hashes_are_canonical_and_sensitive(self):
        st = bolt_statement()
        self.assertRegex(statement_hash(st), r"^sha256:[0-9a-f]{64}$")
        moved = Statement(hyps=(RangeHyp("F", F(0), F(12001), st.hyps[0].label),) + st.hyps[1:], goal=st.goal)
        self.assertNotEqual(statement_hash(moved), statement_hash(st))
        self.assertNotEqual(evidence_hash(BOLT_EVIDENCE), evidence_hash(Evidence(body=Enclosure(partition=Leaf()))))

    def test_canonical_text(self):
        self.assertEqual(canonical_text({"b": [1, None], "a": "é"}), '{"a":"\\u00e9","b":[1,null]}')


class Strictness(unittest.TestCase):
    def assertRefused(self, edit, decode=decode_statement, base=None):
        obj = copy.deepcopy(base if base is not None else encode_statement(bolt_statement()))
        edit(obj)
        with self.assertRaises(DecodeError):
            decode(obj)

    def test_non_canonical_rationals(self):
        for spelling in ["24000/2", "12000.0", "1.2e4", "+12000", " 12000", 12000, 12000.0, None]:
            self.assertRefused(lambda o, v=spelling: o["hyps"][0].update(hi=v))

    def test_unknown_missing_and_misplaced_terms(self):
        edits = [
            lambda o: o["hyps"][0].update(unit="N"),
            lambda o: o["hyps"][0].pop("label"),
            lambda o: o["goal"]["exprs"][0].update(t="add_all"),
            lambda o: o["goal"]["exprs"].__setitem__(0, {"t": "all_nonpositive", "exprs": []}),
            lambda o: o.update(goal={"t": "const", "value": "1"}),
            lambda o: o["hyps"].__setitem__(0, ["range_hyp", "F"]),
            lambda o: o.update(hyps={"t": "range_hyp"}),
            lambda o: o.pop("t"),
        ]
        for edit in edits:
            self.assertRefused(edit)

    def test_integers_are_json_integers(self):
        def exponent(o):
            return o["goal"]["exprs"][0]["args"][2]["arg"]["args"][2]["args"][1]

        for value in ["2", 2.0, True]:
            self.assertRefused(lambda o, v=value: exponent(o).update(exponent=v))

    def test_non_canonical_matrices(self):
        base = encode_statement(Statement(hyps=(), goal=GramPositiveDefinite(dim=2, terms=(GramTerm(c(1), Matrix(2, 2, ((0, 0, F(1)), (1, 1, F(1))))),))))
        self.assertEqual(decode_statement(base).goal.terms[0].factor.entries, ((0, 0, F(1)), (1, 1, F(1))))
        for entries in [[[1, 1, "1"], [0, 0, "1"]], [[0, 0, "0"]], [[0, 2, "1"]], [[0, 0, "1"], [0, 0, "2"]], [[-1, 0, "1"]]]:
            self.assertRefused(lambda o, e=entries: o["goal"]["terms"][0]["factor"].update(entries=e), base=base)
        self.assertRefused(lambda o: o["goal"]["terms"][0]["factor"].update(rows=-1, entries=[]), base=base)

    def test_evidence_is_decoded_as_strictly(self):
        for edit in [lambda o: o["body"]["partition"].update(at="6000.5"), lambda o: o["body"].update(t="statement"), lambda o: o.pop("defined")]:
            self.assertRefused(edit, decode=decode_evidence, base=BOLT_EVIDENCE_JSON)

    def test_an_instance_is_decoded_as_strictly(self):
        instance = samples()[1][-1]
        base = encode_evidence(instance)
        self.assertEqual(decode_evidence(base), instance, "the unedited Instance decodes")
        edits = [
            lambda o: o["body"]["renaming"][0].append("c"),
            lambda o: o["body"]["renaming"][0].__setitem__(1, 1),
            lambda o: o["body"].update(renaming={"x": "a"}),
            lambda o: o["body"].pop("renaming"),
            lambda o: o["body"].update(rule="R4"),
            lambda o: o["body"].update(statement=o["body"]["evidence"]),
            lambda o: o["body"]["evidence"].update(t="statement"),
        ]
        for edit in edits:
            self.assertRefused(edit, decode=decode_evidence, base=base)

    def test_encoder_refuses_values_outside_the_term_language(self):
        bad = [
            Statement(hyps=(), goal=AllNonpositive(exprs=(Const(0.5),))),
            Statement(hyps=(RangeHyp("x", True, F(1), "in:x"),), goal=AllNonpositive(exprs=(s("x"),))),
            Statement(hyps=[], goal=AllNonpositive(exprs=())),
        ]
        for st in bad:
            with self.assertRaises(TypeError):
                encode_statement(st)
        with self.assertRaises(TypeError):
            encode_evidence(Enclosure(partition=Leaf()))


if __name__ == "__main__":
    unittest.main()
