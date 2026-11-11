"""The front end: the text of a card and of a design -> Design IR, and every rejection the
parse boundary owns. Owner: L."""
import dataclasses
import unittest
from fractions import Fraction
from pathlib import Path

from petra import grid, models
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
from petra.files import read_pair
from petra.lang import LolaSyntaxError, LoweringError, load_design, parse_design
from petra.premises import Tag
from petra.registry import Corrosivity, Environment, Registry, Stated
from petra.units import AREA, CURRENT, DIMENSIONLESS, FORCE, LENGTH, STRESS, TEMPERATURE, TORQUE, VOLTAGE, Quantity

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def environments_only(*ids: str) -> Registry:
    """Design-level lowering reads only the registry's environment ids; the domains'
    lowerers read the rest."""
    ambient = Stated(Interval(Fraction(0), Fraction(40)), "degC", Tag.SANCTIONED, "test fixture", "test fixture", "test fixture")
    envs = {e: Environment(e, ambient, Corrosivity.C1, False, source="test fixture") for e in ids}
    return Registry(constants={}, materials={}, parts={}, processes={}, environments=envs)


REGISTRY = environments_only("indoor_dry", "outdoor_c3", "marine_c5")


HEADER = 'petra 0\ncard "d" {\n  owner "o@example.org"\n  environment indoor_dry\n}\n'
"""A card down to its block, so the first line a test adds to the card is line 6. The first
line a test adds to the design is line 2, after `petra 0`."""
CAPACITY = 'given capacity in [36 kN, 40 kN] measured "qa@example.org" source "PL-1"\n'
HOOK = "demand hook {\n  capacity given capacity\n}\n"
LIFT = 'load lift {\n  on hook force in [0 kN, 40 kN] mean 10 kN\n  signed "ops@example.org" source "duty log"\n}\n'
PROOF = 'tests proof {\n  on hook trials 300 failures 0 at 36 kN\n  measured "qa@example.org" source "batch 9"\n}\n'


def lower_text(card: str = CAPACITY, design: str = HOOK, header: str = HEADER) -> Design:
    return parse_design(header + card, "petra 0\n" + design, "t.petra", REGISTRY)


def q(x, dim) -> Quantity:
    return Quantity(Interval(Fraction(x), Fraction(x)), dim)


def rng(lo, hi, dim) -> Quantity:
    return Quantity(Interval(Fraction(lo), Fraction(hi)), dim)


def unspanned(x):
    return dataclasses.replace(x, span=None)


def attr(design: Design, component: str, key: str, nth: int = 0) -> tuple:
    return [a for a in design.components[component].attrs if a.key == key][nth].args


class Case(unittest.TestCase):
    def assertProblem(self, at: str, *fragments: str, card: str = CAPACITY, design: str = HOOK, header: str = HEADER) -> LoweringError:
        """A problem at `at`, which is FILE:LINE:COL, that holds every fragment."""
        with self.assertRaises(LoweringError) as ctx:
            lower_text(card, design, header)
        found = [p for p in ctx.exception.problems if p.startswith(f"{at}: ")]
        self.assertTrue(found, f"no problem at {at} in {ctx.exception.problems}")
        for fragment in fragments:
            self.assertIn(fragment, found[0])
        return ctx.exception

    def assertSyntax(self, at: str, *fragments: str, card: str = HEADER + CAPACITY, design: str = "petra 0\n" + HOOK) -> None:
        """A syntax error at `at`, which is FILE:LINE:COL, in the whole text of a card or a design."""
        with self.assertRaises(LolaSyntaxError) as ctx:
            parse_design(card, design, "t.petra", REGISTRY)
        self.assertTrue(str(ctx.exception).startswith(f"{at}: "), str(ctx.exception))
        self.assertEqual(f"{ctx.exception.path}:{ctx.exception.line}:{ctx.exception.col}", at)
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))


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
                    self.assertIn(component.kind, {*models.KINDS, *grid.kinds()})

    def test_every_example_is_rejected_once_its_component_kind_is_misspelt(self):
        for path in self.paths():
            with self.subTest(example=str(path.relative_to(EXAMPLES))):
                card, text = read_pair(path)
                kind = next(iter(load_design(path, REGISTRY).components.values())).kind
                broken = text.replace(f"\n{kind} ", f"\n{kind}x ", 1)
                self.assertNotEqual(broken, text)
                with self.assertRaises(LoweringError):
                    parse_design(card, broken, str(path), REGISTRY)

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

    def test_bolt_unknown_keeps_digit_led_registry_ids_and_reads_the_cards_bounds(self):
        d = load_design(EXAMPLES / "bolt_unknown.petra", REGISTRY)
        self.assertEqual(d.environment, "marine_c5")
        self.assertEqual(attr(d, "bracket", "bolt"), (Ref(("bolt", "M12_A4_70")), Ref(("count",)), Fixed(q(1, DIMENSIONLESS))))
        self.assertEqual(attr(d, "bracket", "plate"), (Ref(("aluminium", "6061_T6")), Ref(("thickness",)), Fixed(q(Fraction(1, 100), LENGTH))))
        (torque,) = attr(d, "bracket", "torque")
        self.assertEqual(unspanned(torque), Bound(rng(40, 50, TORQUE), Signature("fitter.lead@example.org", "assembly spec AS-12 rev C"), InputKind.ASSUMED, None, None, "torque"))
        self.assertEqual(torque.span.path, str(EXAMPLES / "bolt_unknown.card"), "a bound is where the card states it")
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
        self.assertEqual(tuple(d.params), ("size", "insulation", "run", "draw", "amb"), "the design's params, then the card's")
        self.assertEqual(d.params["size"].range, rng(Fraction(1, 400000), Fraction(1, 62500), AREA))
        self.assertEqual(d.ambient, ParamRef("amb"))
        self.assertEqual(attr(d, "c", "wire")[3:5], (Ref(("area",)), ParamRef("size")))
        self.assertEqual(d.loads["demand"].entries[0], LoadEntry(("c", "load"), "current", ParamRef("draw")))

    def test_a_card_named_on_its_own_stands_in_for_the_one_beside_the_design(self):
        d = load_design(EXAMPLES / "truss_pass.petra", REGISTRY, EXAMPLES / "truss_fail.card")
        self.assertEqual((d.path, d.loads["crowd"].span.path), (str(EXAMPLES / "truss_pass.petra"), str(EXAMPLES / "truss_fail.card")))


class Lowering(Case):
    def test_a_component_keeps_its_positions_and_a_bound_the_cards(self):
        d = lower_text()
        hook = d.components["hook"]
        self.assertEqual((hook.span, hook.attrs[0].span), (Span("t.petra", 2, 1), Span("t.petra", 3, 3)))
        self.assertEqual(
            hook.attrs[0].args,
            (Bound(rng(36000, 40000, FORCE), Signature("qa@example.org", "PL-1"), InputKind.MEASURED, Span("t.card", 6, 16), None, "capacity"),),
        )

    def test_any_attribute_line_of_a_registered_kind_reaches_its_domain_typed(self):
        d = lower_text("", 'param p in [1 m, 2 m]\ntruss frame {\n  anything 3 kN foo.bar "x y" (1 m, 2 m) : -- -> param p\n}\n')
        self.assertEqual(
            d.components["frame"].attrs,
            (Attr("anything", (Fixed(q(3000, FORCE)), Ref(("foo", "bar")), Text("x y"), Vec((q(1, LENGTH), q(2, LENGTH))), Punct(":"), Punct("--"), Punct("->"), ParamRef("p")), Span("t.petra", 4, 3)),),
        )

    def test_comments_blank_lines_and_bracketed_line_breaks_are_layout(self):
        d = lower_text('# a comment\n\ngiven capacity in [36 kN,\n      40 kN] measured "qa@example.org" source "PL-1"   # trailing\n',
                       "# a comment\n\ndemand hook {   # trailing\n\n  capacity given capacity\n}\n")
        self.assertEqual(d.components["hook"].attrs[0].args[0].range, rng(36000, 40000, FORCE))

    def test_crlf_line_ends_lower_like_lf(self):
        crlf = parse_design((HEADER + CAPACITY).replace("\n", "\r\n"), ("petra 0\n" + HOOK).replace("\n", "\r\n"), "t.petra", REGISTRY)
        self.assertEqual(crlf.components["hook"], lower_text().components["hook"])

    def test_string_escapes(self):
        d = lower_text("", "", header='petra 0\ncard "d" {\n  owner "a \\"b\\" \\\\ c"\n}\n')
        self.assertEqual(d.owner, 'a "b" \\ c')
        self.assertIsNone(d.environment)

    def test_an_entry_signature_wins_over_its_block_signature(self):
        d = lower_text(CAPACITY + 'load lift {\n  on hook force in [0 kN, 1 kN] signed "own@example.org" source "own"\n  on hook moment in [0 Nm, 1 Nm]\n  signed "block@example.org" source "block"\n}\n')
        own, inherited = d.loads["lift"].entries
        self.assertEqual(own.value.signature, Signature("own@example.org", "own"))
        self.assertEqual(inherited.value.signature, Signature("block@example.org", "block"))

    def test_a_claim_may_name_several_load_cases(self):
        d = lower_text(CAPACITY + LIFT + LIFT.replace("lift", "gust") + "claim c: hook.utilisation <= 1 under lift, gust\n")
        self.assertEqual(d.claims[0].under, ("lift", "gust"))

    def test_a_known_waiver_mode_is_kept(self):
        d = lower_text(CAPACITY + 'waive corrosion.galvanic on hook by "o@example.org" reason "isolated"\n')
        self.assertEqual(d.waivers, (Waiver("corrosion.galvanic", ("hook",), "o@example.org", "isolated", Span("t.card", 7, 1)),))

    def test_a_point_range_is_well_formed(self):
        d = lower_text(CAPACITY.replace("[36 kN, 40 kN]", "[5 kN, 5 kN]"))
        self.assertEqual(d.components["hook"].attrs[0].args[0].range, q(5000, FORCE))

    def test_the_ir_is_read_only(self):
        d = lower_text()
        with self.assertRaises(TypeError):
            d.components["crane"] = d.components["hook"]


class TwoFiles(Case):
    """What only the card may state, what only the design may, and how the design reads the card."""

    def test_a_design_states_nothing_that_is_the_cards(self):
        cards = (LIFT, PROOF, "claim c: hook.utilisation <= 1\n", 'waive corrosion.galvanic on hook by "o@example.org" reason "isolated"\n',
                 'ambient in [10 degC, 40 degC] signed "s@example.org" source "survey"\n', CAPACITY, 'card "d" {\n  owner "o@example.org"\n}\n',
                 'design "d" {\n  owner "o@example.org"\n}\n')
        for declaration in cards:
            with self.subTest(declaration=declaration.split()[0]):
                self.assertSyntax("t.petra:5:1", "belongs in the card", design="petra 0\n" + HOOK + declaration)

    def test_a_design_signs_no_bound(self):
        self.assertSyntax("t.petra:3:12", "signs no bound", design='petra 0\ndemand hook {\n  capacity in [36 kN, 40 kN] measured "qa@example.org" source "PL-1"\n}\n')
        self.assertSyntax("t.petra:3:12", "signs no bound", design='petra 0\ndemand hook {\n  capacity signed "a" source "b"\n}\n')

    def test_a_card_holds_no_component(self):
        self.assertSyntax("t.card:7:1", "belongs in the design", card=HEADER + CAPACITY + HOOK)

    def test_a_design_reads_only_what_the_card_gives(self):
        self.assertProblem("t.petra:3:12", "'cap'", "capacity", design="demand hook {\n  capacity given cap\n}\n")
        self.assertProblem("t.petra:3:12", "'capacity'", "nothing", card="")

    def test_a_design_reads_every_bound_the_card_gives(self):
        self.assertProblem("t.card:6:7", "'capacity'", "no component reads it", design="")
        both = lower_text(design=HOOK + HOOK.replace("hook", "crane"))
        self.assertIs(both.components["hook"].attrs[0].args[0], both.components["crane"].attrs[0].args[0], "two lines may read one bound")

    def test_a_given_is_a_signed_bound(self):
        self.assertSyntax("t.card:6:16", "bound", card=HEADER + "given capacity param p\n")
        self.assertProblem("t.card:6:16", "signature", card="given capacity in [36 kN, 40 kN]\n")
        self.assertProblem("t.card:7:7", "twice", card=CAPACITY + CAPACITY)

    def test_a_param_is_the_cards_or_the_designs(self):
        param = "param p in [0 kN, 1 kN]\n"
        load = 'load lift {\n  on hook force param p\n  signed "o@example.org" source "s"\n}\n'
        self.assertEqual(lower_text(CAPACITY + param + load).loads["lift"].entries[0].value, ParamRef("p"))
        self.assertProblem("t.card:8:23", "unknown param 'p'", card=CAPACITY + load, design=param + HOOK)
        self.assertProblem("t.petra:2:7", "in the card too", card=CAPACITY + param, design=param + HOOK)
        reads = lower_text(param, "truss frame {\n  anything param p\n}\n")
        self.assertEqual(reads.components["frame"].attrs[0].args, (ParamRef("p"),), "a design reads the card's params")


class Rejections(Case):
    def test_an_unknown_component_kind(self):
        self.assertProblem("t.petra:2:1", "trus", "truss", card="", design="trus frame {\n  material steel.S355\n}\n")
        self.assertEqual(lower_text("", "truss frame {\n  material steel.S355\n}\n").components["frame"].kind, "truss")

    def test_an_input_bound_without_a_signature(self):
        self.assertProblem("t.card:6:16", "signature", card="given capacity in [36 kN, 40 kN]\n")
        self.assertProblem("t.card:8:17", "signature", card=CAPACITY + "load lift {\n  on hook force in [0 kN, 40 kN]\n}\n")
        self.assertProblem("t.card:7:9", "signature", card=CAPACITY + "ambient in [10 degC, 40 degC]\n")
        self.assertProblem("t.card:7:1", "signature", card=CAPACITY + "tests proof {\n  on hook trials 3 failures 0 at 36 kN\n}\n")
        self.assertProblem("t.card:6:41", "empty", card='given capacity in [36 kN, 40 kN] signed "" source "PL-1"\n')

    def test_an_unknown_unit(self):
        self.assertProblem("t.card:6:23", "kNN", card=CAPACITY.replace("36 kN", "36 kNN"))
        self.assertProblem("t.card:6:32", "furlong", card="claim c: hook.utilisation <= 1 furlong\n" + CAPACITY)

    def test_a_dimension_mismatch(self):
        self.assertProblem("t.card:6:27", "force", "length", card=CAPACITY.replace("40 kN", "40 m"))
        self.assertProblem("t.card:7:9", "ambient", "temperature", card=CAPACITY + 'ambient in [10 kN, 40 kN] signed "s@example.org" source "survey"\n')
        self.assertProblem("t.card:8:9", "ambient", "temperature", card=CAPACITY + "param t in [1 m, 2 m]\nambient param t\n")
        self.assertProblem("t.card:8:39", "mean", card=CAPACITY + LIFT.replace("mean 10 kN", "mean 10 m"))
        self.assertProblem("t.card:11:52", "confidence", card=CAPACITY + PROOF + "claim t: P(fail hook at 36 kN) <= 1/100 confidence 95 kN from proof\n")

    def test_a_malformed_range(self):
        self.assertProblem("t.card:6:19", "malformed range", card=CAPACITY.replace("[36 kN, 40 kN]", "[40 kN, 36 kN]"))
        self.assertProblem("t.petra:2:12", "malformed range", design="param p in [2 m, 1 m]\n" + HOOK)
        self.assertProblem("t.card:8:39", "outside", card=CAPACITY + LIFT.replace("mean 10 kN", "mean 50 kN"))
        self.assertSyntax("t.card:6:26", card=HEADER + CAPACITY.replace("36 kN,", "36 kN"))
        self.assertSyntax("t.card:6:33", card=HEADER + CAPACITY.replace("40 kN]", "40 kN"))
        self.assertSyntax("t.card:6:19", card=HEADER + CAPACITY.replace("[36 kN, 40 kN]", "36 kN"))

    def test_an_unknown_environment_id(self):
        self.assertProblem("t.card:4:15", "marine_c6", header=HEADER.replace("indoor_dry", "marine_c6"))

    def test_an_unknown_waiver_mode(self):
        self.assertProblem("t.card:7:7", "corrosion.galvanik", card=CAPACITY + 'waive corrosion.galvanik on hook by "o@example.org" reason "isolated"\n')

    def test_names_that_are_taken(self):
        self.assertProblem("t.petra:5:8", "twice", design=HOOK + HOOK)
        self.assertProblem("t.card:7:7", "reserved", card=CAPACITY + "claim coverage: hook.utilisation <= 1\n")
        self.assertProblem("t.card:12:7", "twice", card=CAPACITY + LIFT + "claim c: hook.utilisation <= 1\nclaim c: P(hook.utilisation > 1) <= 1/2 under lift\n")
        self.assertProblem("t.petra:2:8", "keyword", card="", design="demand tests {\n}\n")
        self.assertProblem("t.card:11:6", "twice", card=CAPACITY + LIFT + LIFT)

    def test_references_that_do_not_resolve(self):
        self.assertProblem("t.card:7:38", "lifts", card=CAPACITY + "claim c: hook.utilisation <= 1 under lifts\n")
        self.assertProblem("t.card:7:10", "frame", card=CAPACITY + "claim c: frame.collapse_factor >= 1\n")
        self.assertProblem("t.card:7:10", "declared component", card=CAPACITY + "claim c: collapse_factor >= 1\n")
        self.assertProblem("t.petra:3:18", "cap", card="", design="demand hook {\n  capacity param cap\n}\n")
        self.assertProblem("t.card:8:6", "crane", card=CAPACITY + 'load lift {\n  on crane force in [0 kN, 1 kN]\n  signed "o@example.org" source "s"\n}\n')
        self.assertProblem("t.card:11:62", "prof", card=CAPACITY + PROOF + "claim t: P(fail hook at 36 kN) <= 1/100 confidence 95 % from prof\n")
        self.assertProblem("t.card:8:6", "crane", card=CAPACITY + PROOF.replace("on hook", "on crane"))

    def test_probability_and_test_counts_that_cannot_hold(self):
        self.assertProblem("t.card:11:37", "probability", card=CAPACITY + LIFT + "claim o: P(hook.utilisation > 1) <= 3/2 under lift\n")
        self.assertProblem("t.card:11:52", "confidence", card=CAPACITY + PROOF + "claim t: P(fail hook at 36 kN) <= 1/100 confidence 100 % from proof\n")
        self.assertProblem("t.card:7:1", "exceed", card=CAPACITY + PROOF.replace("failures 0", "failures 301"))
        signed_twice = 'tests proof {\n  on hook trials 300 failures 0 at 36 kN measured "a@example.org" source "x"\n  measured "qa@example.org" source "batch 9"\n}\n'
        self.assertProblem("t.card:9:3", "twice", card=CAPACITY + signed_twice)

    def test_every_problem_in_the_two_files_is_reported_together_in_source_order(self):
        error = self.assertProblem("t.petra:2:1", "trus", card="claim c: nowhere.x <= 1\nclaim d: nowhere.y <= 1\n", design="trus frame {\n}\n")
        self.assertEqual([p.split(": ")[0] for p in error.problems], ["t.card:6:10", "t.card:7:10", "t.petra:2:1"])

    def test_a_card_without_a_card_block(self):
        with self.assertRaises(LoweringError) as ctx:
            parse_design("petra 0\n" + CAPACITY, "petra 0\n" + HOOK, "t.petra", REGISTRY)
        self.assertTrue(ctx.exception.problems[0].startswith("t.card:1:1: "))
        self.assertProblem("t.card:2:1", "owner", header='petra 0\ncard "d" {\n}\n')


class SyntaxErrors(Case):
    def test_positions_name_the_offending_token(self):
        self.assertSyntax("t.card:6:19", card=HEADER + "claim c: x.y <= 1 ;\n")
        self.assertSyntax("t.card:6:1", card=HEADER + "requirement x\n")
        self.assertSyntax("t.petra:2:1", design="petra 0\nrequirement x\n")
        self.assertSyntax("t.card:1:7", card="petra 1\n")
        self.assertSyntax("t.petra:1:7", design="petra 1\n")
        self.assertSyntax("t.card:1:1", card='card "d" {\n}\n')
        self.assertSyntax("t.card:6:25", card=HEADER + 'claim c: x.y <= 1 under "l"\n')
        self.assertSyntax("t.petra:3:9", design='petra 0\ndemand hook {\n  owner "unterminated\n}\n')
        self.assertSyntax("t.card:6:19", card=HEADER + "claim c: x.member(m) <= 1\n")
        self.assertSyntax("t.card:6:17", card=HEADER + "claim c: x.y <= 1/0\n")

    def test_a_number_is_at_most_a_hundred_characters(self):
        self.assertSyntax("t.card:6:20", "at most 100", card=HEADER + CAPACITY.replace("36 kN", "3" * 101 + " kN"))
        self.assertSyntax("t.petra:3:12", "at most 100", design="petra 0\ntruss frame {\n  anything " + "1" * 101 + "\n}\n")
        longest = lower_text("", "truss frame {\n  anything " + "1" * 100 + "\n}\n")
        self.assertEqual(longest.components["frame"].attrs[0].args[0].quantity.value.lo, int("1" * 100))

    def test_the_declaration_error_lists_what_the_file_takes(self):
        with self.assertRaises(LolaSyntaxError) as ctx:
            parse_design(HEADER + "requirement x\n", "petra 0\n", "t.petra", REGISTRY)
        for keyword in ("card", "param", "ambient", "given", "load", "tests", "claim", "waive"):
            self.assertIn(keyword, str(ctx.exception))
        with self.assertRaises(LolaSyntaxError) as ctx:
            parse_design(HEADER, "petra 0\nrequirement x\n", "t.petra", REGISTRY)
        for word in ("param", "component block"):
            self.assertIn(word, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
