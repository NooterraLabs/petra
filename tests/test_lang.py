"""The .petra front end: text -> Design IR, and every rejection the parse boundary owns.
Owner: L."""
import dataclasses
import unittest
from fractions import Fraction
from pathlib import Path

from petra import models
from petra.ir import (
    Attr,
    Bound,
    Claim,
    Design,
    Exceeds,
    FailsAt,
    Fixed,
    FromTests,
    Input,
    InputKind,
    LoadEntry,
    ParamRef,
    ProbabilityClaim,
    Punct,
    QoiRef,
    RangeMean,
    Ref,
    Rel,
    Signature,
    Span,
    Text,
    Vec,
    Waiver,
)
from petra.kernel import Interval
from petra.lang import LolaSyntaxError, LoweringError, load_design, parse_design
from petra.premises import Tag
from petra.registry import Corrosivity, Environment, Registry, Stated
from petra.units import AREA, CURRENT, DIMENSIONLESS, FORCE, LENGTH, STRESS, TEMPERATURE, TORQUE, VOLTAGE, Quantity

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def environments_only(*ids: str) -> Registry:
    """Design-level lowering reads only the registry's environment ids; the domains'
    lowerers read the rest."""
    ambient = Stated(Interval(Fraction(0), Fraction(40)), "degC", Tag.SANCTIONED, "test fixture", "test fixture", "test fixture")
    envs = {e: Environment(e, ambient, Corrosivity.C1, False) for e in ids}
    return Registry(constants={}, materials={}, parts={}, processes={}, environments=envs)


REGISTRY = environments_only("indoor_dry", "outdoor_c3", "marine_c5")

HEADER = 'petra 0\ndesign "d" {\n  owner "o@example.org"\n  environment indoor_dry\n}\n'
HOOK = 'demand hook {\n  capacity in [36 kN, 40 kN] measured "qa@example.org" source "PL-1"\n}\n'
LIFT = 'load lift {\n  on hook force in [0 kN, 40 kN] mean 10 kN\n  signed "ops@example.org" source "duty log"\n}\n'
PROOF = 'tests proof {\n  on hook trials 300 failures 0 at 36 kN\n  measured "qa@example.org" source "batch 9"\n}\n'


def lower_text(body: str, header: str = HEADER) -> Design:
    return parse_design(header + body, "t.petra", REGISTRY)


def q(x, dim) -> Quantity:
    return Quantity(Interval(Fraction(x), Fraction(x)), dim)


def rng(lo, hi, dim) -> Quantity:
    return Quantity(Interval(Fraction(lo), Fraction(hi)), dim)


def unspanned(x):
    return dataclasses.replace(x, span=None)


def attr(design: Design, component: str, key: str, nth: int = 0) -> tuple:
    return [a for a in design.components[component].attrs if a.key == key][nth].args


class Case(unittest.TestCase):
    def assertProblem(self, body: str, line: int, col: int, *fragments: str, header: str = HEADER) -> LoweringError:
        with self.assertRaises(LoweringError) as ctx:
            lower_text(body, header)
        at = [p for p in ctx.exception.problems if p.startswith(f"t.petra:{line}:{col}: ")]
        self.assertTrue(at, f"no problem at {line}:{col} in {ctx.exception.problems}")
        for fragment in fragments:
            self.assertIn(fragment, at[0])
        return ctx.exception

    def assertSyntax(self, text: str, line: int, col: int) -> None:
        with self.assertRaises(LolaSyntaxError) as ctx:
            parse_design(text, "t.petra", REGISTRY)
        self.assertEqual((ctx.exception.path, ctx.exception.line, ctx.exception.col), ("t.petra", line, col), str(ctx.exception))
        self.assertTrue(str(ctx.exception).startswith(f"t.petra:{line}:{col}: "))


class Examples(Case):
    def paths(self) -> list[Path]:
        paths = sorted(EXAMPLES.rglob("*.petra"))
        self.assertTrue(any(p.parent.name == "families" for p in paths), "examples/families is swept too")
        return paths

    def test_every_example_parses_and_lowers_to_ir(self):
        for path in self.paths():
            with self.subTest(example=str(path.relative_to(EXAMPLES))):
                design = load_design(path, REGISTRY)
                self.assertIsInstance(design, Design)
                self.assertEqual(design.path, str(path))
                self.assertTrue(design.name and design.owner)
                self.assertTrue(design.components, "every example draws a component")
                for component in design.components.values():
                    self.assertIn(component.kind, models.KINDS)

    def test_every_example_is_rejected_once_its_component_kind_is_misspelt(self):
        for path in self.paths():
            with self.subTest(example=str(path.relative_to(EXAMPLES))):
                text = path.read_text(encoding="utf-8")
                kind = next(iter(load_design(path, REGISTRY).components.values())).kind
                broken = text.replace(f"\n{kind} ", f"\n{kind}x ", 1)
                self.assertNotEqual(broken, text)
                with self.assertRaises(LoweringError):
                    parse_design(broken, str(path), REGISTRY)

    def test_truss_pass_lowers_to_generic_attributes_and_si_loads(self):
        d = load_design(EXAMPLES / "truss_pass.petra", REGISTRY)
        self.assertEqual((d.name, d.owner, d.environment, d.is_family), ("warren-footbridge-panel", "a.reviewer@example.org", "indoor_dry", False))
        self.assertEqual(d.components["frame"].kind, "truss")
        self.assertEqual(attr(d, "frame", "section"), (Ref(("chs", "60_3x3_2")),))
        self.assertEqual(attr(d, "frame", "node", 3), (Ref(("D",)), Ref(("at",)), Vec((q(Fraction(3, 2), LENGTH), q(2, LENGTH)))))
        self.assertEqual(attr(d, "frame", "node", 0)[3:], (Ref(("support",)), Ref(("pinned",))))
        self.assertEqual(
            attr(d, "frame", "member", 2),
            (Ref(("top_de",)), Punct(":"), Ref(("D",)), Punct("--"), Ref(("E",)), Ref(("section",)), Ref(("chs", "76_1x3_2"))),
        )
        signature = Signature("client.structures@example.org", "brief rev B, section 3.2")
        entry = d.loads["crowd"].entries[0]
        self.assertEqual((entry.target, entry.field), (("frame", "D"), "fy"))
        self.assertEqual(unspanned(entry.value), Input("crowd.frame.D.fy", rng(-24000, -16000, FORCE), signature, InputKind.ASSUMED, None))
        strength, stability, stress = d.claims
        self.assertEqual(unspanned(strength), Claim("strength", QoiRef(("frame",), "collapse_factor"), Rel.GE, q(Fraction(3, 2), DIMENSIONLESS), ("crowd",), None, None))
        self.assertEqual(unspanned(stability).bound, q(3, DIMENSIONLESS))
        self.assertEqual((stress.qoi, stress.rel, stress.bound), (QoiRef(("frame", "diag_ad"), "stress"), Rel.LE, q(235_000_000, STRESS)))

    def test_bolt_unknown_keeps_digit_led_registry_ids_and_measured_bounds(self):
        d = load_design(EXAMPLES / "bolt_unknown.petra", REGISTRY)
        self.assertEqual(d.environment, "marine_c5")
        self.assertEqual(attr(d, "bracket", "bolt"), (Ref(("bolt", "M12_A4_70")), Ref(("count",)), Fixed(q(1, DIMENSIONLESS))))
        self.assertEqual(attr(d, "bracket", "plate"), (Ref(("aluminium", "6061_T6")), Ref(("thickness",)), Fixed(q(Fraction(1, 100), LENGTH))))
        (torque,) = attr(d, "bracket", "torque")
        self.assertEqual(unspanned(torque), Bound(rng(40, 50, TORQUE), Signature("fitter.lead@example.org", "assembly spec AS-12 rev C"), InputKind.ASSUMED, None))
        (nut_factor,) = attr(d, "bracket", "nut_factor")
        self.assertEqual((nut_factor.range, nut_factor.kind), (rng(Fraction(4, 25), Fraction(11, 50), DIMENSIONLESS), InputKind.MEASURED))

    def test_circuit_pass_has_a_signed_ambient_and_port_connections(self):
        d = load_design(EXAMPLES / "circuit_pass.petra", REGISTRY)
        self.assertEqual(
            unspanned(d.ambient),
            Input("ambient", rng(10, 40, TEMPERATURE), Signature("site.manager@example.org", "site survey 2026-09"), InputKind.ASSUMED, None),
        )
        supply = attr(d, "lighting", "supply")
        self.assertEqual(supply[:4], (Ref(("mains",)), Ref(("voltage",)), Fixed(q(230, VOLTAGE)), Ref(("fault_current",))))
        self.assertEqual(supply[4].range, rng(0, 6000, CURRENT))
        self.assertEqual(attr(d, "lighting", "connect", 2), (Ref(("w1", "b")), Punct("->"), Ref(("t1", "wire"))))
        self.assertEqual(attr(d, "lighting", "connect", 0)[2], Ref(("cb1", "in")), "'in' after a dot is a port name, not a bound")
        self.assertEqual(d.claims[1].bound, q(Fraction(3, 100), DIMENSIONLESS))

    def test_hook_uncertain_pairs_each_probability_method_with_its_event(self):
        d = load_design(EXAMPLES / "hook_uncertain.petra", REGISTRY)
        self.assertEqual(d.loads["lift"].entries[0].value.mean, q(10000, FORCE))
        proof = d.tests["proof"]
        self.assertEqual((proof.subject, proof.trials, proof.failures, proof.level), (("hook",), 300, 0, q(36000, FORCE)))
        self.assertEqual(proof.signature, Signature("qa.lab@example.org", "batch 2026-09 proof tests, independent lots"))
        overload, tested = (unspanned(c) for c in d.probability_claims)
        self.assertEqual(overload, ProbabilityClaim("overload", Exceeds(QoiRef(("hook",), "utilisation"), q(1, DIMENSIONLESS), "lift"), Fraction(3, 10), RangeMean(), None))
        self.assertEqual(tested, ProbabilityClaim("tested", FailsAt(("hook",), q(36000, FORCE)), Fraction(1, 100), FromTests("proof", Fraction(19, 20)), None))
        self.assertEqual(d.claims, ())

    def test_the_family_example_is_a_family_of_param_refs(self):
        d = load_design(EXAMPLES / "families" / "cu_pvc_clipped.petra", REGISTRY)
        self.assertTrue(d.is_family)
        self.assertEqual(tuple(d.params), ("size", "insulation", "run", "draw", "amb"))
        self.assertEqual(d.params["size"].range, rng(Fraction(1, 400000), Fraction(1, 62500), AREA))
        self.assertEqual(d.ambient, ParamRef("amb"))
        self.assertEqual(attr(d, "c", "wire")[3:5], (Ref(("area",)), ParamRef("size")))
        self.assertEqual(d.loads["demand"].entries[0], LoadEntry(("c", "load"), "current", ParamRef("draw")))


class Lowering(Case):
    def test_a_component_keeps_its_positions(self):
        d = lower_text(HOOK)
        hook = d.components["hook"]
        self.assertEqual((hook.span, hook.attrs[0].span), (Span("t.petra", 6, 1), Span("t.petra", 7, 3)))
        self.assertEqual(
            hook.attrs[0].args,
            (Bound(rng(36000, 40000, FORCE), Signature("qa@example.org", "PL-1"), InputKind.MEASURED, Span("t.petra", 7, 12)),),
        )

    def test_any_attribute_line_of_a_registered_kind_reaches_its_domain_typed(self):
        d = lower_text('param p in [1 m, 2 m]\ntruss frame {\n  anything 3 kN foo.bar "x y" (1 m, 2 m) : -- -> param p\n}\n')
        self.assertEqual(
            d.components["frame"].attrs,
            (Attr("anything", (Fixed(q(3000, FORCE)), Ref(("foo", "bar")), Text("x y"), Vec((q(1, LENGTH), q(2, LENGTH))), Punct(":"), Punct("--"), Punct("->"), ParamRef("p")), Span("t.petra", 8, 3)),),
        )

    def test_comments_blank_lines_and_bracketed_line_breaks_are_layout(self):
        d = lower_text('# a comment\n\ndemand hook {   # trailing\n\n  capacity in [36 kN,\n      40 kN] measured "qa@example.org" source "PL-1"\n}\n')
        self.assertEqual(d.components["hook"].attrs[0].args[0].range, rng(36000, 40000, FORCE))

    def test_crlf_line_ends_lower_like_lf(self):
        crlf = parse_design((HEADER + HOOK).replace("\n", "\r\n"), "t.petra", REGISTRY)
        self.assertEqual(crlf.components["hook"], lower_text(HOOK).components["hook"])

    def test_string_escapes(self):
        d = lower_text("", header='petra 0\ndesign "d" {\n  owner "a \\"b\\" \\\\ c"\n}\n')
        self.assertEqual(d.owner, 'a "b" \\ c')
        self.assertIsNone(d.environment)

    def test_an_entry_signature_wins_over_its_block_signature(self):
        d = lower_text(HOOK + 'load lift {\n  on hook force in [0 kN, 1 kN] signed "own@example.org" source "own"\n  on hook moment in [0 Nm, 1 Nm]\n  signed "block@example.org" source "block"\n}\n')
        own, inherited = d.loads["lift"].entries
        self.assertEqual(own.value.signature, Signature("own@example.org", "own"))
        self.assertEqual(inherited.value.signature, Signature("block@example.org", "block"))

    def test_a_claim_may_name_several_load_cases(self):
        d = lower_text(HOOK + LIFT + LIFT.replace("lift", "gust") + "claim c: hook.utilisation <= 1 under lift, gust\n")
        self.assertEqual(d.claims[0].under, ("lift", "gust"))

    def test_a_known_waiver_mode_is_kept(self):
        d = lower_text(HOOK + 'waive corrosion.galvanic on hook by "o@example.org" reason "isolated"\n')
        self.assertEqual(d.waivers, (Waiver("corrosion.galvanic", ("hook",), "o@example.org", "isolated", Span("t.petra", 9, 1)),))

    def test_a_point_range_is_well_formed(self):
        d = lower_text(HOOK.replace("[36 kN, 40 kN]", "[5 kN, 5 kN]"))
        self.assertEqual(d.components["hook"].attrs[0].args[0].range, q(5000, FORCE))

    def test_the_ir_is_read_only(self):
        d = lower_text(HOOK)
        with self.assertRaises(TypeError):
            d.components["crane"] = d.components["hook"]


class Rejections(Case):
    def test_an_unknown_component_kind(self):
        self.assertProblem('trus frame {\n  material steel.S355\n}\n', 6, 1, "trus", "truss")
        self.assertEqual(lower_text('truss frame {\n  material steel.S355\n}\n').components["frame"].kind, "truss")

    def test_an_input_bound_without_a_signature(self):
        self.assertProblem('demand hook {\n  capacity in [36 kN, 40 kN]\n}\n', 7, 12, "signature")
        self.assertProblem(HOOK + 'load lift {\n  on hook force in [0 kN, 40 kN]\n}\n', 10, 17, "signature")
        self.assertProblem('ambient in [10 degC, 40 degC]\n', 6, 9, "signature")
        self.assertProblem(HOOK + 'tests proof {\n  on hook trials 3 failures 0 at 36 kN\n}\n', 9, 1, "signature")
        self.assertProblem('demand hook {\n  capacity in [36 kN, 40 kN] signed "" source "PL-1"\n}\n', 7, 37, "empty")

    def test_an_unknown_unit(self):
        self.assertProblem('demand hook {\n  capacity in [36 kNN, 40 kN] measured "qa@example.org" source "PL-1"\n}\n', 7, 19, "kNN")
        self.assertProblem("claim c: hook.utilisation <= 1 kip\n" + HOOK, 6, 32, "kip")

    def test_a_dimension_mismatch(self):
        self.assertProblem('demand hook {\n  capacity in [36 kN, 40 m] measured "qa@example.org" source "PL-1"\n}\n', 7, 23, "force", "length")
        self.assertProblem('ambient in [10 kN, 40 kN] signed "s@example.org" source "survey"\n', 6, 9, "ambient", "temperature")
        self.assertProblem('param t in [1 m, 2 m]\nambient param t\n', 7, 9, "ambient", "temperature")
        self.assertProblem(HOOK + LIFT.replace("mean 10 kN", "mean 10 m"), 10, 39, "mean")
        self.assertProblem(HOOK + PROOF + "claim t: P(fail hook at 36 kN) <= 1/100 confidence 95 kN from proof\n", 13, 52, "confidence")

    def test_a_malformed_range(self):
        self.assertProblem('demand hook {\n  capacity in [40 kN, 36 kN] measured "qa@example.org" source "PL-1"\n}\n', 7, 15, "malformed range")
        self.assertProblem("param p in [2 m, 1 m]\n", 6, 12, "malformed range")
        self.assertProblem(HOOK + LIFT.replace("mean 10 kN", "mean 50 kN"), 10, 39, "outside")
        self.assertSyntax(HEADER + 'demand hook {\n  capacity in [36 kN 40 kN] measured "qa@example.org" source "PL-1"\n}\n', 7, 22)
        self.assertSyntax(HEADER + 'demand hook {\n  capacity in [36 kN, 40 kN measured "qa@example.org" source "PL-1"\n}\n', 7, 29)
        self.assertSyntax(HEADER + 'demand hook {\n  capacity in 36 kN measured "qa@example.org" source "PL-1"\n}\n', 7, 15)

    def test_an_unknown_environment_id(self):
        self.assertProblem("", 4, 15, "marine_c6", header=HEADER.replace("indoor_dry", "marine_c6"))

    def test_an_unknown_waiver_mode(self):
        self.assertProblem(HOOK + 'waive corrosion.galvanik on hook by "o@example.org" reason "isolated"\n', 9, 7, "corrosion.galvanik")

    def test_names_that_are_taken(self):
        self.assertProblem(HOOK + HOOK, 9, 8, "twice")
        self.assertProblem(HOOK + "claim coverage: hook.utilisation <= 1\n", 9, 7, "reserved")
        self.assertProblem(HOOK + LIFT + "claim c: hook.utilisation <= 1\nclaim c: P(hook.utilisation > 1) <= 1/2 under lift\n", 14, 7, "twice")
        self.assertProblem("demand tests {\n}\n", 6, 8, "keyword")
        self.assertProblem(HOOK + LIFT + LIFT, 13, 6, "twice")

    def test_references_that_do_not_resolve(self):
        self.assertProblem(HOOK + "claim c: hook.utilisation <= 1 under lifts\n", 9, 38, "lifts")
        self.assertProblem("claim c: frame.collapse_factor >= 1\n", 6, 10, "frame")
        self.assertProblem("claim c: collapse_factor >= 1\n", 6, 10, "declared component")
        self.assertProblem('demand hook {\n  capacity param cap\n}\n', 7, 18, "cap")
        self.assertProblem(HOOK + 'load lift {\n  on crane force in [0 kN, 1 kN]\n  signed "o@example.org" source "s"\n}\n', 10, 6, "crane")
        self.assertProblem(HOOK + PROOF + "claim t: P(fail hook at 36 kN) <= 1/100 confidence 95 % from prof\n", 13, 62, "prof")
        self.assertProblem(HOOK + PROOF.replace("on hook", "on crane"), 10, 6, "crane")

    def test_probability_and_test_counts_that_cannot_hold(self):
        self.assertProblem(HOOK + LIFT + "claim o: P(hook.utilisation > 1) <= 3/2 under lift\n", 13, 37, "probability")
        self.assertProblem(HOOK + PROOF + "claim t: P(fail hook at 36 kN) <= 1/100 confidence 100 % from proof\n", 13, 52, "confidence")
        self.assertProblem(HOOK + PROOF.replace("failures 0", "failures 301"), 9, 1, "exceed")
        signed_twice = 'tests proof {\n  on hook trials 300 failures 0 at 36 kN measured "a@example.org" source "x"\n  measured "qa@example.org" source "batch 9"\n}\n'
        self.assertProblem(HOOK + signed_twice, 11, 3, "twice")

    def test_every_problem_in_a_file_is_reported_together_in_source_order(self):
        error = self.assertProblem("claim c: nowhere.x <= 1\ntrus frame {\n}\n", 7, 1, "trus")
        self.assertEqual([p.split(": ")[0] for p in error.problems], ["t.petra:6:10", "t.petra:7:1"])

    def test_a_file_without_a_design_block(self):
        with self.assertRaises(LoweringError) as ctx:
            parse_design("petra 0\n" + HOOK, "t.petra", REGISTRY)
        self.assertTrue(ctx.exception.problems[0].startswith("t.petra:1:1: "))
        self.assertProblem("", 2, 1, "owner", header='petra 0\ndesign "d" {\n}\n')


class SyntaxErrors(Case):
    def test_positions_name_the_offending_token(self):
        self.assertSyntax(HEADER + "claim c: x.y <= 1 ;\n", 6, 19)
        self.assertSyntax(HEADER + "requirement x\n", 6, 1)
        self.assertSyntax("petra 1\n", 1, 7)
        self.assertSyntax("design \"d\" {\n}\n", 1, 1)
        self.assertSyntax(HEADER + 'claim c: x.y <= 1 under "l"\n', 6, 25)
        self.assertSyntax(HEADER + 'demand hook {\n  owner "unterminated\n}\n', 7, 9)
        self.assertSyntax(HEADER + "claim c: x.member(m) <= 1\n", 6, 19)
        self.assertSyntax(HEADER + "claim c: x.y <= 1/0\n", 6, 17)
        self.assertSyntax(HEADER + 'demand hook {\n  capacity signed "a" source "b"\n}\n', 7, 12)

    def test_the_declaration_error_lists_the_language_keywords(self):
        with self.assertRaises(LolaSyntaxError) as ctx:
            parse_design(HEADER + "requirement x\n", "t.petra", REGISTRY)
        for keyword in ("design", "param", "ambient", "load", "tests", "claim", "waive"):
            self.assertIn(keyword, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
