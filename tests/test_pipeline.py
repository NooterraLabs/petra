"""check_design, explain, the premise book and the evidence-source protocol. Owner: I.

The v0 domains belong to other seams, so the pipeline runs against a small gadget domain
registered in place of the real ones. Its claim says a load stays within a fraction u of
a capacity, F - u * C * scale * twice <= 0, where scale is a stated registry rating (1)
and twice is derived from the constant g.half (2 * 1/2 = 1). Every statement it builds
goes through the real StatementBuilder and the real kernel.
"""
import itertools
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping
from unittest import mock

from petra import coverage, models
from petra.certs import CertStore
from petra.ir import Bound, FromTests, Input, ParamRef, Ref, Rel
from petra.kernel import Add, Const, Evidence, Interval, Leaf, Mul, Neg, Split, Sym, enclose
from petra.kernel.rules.r4_enclosure import AllNonpositive, Enclosure, PointWitness
from petra.kernel.rules.r6_scenario import Arithmetic, BinomialTail
from petra.lang import parse_design
from petra.models.base import (
    CROSS_DOMAIN_MODES,
    CROSS_DOMAIN_UNMODELLED,
    PORT_CONTRACT,
    CertificateRejected,
    CertificateTooWeak,
    ComponentError,
    Connection,
    CoverageOrigin,
    CoverageRule,
    Criterion,
    DomainSpec,
    EnergyDomain,
    FailureMode,
    Feature,
    FeatureKind,
    Gap,
    NeedsCertificate,
    NoModel,
    NoRuleForQuantity,
    Obligation,
    PortRef,
    PortSpec,
    Ports,
    RegistryInconsistent,
    Requirement,
    StatementBuilder,
    model_spec,
)
from petra.pipeline import build_premise_book, check_design, explain
from petra.premises import RangeMismatch, ScopeParam, Tag
from petra.registry import Constant, Corrosivity, Deck, DeckEntry, DeckRecord, Derived, Environment, Material, Registry, Stated
from petra.units import DIMENSIONLESS, Quantity
from petra.verdict import Fail, Pass, Unknown

STRENGTH = FailureMode("gadget.strength")
WEAR = FailureMode("gadget.wear")
TESTED = FailureMode("gadget.tested")
SILENT = FailureMode("gadget.silent")
PART = FeatureKind("gadget.part")
THIS = sys.modules[__name__]
STRENGTH_MODEL = model_spec(THIS, "gadget.strength", "load against capacity", "the load acts axially", "tests@example.org", "tests/test_pipeline.py")
TESTED_MODEL = model_spec(THIS, "gadget.scenario", "i.i.d. proof tests", "every test loads at the claimed level", "tests@example.org", "tests/test_pipeline.py")


def point(x) -> Interval:
    return Interval(Fraction(x), Fraction(x))


@dataclass(frozen=True)
class Gadget:
    name: str
    material: str
    limits: Mapping[str, object]
    inert: bool
    ports: tuple[str, ...]


def lower_gadget(component, design, registry) -> Gadget:
    material, limits, inert, ports, problems = None, {}, False, [], []
    for attr in component.attrs:
        match attr.key, attr.args:
            case "material", (Ref(parts=parts),):
                material = ".".join(parts)
            case "capacity", (Bound() as b,):
                limits["capacity"] = Input(f"{component.name}.capacity", b.range, b.signature, b.kind, b.span, b.mean)
            case "capacity", (ParamRef() as p,):
                limits["capacity"] = p
            case "inert", ():
                inert = True
            case "port", (Ref(parts=(port,)),):
                ports.append(port)
            case _:
                problems.append(f"{attr.span.path}:{attr.span.line}: gadget {component.name} cannot read {attr.key}")
    if problems:
        raise ComponentError(tuple(problems))
    registry.material(material)
    return Gadget(component.name, material, MappingProxyType(limits), inert, tuple(ports))


def build_strength(req, gadget, design, registry):
    capacity = gadget.limits["capacity"]
    out = []
    for case in design.loads.values():
        if req.under and case.name not in req.under:
            continue
        for entry in case.entries:
            sb = StatementBuilder(design, registry)
            force = sb.input(entry.value) if isinstance(entry.value, Input) else sb.value(entry.value, "")
            cap = sb.input(capacity) if isinstance(capacity, Input) else sb.value(capacity, "")
            u = Const(req.criterion.bound.value.hi)
            margin = Add((force, Neg(Mul((u, cap, sb.registry(gadget.material, "scale"), sb.registry(gadget.material, "twice"))))))
            out.append(Obligation(req, sb.finish(AllNonpositive((margin,))), STRENGTH_MODEL, f"{case.name} stays within {u.value} of capacity"))
    return tuple(out)


def build_tested(req, gadget, design, registry):
    sb = StatementBuilder(design, registry)
    n, k = sb.tests(design.tests[req.criterion.tests])
    goal = BinomialTail(n, k, Const(req.criterion.p), Const(1 - req.criterion.confidence))
    return (Obligation(req, sb.finish(goal), TESTED_MODEL, "failure probability from proof tests"),)


def features(gadget, design, registry):
    if gadget.inert:
        return ()
    return (Feature((gadget.name,), PART, (gadget.material,), frozenset({EnergyDomain.MECHANICAL}), design.environment),)


def ports(gadget, registry):
    refs = [PortRef(gadget.name, gadget.name, p) for p in gadget.ports]
    return Ports(tuple(PortSpec(r, {}, {}) for r in refs), tuple(Connection(a, b, None) for a, b in zip(refs, refs[1:])))


def strength_default(mode, feature):
    return Criterion(Rel.LE, Quantity(point(1), DIMENSIONLESS)) if mode is STRENGTH else None


GADGET = DomainSpec(
    name="gadget",
    kinds={"gadget": lower_gadget},
    builders={STRENGTH: build_strength, TESTED: build_tested, SILENT: lambda req, model, design, registry: ()},
    unmodelled=frozenset({WEAR}),
    qois={"utilisation": STRENGTH, "silence": SILENT},
    probability={FromTests: TESTED},
    coverage=(CoverageRule("gadget.part", lambda f, r: f.kind == PART, (STRENGTH, WEAR), strength_default, "every gadget part"),),
    models={STRENGTH: STRENGTH_MODEL, TESTED: TESTED_MODEL},
    features=features,
    ports=ports,
)


def stated(value: Interval, owner: str, standard: str) -> Stated:
    return Stated(value, "1", Tag.SANCTIONED, owner, standard, "at 20 degC")


def registry() -> Registry:
    props = {"scale": stated(point(1), "maker@example.org", "Std 2 table 3"), "twice": Derived(Mul((Const(Fraction(2)), Sym("const.g.half"))), "1")}
    return Registry(
        constants={"g.half": Constant("g.half", point(Fraction(1, 2)), "1", Tag.SANCTIONED, "standards@example.org", "Std 1", "half is one half")},
        materials={"metal.M1": Material("metal.M1", "metal", "Std 2", props)},
        parts={},
        processes={},
        environments={"dry": Environment("dry", stated(Interval(Fraction(10), Fraction(30)), "met@example.org", "climate class"), Corrosivity.C1, False,
                                       source="climate class")},
    )


REGISTRY = registry()
HEADER = 'petra 0\ndesign "rig" {\n  owner "o@example.org"\n  environment dry\n}\n'
CAPACITY = '  capacity in [20 kN, 25 kN] measured "lab@example.org" source "proof report P-1"\n'


def gadget(*lines: str, name: str = "g") -> str:
    return f"gadget {name} {{\n  material metal.M1\n" + "".join(lines) + "}\n"


def push(hi: str = "10", lo: str = "0") -> str:
    return f'load push {{\n  on g force in [{lo} kN, {hi} kN] mean 4 kN\n  signed "client@example.org" source "brief rev A"\n}}\n'


CLAIM = "claim fits: g.utilisation <= 1/2 under push\n"
WAIVE_WEAR = 'waive gadget.wear on g by "o@example.org" reason "no sliding contact"\n'
PROOF = 'tests proof {{\n  on g trials {n} failures 0 at 30 kN\n  measured "lab@example.org" source "batch 9"\n}}\n'
TESTED_CLAIM = "claim tested: P(fail g at 30 kN) <= 1/100 confidence 95 % from proof\n"


class Solver:
    """Test double for SolverSource: for R4 a one-leaf partition, then a counterexample
    at the first box corner where some expression is positive; for R6 the arithmetic."""

    name = "testsolver"

    def offer(self, statement, digest):
        if isinstance(statement.goal, BinomialTail):
            yield Evidence(Arithmetic())
            return
        yield Evidence(Enclosure(Leaf()))
        syms = [h.sym for h in statement.hyps]
        for corner in itertools.product(*((h.lo, h.hi) for h in statement.hyps)):
            at = tuple(zip(syms, corner))
            for k, e in enumerate(statement.goal.exprs):
                if enclose(e, {s: point(v) for s, v in at}).lo > 0:
                    yield Evidence(PointWitness(at, k))
                    return


class Offers:
    """Offers fixed evidence for every statement and counts how often it was asked."""

    def __init__(self, name, *evidence):
        self.name, self.evidence, self.asked = name, evidence, 0

    def offer(self, statement, digest):
        self.asked += 1
        return self.evidence


class Broken:
    name = "broken"

    def offer(self, statement, digest):
        raise RuntimeError("solver crashed")
        yield


class Sink:
    def __init__(self, fail=False):
        self.recorded, self.fail = [], fail

    def record(self, statement, digest, evidence, source):
        if self.fail:
            raise OSError("disk full")
        self.recorded.append((digest, source))


class GadgetDomain(unittest.TestCase):
    def setUp(self):
        modes = {m.id: m for m in (STRENGTH, WEAR, TESTED, SILENT, *CROSS_DOMAIN_MODES)}
        self.enterContext(mock.patch.object(models, "KINDS", MappingProxyType({"gadget": GADGET})))
        self.enterContext(mock.patch.object(models, "MODES", MappingProxyType(modes)))
        self.enterContext(mock.patch.object(models, "UNMODELLED", frozenset({WEAR}) | CROSS_DOMAIN_UNMODELLED))
        self.enterContext(mock.patch.object(coverage, "KINDS", {"gadget": GADGET}))

    def design(self, *blocks: str, registry: Registry = REGISTRY):
        return parse_design(HEADER + "".join(blocks), "rig.petra", registry)

    def check(self, *blocks: str, sources=(Solver(),), **kwargs):
        return check_design(self.design(*blocks), REGISTRY, tuple(sources), **kwargs)

    def entry(self, report, claim):
        return next(e.verdict for e in report.entries if e.claim == claim)

    def needs(self, verdict):
        return [n for item in verdict.open for n in item.needs]


class Verdicts(GadgetDomain):
    def test_a_claim_that_holds_passes_with_its_whole_footprint(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Pass, report.render())
        footprint = report.verdict.footprint
        expected = {
            coverage.table_premise().label,
            STRENGTH_MODEL.premise().label,
            "waive:rig.gadget.wear.g",
            "reg:const.g.half",
            "reg:metal.M1.scale",
            "in:rig.push.g.force",
            "in:rig.g.capacity",
        }
        certified = {p.label for p in footprint.premises if p.tag is Tag.CERTIFIED}
        self.assertEqual(footprint.labels - certified, expected)
        self.assertEqual(len(certified), 1, "one certified premise for the one theorem")
        by_label = {p.label: p for p in footprint.premises}
        self.assertEqual((by_label["in:rig.g.capacity"].tag, by_label["in:rig.g.capacity"].owner), (Tag.MEASURED, "lab@example.org"))
        self.assertEqual((by_label["in:rig.push.g.force"].tag, by_label["in:rig.push.g.force"].source), (Tag.ASSUMED, "brief rev A"))
        self.assertEqual((by_label["reg:metal.M1.scale"].owner, by_label["reg:metal.M1.scale"].source), ("maker@example.org", "Std 2 table 3"))
        self.assertEqual(report.verdict.scope.load_cases, ("push",))
        self.assertEqual(report.verdict.scope.environment, "dry")

    def test_a_load_beyond_the_claim_fails_at_its_worst_corner(self):
        report = self.check(gadget(CAPACITY), push("30"), CLAIM, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Fail, report.render())
        at = dict(report.verdict.refutation.point)
        self.assertEqual((at["push.g.force"], at["g.capacity"]), (30000, 20000), "30 kN against half of 20 kN")
        self.assertIn("in:rig.push.g.force", report.verdict.footprint.labels)

    def test_without_evidence_the_claim_is_unknown_and_names_its_statement(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, sources=())
        self.assertIsInstance(report.verdict, Unknown)
        (need,) = self.needs(report.verdict)
        discharged = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR).outcomes[0]
        self.assertEqual(need, NeedsCertificate(discharged.theorem.statement_hash, "R4", discharged.obligation.describe))

    def test_an_unmodelled_mode_without_a_waiver_holds_the_coverage_entry_open(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM)
        self.assertIsInstance(self.entry(report, "fits"), Pass)
        self.assertEqual(self.needs(self.entry(report, "coverage")), [NoModel(WEAR, ("g",))])
        self.assertIsInstance(report.verdict, Unknown)

    def test_a_builder_that_states_nothing_cannot_make_its_claim_vanish(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, "claim quiet: g.silence <= 1\n")
        self.assertEqual([e.claim for e in report.entries], ["fits", "quiet"])
        (need,) = self.needs(self.entry(report, "quiet"))
        self.assertIsInstance(need, NoRuleForQuantity)
        self.assertIsInstance(report.verdict, Unknown)

    def test_a_probability_claim_passes_on_its_tested_counts(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, PROOF.format(n=300), TESTED_CLAIM)
        tested = self.entry(report, "tested")
        self.assertIsInstance(tested, Pass, "0.99^300 = 0.049 <= 0.05")
        trials = next(p for p in tested.footprint.premises if p.label == "in:rig.tests.proof.trials")
        self.assertEqual((trials.tag, trials.owner, trials.range), (Tag.MEASURED, "lab@example.org", point(300)))
        self.assertIn("in:rig.tests.proof.failures", tested.footprint.labels)

    def test_too_few_tests_leave_the_probability_claim_open_as_too_weak(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, PROOF.format(n=200), TESTED_CLAIM)
        (need,) = self.needs(self.entry(report, "tested"))
        self.assertIsInstance(need, CertificateTooWeak, "0.99^200 = 0.134 > 0.05")
        self.assertEqual((need.rule, need.source), ("R6", "testsolver"))

    def test_a_scope_parameter_bounds_the_pass_and_stays_out_of_the_footprint(self):
        param = "param cap in [20 kN, 25 kN]\n"
        report = self.check(param, gadget("  capacity param cap\n"), push("10"), CLAIM, WAIVE_WEAR)
        self.assertIsInstance(report.verdict, Pass, report.render())
        self.assertEqual(report.verdict.scope.params, (ScopeParam("par:rig.cap", "cap", Interval(Fraction(20000), Fraction(25000)), "N"),))
        self.assertFalse(any(label.startswith("par:") for label in report.verdict.footprint.labels))
        self.assertIn("par:rig.cap", report.verdict.theorems[0].labels)


class EvidenceSources(GadgetDomain):
    BODY = (gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR)

    def test_invalid_evidence_is_rejected_and_names_its_source(self):
        forged = Offers("forger", Evidence(Enclosure(Split("push.g.force", Fraction(50000), Leaf(), Leaf()))))
        report = self.check(*self.BODY, sources=(forged,))
        (need,) = self.needs(report.verdict)
        self.assertIsInstance(need, CertificateRejected)
        self.assertEqual((need.source, need.rule), ("forger", "R4"))

    def test_evidence_that_proves_too_little_is_too_weak(self):
        report = self.check(gadget(CAPACITY), push("30"), CLAIM, WAIVE_WEAR, sources=(Offers("leafy", Evidence(Enclosure(Leaf()))),))
        (need,) = self.needs(report.verdict)
        self.assertIsInstance(need, CertificateTooWeak)
        self.assertEqual(need.source, "leafy")

    def test_the_first_candidate_the_kernel_accepts_wins_in_source_order(self):
        forged = Offers("forger", Evidence(Enclosure(Split("push.g.force", Fraction(50000), Leaf(), Leaf()))))
        never = Offers("never")
        report = self.check(*self.BODY, sources=(forged, Solver(), never))
        self.assertIsInstance(report.verdict, Pass)
        self.assertEqual(report.outcomes[0].source, "testsolver")
        self.assertEqual(never.asked, 0, "no source after the accepting one is asked")

    def test_a_failing_source_costs_only_the_evidence_it_would_have_offered(self):
        report = self.check(*self.BODY, sources=(Broken(), Solver()))
        self.assertIsInstance(report.verdict, Pass)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("broken", report.warnings[0])
        alone = self.check(*self.BODY, sources=(Broken(),))
        self.assertIsInstance(self.needs(alone.verdict)[0], NeedsCertificate)

    def test_accepted_evidence_goes_to_the_sink_and_a_failing_sink_only_warns(self):
        sink = Sink()
        report = self.check(*self.BODY, sink=sink)
        self.assertEqual(sink.recorded, [(report.outcomes[0].theorem.statement_hash, "testsolver")])
        failing = self.check(*self.BODY, sink=Sink(fail=True))
        self.assertIsInstance(failing.verdict, Pass)
        self.assertIn("disk full", failing.warnings[0])
        unrecorded = Sink()
        self.check(*self.BODY, sources=(), sink=unrecorded)
        self.assertEqual(unrecorded.recorded, [], "nothing accepted, nothing recorded")

    def test_a_check_is_deterministic_given_the_same_sources(self):
        self.assertEqual(self.check(*self.BODY).to_json(), self.check(*self.BODY).to_json())


class StoredCertificates(GadgetDomain):
    BODY = (gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR)

    def setUp(self):
        super().setUp()
        self.store = CertStore(self.enterContext(tempfile.TemporaryDirectory()))
        first = self.check(*self.BODY, sink=self.store)
        self.assertIsInstance(first.verdict, Pass)
        (self.path,) = self.store.paths()

    def test_a_stored_certificate_discharges_the_obligation_it_was_written_for(self):
        report = self.check(*self.BODY, sources=(self.store,))
        self.assertIsInstance(report.verdict, Pass)
        self.assertEqual(report.outcomes[0].source, "certs")

    def test_a_certificate_whose_statement_was_edited_is_never_consulted(self):
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        envelope["statement"]["hyps"][-1]["hi"] = "1000000"
        self.path.write_text(json.dumps(envelope), encoding="utf-8")
        report = self.check(*self.BODY, sources=(self.store,))
        self.assertIsInstance(self.needs(report.verdict)[0], NeedsCertificate)
        self.assertIn("certs", report.warnings[0])

    def test_a_certificate_for_an_earlier_design_does_not_discharge_a_changed_one(self):
        report = self.check(gadget(CAPACITY), push("8"), CLAIM, WAIVE_WEAR, sources=(self.store,))
        self.assertIsInstance(self.needs(report.verdict)[0], NeedsCertificate)
        self.assertEqual(report.warnings, ())

    def test_tampered_evidence_under_the_right_hash_is_rejected_by_the_kernel(self):
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        envelope["evidence"]["body"]["partition"] = {"t": "split", "sym": "push.g.force", "at": "50000", "left": {"t": "leaf"}, "right": {"t": "leaf"}}
        self.path.write_text(json.dumps(envelope), encoding="utf-8")
        report = self.check(*self.BODY, sources=(self.store,))
        (need,) = self.needs(report.verdict)
        self.assertIsInstance(need, CertificateRejected)
        self.assertEqual(need.source, "certs")


class PremiseBook(GadgetDomain):
    def setUp(self):
        super().setUp()
        ambient = 'ambient in [10 degC, 40 degC] signed "site@example.org" source "survey"\n'
        blocks = (ambient, "param span in [1 m, 2 m]\n", gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, PROOF.format(n=300), TESTED_CLAIM)
        self.design_ = self.design(*blocks)
        report = check_design(self.design_, REGISTRY, (Solver(),))
        self.assertIsInstance(report.verdict, Pass, report.render())
        self.book = build_premise_book(self.design_, REGISTRY, report.outcomes)

    def test_every_label_kind_resolves_to_its_owner_and_the_range_it_grants(self):
        cases = {
            "reg:metal.M1.scale": (Tag.SANCTIONED, "maker@example.org", point(1)),
            "reg:const.g.half": (Tag.SANCTIONED, "standards@example.org", point(Fraction(1, 2))),
            "in:rig.push.g.force": (Tag.ASSUMED, "client@example.org", Interval(Fraction(0), Fraction(10000))),
            "in:rig.push.g.force.mean": (Tag.ASSUMED, "client@example.org", point(4000)),
            "in:rig.g.capacity": (Tag.MEASURED, "lab@example.org", Interval(Fraction(20000), Fraction(25000))),
            "in:rig.ambient": (Tag.ASSUMED, "site@example.org", Interval(Fraction(10), Fraction(40))),
            "in:rig.tests.proof.trials": (Tag.MEASURED, "lab@example.org", point(300)),
            "in:rig.tests.proof.failures": (Tag.MEASURED, "lab@example.org", point(0)),
        }
        for label, (tag, owner, granted) in cases.items():
            entry = self.book.resolve(label, granted)
            self.assertEqual((entry.tag, entry.owner, entry.range), (tag, owner, granted), label)
        span = self.book.resolve("par:rig.span", Interval(Fraction(1), Fraction(2)))
        self.assertEqual(span, ScopeParam("par:rig.span", "span", Interval(Fraction(1), Fraction(2)), "m"))

    def test_a_hypothesis_narrower_than_its_premise_is_refused(self):
        with self.assertRaises(RangeMismatch):
            self.book.resolve("in:rig.push.g.force", Interval(Fraction(0), Fraction(5000)))
        with self.assertRaises(RangeMismatch):
            self.book.resolve("in:rig.g.capacity", point(20000))


class NothingToCheck(GadgetDomain):
    def test_a_design_whose_every_requirement_is_waived_is_an_input_error(self):
        waive_strength = 'waive gadget.strength on g by "o@example.org" reason "test rig only"\n'
        with self.assertRaises(ComponentError):
            self.check(gadget(CAPACITY), push("10"), WAIVE_WEAR, waive_strength)

    def test_a_design_that_demands_nothing_is_an_input_error(self):
        with self.assertRaises(ComponentError):
            self.check(gadget(CAPACITY, "  inert\n"), push("10"))

    def test_one_requirement_left_is_enough_for_a_verdict(self):
        report = self.check(gadget(CAPACITY, "  inert\n"), push("10"), CLAIM)
        self.assertIsInstance(report.verdict, Pass)


class Waivers(GadgetDomain):
    def test_a_waiver_that_matches_no_coverage_requirement_is_a_warning(self):
        on_claim = 'waive gadget.strength on g by "o@example.org" reason "claimed already"\n'
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, on_claim)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("gadget.strength on g", report.warnings[0])
        self.assertEqual(self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR).warnings, ())


class PortContracts(GadgetDomain):
    def contracts(self, design, connections, specs, registry):
        self.seen = (connections, specs)
        return tuple(
            Gap(Requirement((c.a.component, c.a.element, c.a.port), PORT_CONTRACT, None, CoverageOrigin("port.contract")), (NoRuleForQuantity("current", "nothing guarantees it"),))
            for c in connections
        )

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch("petra.pipeline.contract_obligations", self.contracts))

    def test_every_components_ports_reach_the_contracts_and_their_obligations_are_checked(self):
        report = self.check(gadget(CAPACITY, "  port a\n", "  port b\n"), push("10"), CLAIM, WAIVE_WEAR)
        connections, specs = self.seen
        self.assertEqual(set(specs), {PortRef("g", "g", "a"), PortRef("g", "g", "b")})
        self.assertEqual(len(connections), 1)
        self.assertIsInstance(self.needs(self.entry(report, "coverage"))[0], NoRuleForQuantity)

    def test_a_waiver_on_a_port_contract_waives_it(self):
        waive = 'waive port.contract on g.g.a by "o@example.org" reason "bench supply"\n'
        report = self.check(gadget(CAPACITY, "  port a\n", "  port b\n"), push("10"), CLAIM, WAIVE_WEAR, waive)
        self.assertIsInstance(report.verdict, Pass, report.render())
        self.assertEqual(report.warnings, ())


class Lowering(GadgetDomain):
    def test_every_lowering_problem_is_reported_in_one_input_error(self):
        broken = gadget(CAPACITY, "  colour red\n") + "gadget h {\n  material metal.M9\n}\n"
        with self.assertRaises(ComponentError) as raised:
            self.check(broken, push("10"), CLAIM)
        self.assertEqual(len(raised.exception.problems), 2)


class Decks(GadgetDomain):
    def deck(self, fy: int, fu: int) -> Deck:
        provenance = "stated:sanctioned:maker@example.org:Std 2"
        records = (DeckRecord("metal.M1", "fu", point(fu), "Pa", provenance), DeckRecord("metal.M1", "fy", point(fy), "Pa", provenance))
        return Deck("petra-deck/1", records, (DeckEntry("metal.M1", 1, "Std 2", ()),))

    def test_an_obligation_that_reads_a_flagged_entry_stays_open_without_asking_a_source(self):
        asked = Offers("asked", Evidence(Enclosure(Leaf())))
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, sources=(asked,), deck=self.deck(500, 400))
        (need,) = self.needs(report.verdict)
        self.assertIsInstance(need, RegistryInconsistent)
        self.assertEqual((need.entry, need.relation), ("metal.M1", "material.yield_order"))
        self.assertEqual(asked.asked, 0)

    def test_a_consistent_deck_changes_nothing(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR, deck=self.deck(300, 400))
        self.assertIsInstance(report.verdict, Pass)


class Reports(GadgetDomain):
    def test_the_json_report_has_one_verdict_per_claim_then_coverage(self):
        report = self.check(gadget(CAPACITY), push("10"), CLAIM)
        body = json.loads(json.dumps(report.to_json()))
        self.assertEqual((body["file"], body["design"], body["status"]), ("rig.petra", "rig", "UNKNOWN"))
        self.assertEqual([(v["claim"], v["status"]) for v in body["verdicts"]], [("fits", "PASS"), ("coverage", "UNKNOWN")])
        self.assertEqual([bool(v["needs"]) for v in body["verdicts"]], [False, True])
        self.assertEqual(body["verdicts"][0]["rules"], ["R4"])

    def test_the_text_report_names_the_design_each_entry_and_each_warning(self):
        text = self.check(gadget(CAPACITY), push("10"), CLAIM, sources=(Broken(), Solver())).render()
        first, second = text.split("\n")[:2]
        self.assertEqual(first, "rig: UNKNOWN")
        self.assertEqual(second, "entries    fits PASS, coverage UNKNOWN")
        self.assertIn("warning    broken failed on g/gadget.strength/claim.fits", text)


class Explain(GadgetDomain):
    def test_explain_prints_every_statement_with_its_labels_and_every_gap(self):
        text = explain(self.design(gadget(CAPACITY), push("10"), CLAIM), REGISTRY)
        for fragment in ("obligation g/gadget.strength/claim.fits", "in:rig.push.g.force", "in:rig.g.capacity",
                         "reg:metal.M1.scale", "reg:const.g.half", "all_nonpositive", "gap g/gadget.wear/coverage.gadget.part",
                         "no model for gadget.wear on g"):
            self.assertIn(fragment, text)

    def test_explain_shows_a_waived_requirement_instead_of_its_gap(self):
        text = explain(self.design(gadget(CAPACITY), push("10"), CLAIM, WAIVE_WEAR), REGISTRY)
        self.assertIn("waived g/gadget.wear/coverage.gadget.part", text)
        self.assertNotIn("gap ", text)


if __name__ == "__main__":
    unittest.main()
