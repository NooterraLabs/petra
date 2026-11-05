"""Coverage rules, requirement generation and waivers. Owner: P.

The v0 domains' features hooks belong to other seams, so generation runs against a small
widget domain registered in place of the real ones. The galvanic rule and the table are
the real ones.
"""
import unittest
from fractions import Fraction
from unittest import mock

from lola import coverage
from lola.coverage import GALVANIC_CONTACT, RULES, apply_waivers, claim_requirements, generate, table_premise
from lola.ir import (
    Claim,
    Component,
    Design,
    Exceeds,
    FailsAt,
    FromTests,
    Input,
    InputKind,
    LoadCase,
    LoadEntry,
    ProbabilityClaim,
    QoiRef,
    RangeMean,
    Rel,
    Signature,
    Span,
    Waiver,
)
from lola.kernel import Interval
from lola.models import bolt, circuit, truss
from lola.models.base import (
    CONTACT_PAIR,
    GALVANIC_CORROSION,
    NO_PORTS,
    ClaimOrigin,
    CoverageOrigin,
    CoverageRule,
    Criterion,
    DomainSpec,
    EnergyDomain,
    FailureMode,
    Feature,
    FeatureKind,
    ProbabilityCriterion,
    Requirement,
)
from lola.premises import Tag
from lola.units import DIMENSIONLESS, FORCE, STRESS, Quantity
from tests.test_premises import REGISTRY

STRENGTH = FailureMode("widget.strength")
BEARING = FailureMode("widget.bearing")
PART = FeatureKind("widget.part")
ONE = Quantity(Interval(Fraction(1), Fraction(1)), DIMENSIONLESS)
MECHANICAL = frozenset({EnergyDomain.MECHANICAL})


def ratio(x: Fraction) -> Quantity:
    return Quantity(Interval(x, x), DIMENSIONLESS)


def _default(mode: FailureMode, feature: Feature) -> Criterion | None:
    return Criterion(Rel.LE, ONE) if mode is STRENGTH else None


WIDGET_RULE = CoverageRule("widget.part", lambda f, r: f.kind == PART, (STRENGTH, BEARING), _default, "every widget part")
WIDGET = DomainSpec(
    name="widget",
    kinds={"widget": lambda component, design, registry: ()},
    builders={STRENGTH: lambda req, model, design, registry: ()},
    unmodelled=frozenset({BEARING}),
    qois={"utilisation": STRENGTH},
    probability={RangeMean: STRENGTH, FromTests: STRENGTH},
    coverage=(WIDGET_RULE,),
    models={},
    features=lambda model, design, registry: model,
    ports=lambda model, registry: NO_PORTS,
)


def span(line: int) -> Span:
    return Span("t.lola", line, 1)


def part(name: str = "p1", materials: tuple[str, ...] = ("steel.S355",), kind: FeatureKind = PART, environment: str | None = "marine_c5") -> Feature:
    return Feature(("w", name), kind, materials, MECHANICAL, environment)


def contact(*materials: str, environment: str | None = "marine_c5") -> Feature:
    return Feature(("w",), CONTACT_PAIR, materials, frozenset({EnergyDomain.CHEMICAL}), environment)


def claim(name: str, bound: Quantity, rel: Rel = Rel.LE, path: tuple[str, ...] = ("w", "p1"), under: tuple[str, ...] = (), line: int = 10) -> Claim:
    return Claim(name, QoiRef(path, "utilisation"), rel, bound, under, None, span(line))


def load(name: str, target: tuple[str, ...] = ("w",)) -> LoadCase:
    entry = Input(f"{name}.w.force", Quantity(Interval(Fraction(0), Fraction(10)), FORCE), Signature("o@example.org", "brief"), InputKind.ASSUMED, span(2))
    return LoadCase(name, (LoadEntry(target, "force", entry),), span(2))


def design(claims=(), probability_claims=(), loads=(), waivers=()) -> Design:
    return Design(
        name="d",
        owner="o@example.org",
        path="t.lola",
        environment="marine_c5",
        ambient=None,
        components={"w": Component("widget", "w", (), span(1))},
        loads={case.name: case for case in loads},
        claims=tuple(claims),
        probability_claims=tuple(probability_claims),
        tests={},
        waivers=tuple(waivers),
        params={},
    )


def demanded(d: Design, *features: Feature) -> list[Requirement]:
    return [r for r in generate(d, {"w": features}, REGISTRY) if isinstance(r.origin, CoverageOrigin)]


class WidgetDomain(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(coverage, "KINDS", {"widget": WIDGET}))


class Table(unittest.TestCase):
    def test_the_table_demands_the_v0_modes(self):
        demands = {mode for rule in RULES for mode in rule.demands}
        for mode in (GALVANIC_CORROSION, truss.MEMBER_BUCKLING, circuit.SHORT_CIRCUIT, circuit.OVERLOAD_PROTECTION, bolt.PLATE_BEARING):
            self.assertIn(mode, demands, mode.id)
        self.assertIn(GALVANIC_CONTACT, coverage.CROSS_DOMAIN)

    def test_the_table_is_one_judged_premise(self):
        p = table_premise()
        self.assertRegex(p.label, r"^cov:[0-9a-f]{16}$")
        self.assertIs(p.tag, Tag.JUDGED)
        self.assertEqual(p.owner, "lola-maintainers")
        self.assertEqual(table_premise(), p)
        for rule in RULES:
            self.assertIn(rule.id, p.statement)


class Requirements(unittest.TestCase):
    def test_id_names_subject_mode_and_origin(self):
        self.assertEqual(
            Requirement(("frame", "diag_ad"), truss.MEMBER_BUCKLING, None, CoverageOrigin("truss.axial_member")).id,
            "frame.diag_ad/truss.member_buckling/coverage.truss.axial_member",
        )
        self.assertEqual(Requirement(("bracket",), bolt.TENSION, None, ClaimOrigin("tension")).id, "bracket/bolt.tension/claim.tension")


class Claims(WidgetDomain):
    def test_a_claim_becomes_one_requirement(self):
        c = claim("tension", ratio(Fraction(9, 10)), under=("wind",))
        (req,) = claim_requirements(design([c]), {"w": ()})
        self.assertEqual(req, Requirement(("w", "p1"), STRENGTH, Criterion(Rel.LE, ratio(Fraction(9, 10))), ClaimOrigin("tension"), ("wind",), c.qoi))

    def test_probability_claims_take_their_mode_from_the_method(self):
        qoi = QoiRef(("w",), "utilisation")
        exceeds = ProbabilityClaim("overload", Exceeds(qoi, ONE, "lift"), Fraction(3, 10), RangeMean(), span(12))
        tested = ProbabilityClaim("tested", FailsAt(("w",), Quantity(Interval(Fraction(36000), Fraction(36000)), FORCE)), Fraction(1, 100), FromTests("proof", Fraction(95, 100)), span(13))
        first, second = claim_requirements(design(probability_claims=[exceeds, tested]), {"w": ()})
        self.assertEqual(first, Requirement(("w",), STRENGTH, ProbabilityCriterion(ONE, Fraction(3, 10), "lift", None, None), ClaimOrigin("overload"), ("lift",), qoi))
        self.assertEqual(second, Requirement(("w",), STRENGTH, ProbabilityCriterion(None, Fraction(1, 100), None, "proof", Fraction(95, 100)), ClaimOrigin("tested"), (), None))

    def test_claims_keep_source_order(self):
        late = claim("late", ONE, line=30)
        early = claim("early", ONE, line=10)
        middle = ProbabilityClaim("middle", Exceeds(QoiRef(("w",), "utilisation"), ONE, "lift"), Fraction(1, 2), RangeMean(), span(20))
        names = [r.origin.claim for r in claim_requirements(design([late, early], [middle]), {"w": ()})]
        self.assertEqual(names, ["early", "middle", "late"])


class Generation(WidgetDomain):
    def test_a_matching_rule_demands_each_mode_once_per_subject(self):
        reqs = demanded(design(), part(), part(), part(kind=FeatureKind("widget.other")))
        self.assertEqual(
            reqs,
            [
                Requirement(("w", "p1"), STRENGTH, Criterion(Rel.LE, ONE), CoverageOrigin("widget.part")),
                Requirement(("w", "p1"), BEARING, None, CoverageOrigin("widget.part")),
            ],
        )

    def test_a_rule_that_does_not_match_demands_nothing(self):
        self.assertEqual(demanded(design(), part(kind=FeatureKind("widget.other"))), [])

    def test_a_claim_at_least_as_strict_settles_the_coverage_requirement(self):
        for bound in (Fraction(9, 10), Fraction(1)):
            modes = [r.mode for r in demanded(design([claim("c", ratio(bound))]), part())]
            self.assertEqual(modes, [BEARING], f"a claim of <= {bound} settles the default <= 1")

    def test_a_claim_that_does_not_imply_the_default_leaves_it(self):
        cases = {
            "looser bound": claim("c", ratio(Fraction(6, 5))),
            "other relation": claim("c", ratio(Fraction(1, 2)), rel=Rel.GE),
            "other dimension": claim("c", Quantity(Interval(Fraction(1), Fraction(1)), STRESS)),
            "other subject": claim("c", ratio(Fraction(1, 2)), path=("w", "p2")),
        }
        for why, c in cases.items():
            modes = [r.mode for r in demanded(design([c]), part())]
            self.assertEqual(modes, [STRENGTH, BEARING], why)

    def test_a_claim_settles_coverage_only_under_every_load_case_on_the_component(self):
        loads = [load("wind"), load("snow"), load("elsewhere", target=("other",))]
        partial = claim("c", ratio(Fraction(9, 10)), under=("wind",))
        every = claim("c", ratio(Fraction(9, 10)), under=("wind", "snow"))
        self.assertEqual([r.mode for r in demanded(design([partial], loads=loads), part())], [STRENGTH, BEARING])
        self.assertEqual([r.mode for r in demanded(design([every], loads=loads), part())], [BEARING])

    def test_claims_come_first(self):
        reqs = generate(design([claim("c", ratio(Fraction(6, 5)))]), {"w": (part(),)}, REGISTRY)
        self.assertEqual([type(r.origin) for r in reqs], [ClaimOrigin, CoverageOrigin, CoverageOrigin])

    def test_cross_domain_rules_see_every_domains_features(self):
        (req,) = demanded(design(), contact("stainless.A4", "aluminium.6061_T6"))
        self.assertEqual(req, Requirement(("w",), GALVANIC_CORROSION, None, CoverageOrigin("galvanic.contact")))


class Galvanic(unittest.TestCase):
    """Anodic indices from MIL-STD-889C: A4 stainless 0.50 V, 6061 aluminium 0.90 V,
    copper 0.35 V. The rule fires above a 0.15 V spread in wet, C3-or-worse, or undeclared
    environments."""

    def applies(self, feature: Feature) -> bool:
        return GALVANIC_CONTACT.when(feature, REGISTRY)

    def test_dissimilar_metals_in_a_wet_or_corrosive_environment(self):
        self.assertTrue(self.applies(contact("stainless.A4", "aluminium.6061_T6", environment="marine_c5")))
        self.assertTrue(self.applies(contact("stainless.A4", "aluminium.6061_T6", environment="outdoor_c3")))
        self.assertTrue(self.applies(contact("stainless.A4", "aluminium.6061_T6", environment=None)), "an undeclared environment counts as wet")

    def test_no_check_where_galvanic_corrosion_cannot_run(self):
        cases = {
            "dry C1 environment": contact("stainless.A4", "aluminium.6061_T6", environment="indoor_dry"),
            "one metal": contact("aluminium.6061_T6", "aluminium.6061_T6"),
            "spread of exactly 0.15 V": contact("copper.annealed", "stainless.A4"),
            "a polymer is not an electrode": contact("pvc.general", "aluminium.6061_T6"),
            "not a contact pair": part(materials=("stainless.A4", "aluminium.6061_T6")),
        }
        for why, feature in cases.items():
            self.assertFalse(self.applies(feature), why)


class Waivers(unittest.TestCase):
    BEARING_REQ = Requirement(("w", "p1"), BEARING, None, CoverageOrigin("widget.part"))
    CLAIMED = Requirement(("w", "p1"), STRENGTH, Criterion(Rel.LE, ONE), ClaimOrigin("c"))

    def waiver(self, mode: str = "widget.bearing", subject: tuple[str, ...] = ("w", "p1")) -> Waiver:
        return Waiver(mode, subject, "m.engineer@example.org", "bearing checked by hand, calc C-14", span(40))

    def test_a_matching_waiver_becomes_a_judged_premise(self):
        remaining, waived = apply_waivers((self.BEARING_REQ,), design(waivers=[self.waiver()]))
        self.assertEqual(remaining, ())
        ((req, premise),) = waived
        self.assertEqual(req, self.BEARING_REQ)
        self.assertEqual(premise.label, "waive:d.widget.bearing.w.p1")
        self.assertIs(premise.tag, Tag.JUDGED)
        self.assertEqual(premise.owner, "m.engineer@example.org")
        self.assertIn("calc C-14", premise.statement)
        self.assertIn("t.lola:40", premise.source)

    def test_a_waiver_matches_exact_mode_and_subject_only(self):
        reqs = (self.BEARING_REQ,)
        for w in (self.waiver(subject=("w", "p2")), self.waiver(subject=("w",)), self.waiver(mode="widget.strength")):
            self.assertEqual(apply_waivers(reqs, design(waivers=[w])), (reqs, ()), w)

    def test_a_claim_is_never_waived(self):
        reqs = (self.CLAIMED,)
        self.assertEqual(apply_waivers(reqs, design(waivers=[self.waiver(mode="widget.strength")])), (reqs, ()))


if __name__ == "__main__":
    unittest.main()
