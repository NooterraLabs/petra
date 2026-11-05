"""Premise, scope-parameter and footprint construction rules. Owner: P."""
import unittest
from fractions import Fraction

from lola.kernel import Interval
from lola.premises import DesignValue, Footprint, LabelKind, Premise, ScopeParam, Tag, label_kind

RANGE = Interval(Fraction(0), Fraction(1))


def premise(label: str, tag: Tag = Tag.ASSUMED, owner: str = "o@example.org", source: str = "s") -> Premise:
    return Premise(label, tag, owner, source, "statement")


class Labels(unittest.TestCase):
    def test_prefix_names_the_kind(self):
        self.assertIs(label_kind("reg:steel.S355.fy"), LabelKind.REGISTRY)
        self.assertIs(label_kind("cert:sha256:ab"), LabelKind.CERT)

    def test_unknown_or_missing_prefix_is_refused(self):
        for bad in ("steel.S355", "foo:bar", "in:", ":x"):
            with self.assertRaises(ValueError, msg=bad):
                label_kind(bad)


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


if __name__ == "__main__":
    unittest.main()
