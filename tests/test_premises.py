"""Premises, the premise book, footprints, and the statement builder's labelling. Owner: P."""
import unittest
from fractions import Fraction

from lola.ir import Design, Fixed, Input, InputKind, Param, ParamRef, Signature, Span, Tests
from lola.kernel import Add, Const, DefinedHyp, Div, Interval, Matrix, Mul, Neg, RangeHyp, Sym, enclose
from lola.kernel.rules.r3_hypercircle import MinimizerComponent, QuadraticProblem
from lola.kernel.rules.r4_enclosure import AllNonpositive
from lola.kernel.rules.r5_moment import MomentBound, MomentConstraint, RandomVar
from lola.models.base import StatementBuilder
from lola.premises import (
    DesignValue,
    Footprint,
    LabelKind,
    Premise,
    PremiseBook,
    RangeMismatch,
    ScopeParam,
    Tag,
    UnresolvedLabel,
    constant_label,
    design_label,
    input_label,
    label_kind,
    param_label,
    registry_label,
)
from lola.registry import Constant, Corrosivity, Derived, Environment, Material, OutsideMakeableSet, Part, PartKind, Registry, Stated, build_registry
from lola.units import AREA, DIMENSIONLESS, FORCE, Quantity

RANGE = Interval(Fraction(0), Fraction(1))
SPAN = Span("t.lola", 1, 1)


def premise(label: str, tag: Tag = Tag.ASSUMED, owner: str = "o@example.org", source: str = "s", range: Interval | None = None) -> Premise:
    return Premise(label, tag, owner, source, "statement", range)


def point(x: Fraction) -> Interval:
    return Interval(x, x)


def stated(value: Interval, unit: str, tag: Tag = Tag.SANCTIONED) -> Stated:
    return Stated(value, unit, tag, "standards.body@example.org", "a standard", "its test conditions")


class FakeRegistry(Registry):
    """Answers lookups from its own tables, standing in for the derived makeable set."""

    def _find(self, table, id):
        if id not in table:
            raise OutsideMakeableSet(id)
        return table[id]

    def material(self, id):
        return self._find(self.materials, id)

    def part(self, id, kind):
        return self._find(self.parts, id)

    def process(self, id):
        return self._find(self.processes, id)

    def environment(self, id):
        return self._find(self.environments, id)

    def property(self, entry_id, prop):
        for table in (self.materials, self.parts, self.processes):
            if entry_id in table:
                return table[entry_id].props[prop]
        raise OutsideMakeableSet(entry_id)


def constant(name: str, value: Interval, unit: str) -> Constant:
    return Constant(name, value, unit, Tag.SANCTIONED, "standards.body@example.org", "a standard", f"{name} as the standard gives it")


def material(id: str, anodic_index: Fraction | None = None, **props) -> Material:
    if anodic_index is not None:
        props["anodic_index"] = stated(point(anodic_index), "V")
    return Material(id, id.split(".")[0], "a standard", props)


def environment(id: str, corrosivity: Corrosivity, wet: bool) -> Environment:
    return Environment(id, stated(Interval(Fraction(10), Fraction(40)), "degC"), corrosivity, wet)


AREA_2_5 = Fraction(1, 400000)
AREA_16 = Fraction(1, 62500)
RHO20 = Fraction(1, 58000000)

REGISTRY = FakeRegistry(
    constants={
        "steel.E": constant("steel.E", Interval(Fraction(200 * 10**9), Fraction(210 * 10**9)), "Pa"),
        "steel.nu": constant("steel.nu", point(Fraction(3, 10)), "1"),
        "cu.rho20": constant("cu.rho20", point(RHO20), "ohm m"),
    },
    materials={
        "steel.S355": material(
            "steel.S355",
            fy=stated(point(Fraction(355 * 10**6)), "Pa"),
            G=Derived(Div(Sym("const.steel.E"), Mul((Const(Fraction(2)), Add((Const(Fraction(1)), Sym("const.steel.nu")))))), "Pa"),
        ),
        "stainless.A4": material("stainless.A4", Fraction(1, 2)),
        "aluminium.6061_T6": material("aluminium.6061_T6", Fraction(9, 10)),
        "copper.annealed": material("copper.annealed", Fraction(7, 20)),
        "pvc.general": material("pvc.general"),
        "probe.chain": material(
            "probe.chain",
            fy=stated(point(Fraction(355 * 10**6)), "Pa"),
            twice=Derived(Mul((Const(Fraction(2)), Sym("self.fy"))), "Pa"),
            over_nu=Derived(Div(Sym("self.twice"), Sym("const.steel.nu")), "Pa"),
            loop_a=Derived(Add((Sym("self.loop_b"), Const(Fraction(1)))), "1"),
            loop_b=Derived(Mul((Const(Fraction(2)), Sym("self.loop_a"))), "1"),
        ),
    },
    parts={
        "cable.cu_pvc": Part(
            "cable.cu_pvc",
            PartKind.CABLE,
            "Cu/PVC single core",
            "copper.annealed",
            {
                "R20": Derived(Div(Sym("const.cu.rho20"), Sym("self.area")), "ohm/m"),
                "theta_max": stated(point(Fraction(70)), "degC"),
                "broken": Derived(Div(Sym("const.cu.rho20"), Sym("other.area")), "ohm/m"),
                "conductance": Derived(Div(Const(Fraction(1)), Sym("self.R20")), "S m"),
            },
        ),
        "cable.cu_pvc_2_5": Part(
            "cable.cu_pvc_2_5", PartKind.CABLE, "Cu/PVC 2.5 mm2", "copper.annealed", {}, series="cable.cu_pvc", fixes={"area": point(AREA_2_5)}
        ),
    },
    processes={},
    environments={
        "marine_c5": environment("marine_c5", Corrosivity.C5, True),
        "indoor_dry": environment("indoor_dry", Corrosivity.C1, False),
        "outdoor_c3": environment("outdoor_c3", Corrosivity.C3, False),
    },
)

DESIGN = Design(
    name="d",
    owner="o@example.org",
    path="t.lola",
    environment=None,
    ambient=None,
    components={},
    loads={},
    claims=(),
    probability_claims=(),
    tests={},
    waivers=(),
    params={"size": Param("size", Quantity(Interval(AREA_2_5, AREA_16), AREA), SPAN)},
)

FORCE_IN = Input(
    "wind.bracket.force",
    Quantity(Interval(Fraction(0), Fraction(12000)), FORCE),
    Signature("client@example.org", "wind study WS-4"),
    InputKind.ASSUMED,
    SPAN,
    mean=Quantity(point(Fraction(3000)), FORCE),
)


def nonpositive(*exprs) -> AllNonpositive:
    return AllNonpositive(exprs=tuple(exprs))


def builder() -> StatementBuilder:
    return StatementBuilder(DESIGN, REGISTRY)


class Labels(unittest.TestCase):
    def test_prefix_names_the_kind(self):
        self.assertIs(label_kind("reg:steel.S355.fy"), LabelKind.REGISTRY)
        self.assertIs(label_kind("cert:sha256:ab"), LabelKind.CERT)

    def test_unknown_or_missing_prefix_is_refused(self):
        for bad in ("steel.S355", "foo:bar", "in:", ":x"):
            with self.assertRaises(ValueError, msg=bad):
                label_kind(bad)

    def test_label_helpers_spell_the_documented_namespaces(self):
        self.assertEqual(registry_label("steel.S355", "fy"), "reg:steel.S355.fy")
        self.assertEqual(constant_label("cu.rho20"), "reg:const.cu.rho20")
        self.assertEqual(input_label("d", "wind.bracket.force"), "in:d.wind.bracket.force")
        self.assertEqual(param_label("d", "size"), "par:d.size")
        self.assertEqual(design_label("d", "frame.A.x"), "dsg:d.frame.A.x")


class Premises(unittest.TestCase):
    def test_tags_fit_their_namespace(self):
        premise("in:d.lift.force", Tag.ASSUMED)
        premise("reg:steel.S355.fy", Tag.SANCTIONED)
        premise("model:truss.plastic@0123", Tag.VALIDATED_MODEL)
        premise("cov:0123", Tag.JUDGED)
        premise("waive:d.bolt.plate_bearing.hook", Tag.JUDGED)
        premise("cert:sha256:ab", Tag.CERTIFIED)
        for label, tag in (
            ("in:d.lift.force", Tag.SANCTIONED),       # an input bound is never sanctioned
            ("model:truss.plastic@0123", Tag.ASSUMED),  # a model is never merely assumed
            ("cov:0123", Tag.CERTIFIED),
            ("par:d.length", Tag.ASSUMED),             # a scope parameter is not a premise
            ("dsg:d.frame.A.x", Tag.ASSUMED),          # nor is the design itself
        ):
            with self.assertRaises(ValueError, msg=f"{label} {tag}"):
                premise(label, tag)

    def test_proved_is_never_a_premise(self):
        with self.assertRaises(ValueError):
            premise("cert:sha256:ab", Tag.PROVED)

    def test_owner_and_source_are_required(self):
        with self.assertRaises(ValueError):
            premise("in:d.lift.force", owner="")
        with self.assertRaises(ValueError):
            premise("in:d.lift.force", source="")

    def test_scope_params_and_design_values_keep_their_namespace(self):
        ScopeParam("par:d.length", "length", RANGE, "m")
        DesignValue("dsg:d.frame.A.x", RANGE, "m")
        with self.assertRaises(ValueError):
            ScopeParam("in:d.length", "length", RANGE, "m")
        with self.assertRaises(ValueError):
            DesignValue("par:d.frame.A.x", RANGE, "m")


class Footprints(unittest.TestCase):
    def test_sorted_unique_non_empty(self):
        a, b = premise("cov:0123", Tag.JUDGED), premise("in:d.lift.force")
        self.assertEqual(Footprint((a, b)).labels, {"cov:0123", "in:d.lift.force"})
        with self.assertRaises(ValueError):
            Footprint(())
        with self.assertRaises(ValueError):
            Footprint((b, a))
        with self.assertRaises(ValueError):
            Footprint((a, a))
        with self.assertRaises(TypeError):
            Footprint(("cov:0123",))

    def test_by_tag_groups_in_tag_order(self):
        cert = premise("cert:sha256:ab", Tag.CERTIFIED)
        cov = premise("cov:0123", Tag.JUDGED)
        load = premise("in:d.lift.force")
        mass = premise("in:d.lift.mass")
        groups = Footprint((cert, cov, load, mass)).by_tag()
        self.assertEqual(list(groups), [Tag.CERTIFIED, Tag.ASSUMED, Tag.JUDGED])
        self.assertEqual(groups[Tag.ASSUMED], (load, mass))
        self.assertNotIn(Tag.SANCTIONED, groups, "a tag no premise carries has no group")


class Book(unittest.TestCase):
    LOAD = premise("in:d.lift.force", range=Interval(Fraction(0), Fraction(10)))
    PARAM = ScopeParam("par:d.length", "length", Interval(Fraction(1), Fraction(2)), "m")
    DRAWN = DesignValue("dsg:d.frame.A.x", point(Fraction(3)), "m")

    def book(self, *extra) -> PremiseBook:
        return PremiseBook([self.LOAD, premise("cov:0123", Tag.JUDGED), *extra], [self.PARAM], [self.DRAWN])

    def test_resolve_accepts_a_hypothesis_at_least_as_wide_as_the_premise(self):
        book = self.book()
        self.assertIs(book.resolve("in:d.lift.force", Interval(Fraction(0), Fraction(10))), self.LOAD)
        self.assertIs(book.resolve("in:d.lift.force", Interval(Fraction(-1), Fraction(11))), self.LOAD)
        self.assertIs(book.resolve("par:d.length", Interval(Fraction(1), Fraction(2))), self.PARAM)
        self.assertIs(book.resolve("dsg:d.frame.A.x", point(Fraction(3))), self.DRAWN)

    def test_resolve_refuses_a_hypothesis_narrower_than_the_premise(self):
        book = self.book()
        with self.assertRaises(RangeMismatch):
            book.resolve("in:d.lift.force", Interval(Fraction(0), Fraction(9)))
        with self.assertRaises(RangeMismatch):
            book.resolve("par:d.length", Interval(Fraction(1), Fraction(3, 2)))
        with self.assertRaises(RangeMismatch, msg="a premise with no range cannot back a hypothesis"):
            book.resolve("cov:0123", RANGE)

    def test_resolve_refuses_an_unknown_label(self):
        with self.assertRaises(UnresolvedLabel):
            self.book().resolve("in:d.lift.moment", RANGE)

    def test_one_label_one_entry(self):
        self.book(self.LOAD)
        with self.assertRaises(ValueError):
            self.book(premise("in:d.lift.force", range=Interval(Fraction(0), Fraction(20))))
        with self.assertRaises(TypeError):
            PremiseBook(["in:d.lift.force"], [], [])

    def test_footprint_names_premises_only(self):
        fp = self.book().footprint(["in:d.lift.force", "par:d.length", "dsg:d.frame.A.x", "cov:0123", "in:d.lift.force"])
        self.assertEqual([p.label for p in fp.premises], ["cov:0123", "in:d.lift.force"])
        with self.assertRaises(UnresolvedLabel):
            self.book().footprint(["in:d.lift.moment"])


class BuilderLabels(unittest.TestCase):
    def test_a_stated_property_is_one_labelled_hypothesis(self):
        sb = builder()
        fy = sb.registry("steel.S355", "fy")
        st = sb.finish(nonpositive(Neg(fy)))
        self.assertEqual(st.hyps, (RangeHyp("steel.S355.fy", Fraction(355 * 10**6), Fraction(355 * 10**6), "reg:steel.S355.fy"),))

    def test_a_derived_property_names_its_constants_not_a_cached_number(self):
        sb = builder()
        g = sb.registry("steel.S355", "G")
        self.assertEqual(g, Div(Sym("const.steel.E"), Mul((Const(Fraction(2)), Add((Const(Fraction(1)), Sym("const.steel.nu")))))))
        st = sb.finish(nonpositive(Neg(g)))
        self.assertEqual(
            st.hyps,
            (
                RangeHyp("const.steel.E", Fraction(200 * 10**9), Fraction(210 * 10**9), "reg:const.steel.E"),
                RangeHyp("const.steel.nu", Fraction(3, 10), Fraction(3, 10), "reg:const.steel.nu"),
            ),
        )

    def test_a_size_entry_expands_through_its_series(self):
        sb = builder()
        r20 = sb.registry("cable.cu_pvc_2_5", "R20")
        theta = sb.registry("cable.cu_pvc_2_5", "theta_max")
        self.assertEqual(r20, Div(Sym("const.cu.rho20"), Sym("cable.cu_pvc_2_5.area")))
        st = sb.finish(nonpositive(Add((r20, Neg(theta)))))
        self.assertEqual(
            st.hyps,
            (
                RangeHyp("cable.cu_pvc.theta_max", Fraction(70), Fraction(70), "reg:cable.cu_pvc.theta_max"),
                RangeHyp("cable.cu_pvc_2_5.area", AREA_2_5, AREA_2_5, "dsg:d.cable.cu_pvc_2_5.area"),
                RangeHyp("const.cu.rho20", RHO20, RHO20, "reg:const.cu.rho20"),
            ),
        )

    def test_a_family_binds_series_parameters_to_its_params(self):
        sb = builder()
        area = sb.value(ParamRef("size"), "c.w1.area")
        r20 = sb.registry("cable.cu_pvc", "R20", series={"area": area})
        self.assertEqual(r20, Div(Sym("const.cu.rho20"), Sym("size")))
        st = sb.finish(nonpositive(r20))
        self.assertIn(RangeHyp("size", AREA_2_5, AREA_16, "par:d.size"), st.hyps)

    def test_series_parameters_must_be_fixed_or_bound_exactly_once(self):
        sb = builder()
        area = sb.value(ParamRef("size"), "c.w1.area")
        with self.assertRaises(ValueError, msg="a series entry with nothing bound"):
            sb.registry("cable.cu_pvc", "R20")
        with self.assertRaises(ValueError, msg="a size entry fixes its area"):
            sb.registry("cable.cu_pvc_2_5", "R20", series={"area": area})
        with self.assertRaises(TypeError, msg="a binding must be one of this builder's hypotheses"):
            sb.registry("cable.cu_pvc", "R20", series={"area": Const(AREA_2_5)})
        with self.assertRaises(ValueError, msg="a derivation may name only const.* and self.*, even when the rest matches a fixed parameter"):
            sb.registry("cable.cu_pvc_2_5", "broken")

    def test_a_derivation_that_names_a_derived_property_expands_it_recursively(self):
        sb = builder()
        over_nu = sb.registry("probe.chain", "over_nu")
        self.assertEqual(over_nu, Div(Mul((Const(Fraction(2)), Sym("probe.chain.fy"))), Sym("const.steel.nu")))
        st = sb.finish(nonpositive(over_nu))
        self.assertEqual(
            st.hyps,
            (
                RangeHyp("const.steel.nu", Fraction(3, 10), Fraction(3, 10), "reg:const.steel.nu"),
                RangeHyp("probe.chain.fy", Fraction(355 * 10**6), Fraction(355 * 10**6), "reg:probe.chain.fy"),
            ),
        )
        box = {h.sym: Interval(h.lo, h.hi) for h in st.hyps}
        self.assertEqual(enclose(over_nu, box), point(Fraction(2 * 355 * 10**6) / Fraction(3, 10)), "2 fy / nu")

    def test_a_nested_property_of_a_size_reads_the_size_fixed_parameters(self):
        sb = builder()
        conductance = sb.registry("cable.cu_pvc_2_5", "conductance")
        self.assertEqual(conductance, Div(Const(Fraction(1)), Div(Sym("const.cu.rho20"), Sym("cable.cu_pvc_2_5.area"))))
        labels = {h.label for h in sb.finish(nonpositive(conductance)).hyps}
        self.assertEqual(labels, {"reg:const.cu.rho20", "dsg:d.cable.cu_pvc_2_5.area"})

    def test_a_derivation_cycle_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, r"probe\.chain: derivation cycle loop_a -> loop_b -> loop_a"):
            builder().registry("probe.chain", "loop_a")

    def test_nested_shipped_derivations_match_hand_values(self):
        registry = build_registry()
        cases = (
            ("cable.cu_pvc_2_5", "T1", 0.509429, 1e-6,
             {"dsg:d.cable.cu_pvc_2_5.area", "dsg:d.cable.cu_pvc_2_5.insulation", "reg:const.pvc.thermal_resistivity"}),
            ("bolt.M12_8_8", "Fp", 48874.6, 0.1,
             {"reg:bolt.M12_8_8.Sp", "reg:const.iso261.M12.d", "reg:const.iso261.M12.pitch",
              "reg:const.iso724.d2_coefficient", "reg:const.iso724.d3_coefficient"}),
        )
        for entry, prop, expected, tolerance, labels in cases:
            with self.subTest(f"{entry}.{prop}"):
                sb = StatementBuilder(DESIGN, registry)
                value = sb.registry(entry, prop)
                st = sb.finish(nonpositive(value))
                self.assertEqual({h.label for h in st.hyps}, labels)
                found = enclose(value, {h.sym: Interval(h.lo, h.hi) for h in st.hyps})
                self.assertLess(abs(float(found.midpoint()) - expected), tolerance, f"{entry}.{prop} = {float(found.midpoint())}")

    def test_inputs_means_and_tests_carry_their_owner_label(self):
        sb = builder()
        force = sb.input(FORCE_IN)
        mean = sb.mean(FORCE_IN)
        trials, failures = sb.tests(Tests("proof", ("hook",), 300, 0, Quantity(point(Fraction(36000)), FORCE), Signature("qa@example.org", "PL-0917"), SPAN))
        st = sb.finish(nonpositive(Add((force, mean, trials, failures))))
        self.assertEqual(
            st.hyps,
            (
                RangeHyp("tests.proof.failures", Fraction(0), Fraction(0), "in:d.tests.proof.failures"),
                RangeHyp("tests.proof.trials", Fraction(300), Fraction(300), "in:d.tests.proof.trials"),
                RangeHyp("wind.bracket.force", Fraction(0), Fraction(12000), "in:d.wind.bracket.force"),
                RangeHyp("wind.bracket.force.mean", Fraction(3000), Fraction(3000), "in:d.wind.bracket.force.mean"),
            ),
        )

    def test_a_missing_mean_is_not_invented(self):
        no_mean = Input("lift.hook.force", FORCE_IN.range, FORCE_IN.signature, InputKind.ASSUMED, SPAN)
        with self.assertRaises(ValueError):
            builder().mean(no_mean)

    def test_values_and_params(self):
        sb = builder()
        x = sb.value(Fixed(Quantity(point(Fraction(3, 2)), DIMENSIONLESS)), "frame.D.x")
        a = sb.value(ParamRef("size"), "c.w1.area")
        b = sb.value(ParamRef("size"), "c.w2.area")
        self.assertEqual(a, b, "two values naming one param share its hypothesis")
        st = sb.finish(nonpositive(Add((x, a, b))))
        self.assertEqual(
            st.hyps,
            (
                RangeHyp("frame.D.x", Fraction(3, 2), Fraction(3, 2), "dsg:d.frame.D.x"),
                RangeHyp("size", AREA_2_5, AREA_16, "par:d.size"),
            ),
        )

    def test_one_symbol_has_one_meaning(self):
        sb = builder()
        sb.value(Fixed(Quantity(point(Fraction(1)), DIMENSIONLESS)), "frame.D.x")
        sb.value(Fixed(Quantity(point(Fraction(1)), DIMENSIONLESS)), "frame.D.x")
        with self.assertRaises(ValueError):
            sb.value(Fixed(Quantity(point(Fraction(2)), DIMENSIONLESS)), "frame.D.x")


class BuilderFinish(unittest.TestCase):
    def test_hyps_are_sorted_and_unused_ones_dropped(self):
        sb = builder()
        fy = sb.registry("steel.S355", "fy")
        sb.registry("steel.S355", "G")
        force = sb.input(FORCE_IN)
        st = sb.finish(nonpositive(Add((force, Neg(fy)))))
        self.assertEqual([h.sym for h in st.hyps], ["steel.S355.fy", "wind.bracket.force"])

    def test_a_defined_quantity_keeps_the_hyps_its_definition_uses(self):
        sb = builder()
        force = sb.input(FORCE_IN)
        fy = sb.registry("steel.S355", "fy")
        problem = QuadraticProblem(B=Matrix(1, 1, ((0, 0, Fraction(1)),)), f=(force,), w=(fy,))
        n = sb.defined("frame.n0", MinimizerComponent(problem, 0, Const(Fraction(1))))
        st = sb.finish(nonpositive(n))
        self.assertEqual([h.sym for h in st.hyps], ["frame.n0", "steel.S355.fy", "wind.bracket.force"])
        self.assertIsInstance(st.hyps[0], DefinedHyp)

    def test_symbols_the_goal_binds_need_no_hypothesis(self):
        sb = builder()
        load = sb.input(FORCE_IN)
        mean = sb.mean(FORCE_IN)
        goal = MomentBound(
            random=(RandomVar("x", load, load),),
            moments=(MomentConstraint(Sym("x"), mean, mean),),
            fail=Add((Sym("x"), Neg(Const(Fraction(36000))))),
            p=Fraction(3, 10),
        )
        self.assertEqual([h.sym for h in sb.finish(goal).hyps], ["wind.bracket.force", "wind.bracket.force.mean"])

    def test_a_symbol_no_hypothesis_introduces_is_refused(self):
        with self.assertRaises(ValueError):
            builder().finish(nonpositive(Sym("x")))

    def test_only_registered_goals(self):
        with self.assertRaises(TypeError):
            builder().finish(Sym("x"))

    def test_single_use(self):
        sb = builder()
        sb.finish(nonpositive(Const(Fraction(-1))))
        with self.assertRaises(RuntimeError):
            sb.input(FORCE_IN)
        with self.assertRaises(RuntimeError):
            sb.finish(nonpositive(Const(Fraction(-1))))


class NoBareNumbers(unittest.TestCase):
    INTRODUCERS = {"registry", "input", "mean", "tests", "value", "param", "defined"}

    def test_every_way_to_introduce_a_hypothesis_refuses_a_bare_number(self):
        public = {name for name in vars(StatementBuilder) if not name.startswith("_")}
        self.assertEqual(public, self.INTRODUCERS | {"finish"}, "a new builder method needs a bare-number check here")
        n = Fraction(12000)
        calls = {
            "registry": lambda sb: sb.registry(n, "fy"),
            "input": lambda sb: sb.input(n),
            "mean": lambda sb: sb.mean(n),
            "tests": lambda sb: sb.tests(n),
            "value": lambda sb: sb.value(n, "frame.D.x"),
            "param": lambda sb: sb.param(n),
            "defined": lambda sb: sb.defined("frame.n0", n),
        }
        self.assertEqual(set(calls), self.INTRODUCERS)
        for name, call in calls.items():
            with self.assertRaises(TypeError, msg=name):
                call(builder())

    def test_typed_sources_are_accepted(self):
        sb = builder()
        self.assertEqual(sb.input(FORCE_IN), Sym("wind.bracket.force"))
        self.assertEqual(sb.param(DESIGN.params["size"]), Sym("size"))


if __name__ == "__main__":
    unittest.main()
