"""Bolted joints: lowering, the tension obligation, coverage, and the stored certificate,
through the elaborator, the R4 solver and kernel.check. Owner: C.

Hand values (ISO 724: d2 = d - 0.649519 P, d3 = d - 1.226869 P, As = pi/4 ((d2 + d3)/2)^2):
    M12 (P 1.75 mm): As = 84.26654 mm2;  M10 (P 1.5 mm): As = 57.98960 mm2
    worst corner of bolt_unknown.lola: T = 50 Nm, K = 0.16, Phi = 0.25, F = 12 kN
    M12: F_V = T / (K d) = 26041.667 N;  F_bolt = F_V + Phi F = 29041.667 N
         0.9 Rp02 As = 0.9 x 450 MPa x As = 34127.948 N  -> margin -5086.281 N
         Rp02 As = 37919.942 N -> margin -8878.276 N;  Sp(8.8) As = 580 MPa x As = 48874.592 N
    M10: F_V = 31250 N;  F_bolt = 34250 N;  0.9 Rp02 As = 23485.787 N -> margin +10764.213 N
"""
import dataclasses
import json
import unittest
from fractions import Fraction
from pathlib import Path

from lola import coverage, models
from lola.kernel import Interval, Refutation, Rejection, Theorem, check, decode_evidence, decode_statement, statement_hash
from lola.lang import load_design, parse_design
from lola.models import bolt
from lola.models.base import (
    CONTACT_PAIR,
    GALVANIC_CORROSION,
    ClaimOrigin,
    ComponentError,
    CoverageOrigin,
    Gap,
    NeedsInputBound,
    NoRuleForQuantity,
    Obligation,
)
from lola.premises import Tag
from lola.registry import Material, Process, ProcessKind, Stated, build_registry
from lola.solvers import r4_enclosure

from tests.test_circuit import at

REGISTRY = build_registry()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
EXAMPLE = EXAMPLES / "bolt_unknown.lola"
CERT = EXAMPLES / "bolt_tension.cert.json"

WORST = {"bracket.torque": 50, "bracket.nut_factor": Fraction(4, 25), "bracket.load_share": Fraction(1, 4), "wind.bracket.force": 12000}


def joint(*edits: tuple[str, str], extra: str = ""):
    text = EXAMPLE.read_text(encoding="utf-8")
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"{old!r} is not in bolt_unknown.lola")
        text = text.replace(old, new)
    return parse_design(text + extra, "joint.lola", REGISTRY)


def lowered(design) -> dict:
    return {name: bolt.lower_joint(c, design, REGISTRY) for name, c in design.components.items()}


def requirements(design) -> tuple:
    return coverage.generate(design, lowered(design), REGISTRY)


def tension(design, origin: str = "tension"):
    """The one tension result of the requirement from `origin` (a claim name or rule id)."""
    model = lowered(design)
    found = []
    for req in requirements(design):
        name = req.origin.claim if isinstance(req.origin, ClaimOrigin) else req.origin.rule
        if req.mode == bolt.TENSION and name == origin:
            found += bolt.build_tension(req, model[req.subject[0]], design, REGISTRY)
    if len(found) != 1:
        raise AssertionError(f"{len(found)} tension results from {origin}")
    return found[0]


def solved(ob: Obligation):
    (evidence,) = r4_enclosure.solve(ob.statement)
    return check(ob.statement, evidence), evidence


class BoltUnknown(unittest.TestCase):
    def test_the_joint_lowers_to_its_bolt_plates_and_signed_inputs(self):
        model = lowered(load_design(EXAMPLE, REGISTRY))["bracket"]
        self.assertEqual((model.bolt, model.count), ("bolt.M12_A4_70", 1))
        self.assertEqual([(p.material, p.thickness.quantity.value.lo, p.process) for p in model.plates],
                         [("aluminium.6061_T6", Fraction(1, 100), None)] * 2)
        self.assertEqual((model.torque.name, model.nut_factor.name, model.load_share.name),
                         ("bracket.torque", "bracket.nut_factor", "bracket.load_share"))

    def test_the_tension_claim_is_a_theorem_with_the_hand_margin(self):
        ob = tension(load_design(EXAMPLE, REGISTRY))
        self.assertIsInstance(solved(ob)[0], Theorem)
        self.assertAlmostEqual(at(ob.statement, 0, WORST), -5086.281, places=2)
        self.assertEqual(ob.model.id, "bolt.tension")

    def test_every_input_enters_as_a_labelled_hypothesis(self):
        ob = tension(load_design(EXAMPLE, REGISTRY))
        self.assertEqual({h.label for h in ob.statement.hyps}, {
            "in:mast-bracket-coastal.bracket.torque",
            "in:mast-bracket-coastal.bracket.nut_factor",
            "in:mast-bracket-coastal.bracket.load_share",
            "in:mast-bracket-coastal.wind.bracket.force",
            "dsg:mast-bracket-coastal.bracket.count",
            "reg:const.iso261.M12.d",
            "reg:const.iso261.M12.pitch",
            "reg:const.iso724.d2_coefficient",
            "reg:const.iso724.d3_coefficient",
            "reg:bolt.M12_A4_70.Rp02_min",
        })

    def test_coverage_leaves_galvanic_corrosion_and_plate_bearing_open(self):
        reqs = requirements(load_design(EXAMPLE, REGISTRY))
        self.assertEqual([(r.subject, r.mode, type(r.origin)) for r in reqs], [
            (("bracket",), bolt.TENSION, ClaimOrigin),
            (("bracket",), bolt.PLATE_BEARING, CoverageOrigin),
            (("bracket",), GALVANIC_CORROSION, CoverageOrigin),
        ])
        self.assertTrue({GALVANIC_CORROSION, bolt.PLATE_BEARING} <= models.UNMODELLED)

    def test_in_a_dry_room_the_same_pair_raises_no_galvanic_demand(self):
        reqs = requirements(joint(("environment marine_c5", "environment indoor_dry")))
        self.assertNotIn(GALVANIC_CORROSION, [r.mode for r in reqs])

    def test_a_claim_looser_than_the_proof_load_keeps_the_coverage_demand(self):
        d = joint(("tension_utilisation <= 0.9", "tension_utilisation <= 1.1"))
        self.assertEqual([r.origin for r in requirements(d) if r.mode == bolt.TENSION],
                         [ClaimOrigin("tension"), CoverageOrigin("bolt.tension")])
        ob = tension(d, "bolt.tension")
        self.assertAlmostEqual(at(ob.statement, 0, WORST), -8878.276, places=2)

    def test_features_pair_the_bolt_with_each_plate_and_the_plates_with_each_other(self):
        d = load_design(EXAMPLE, REGISTRY)
        found = bolt.features(lowered(d)["bracket"], d, REGISTRY)
        self.assertEqual([(f.subject, f.kind, f.materials, f.environment) for f in found], [
            (("bracket",), bolt.BOLTED_JOINT, ("stainless.A4", "aluminium.6061_T6"), "marine_c5"),
            (("bracket",), CONTACT_PAIR, ("stainless.A4", "aluminium.6061_T6"), "marine_c5"),
            (("bracket",), CONTACT_PAIR, ("aluminium.6061_T6", "aluminium.6061_T6"), "marine_c5"),
        ])


CADMIUM = dataclasses.replace(
    REGISTRY,
    materials={**REGISTRY.materials, "cadmium.electroplate": Material("cadmium.electroplate", "cadmium", "ISO 2082", {
        "anodic_index": Stated(Interval(Fraction(19, 20), Fraction(19, 20)), "V", Tag.JUDGED, "test.registry@example.org",
                               "MIL-STD-889 anodic index, cadmium plated and chromate", "anodic index of the plated surface"),
    })},
    processes={**REGISTRY.processes,
               "process.cadmium_plate": Process("process.cadmium_plate", ProcessKind.COATING, {}, surface="cadmium.electroplate")},
    parts={**REGISTRY.parts, "bolt.M12_A4_70_cd": dataclasses.replace(
        REGISTRY.parts["bolt.M12_A4_70"], id="bolt.M12_A4_70_cd", process="process.cadmium_plate")},
)
"""The shipped registry plus a cadmium-plated A4 bolt, a coating the shipped set lacks."""


class Galvanic(unittest.TestCase):
    """The contact pairs name each part's exposed surface. MIL-STD-889 anodic indices:
    zinc plated 1.25 V, plain carbon steel 0.85 V, wrought 6061 aluminium 0.90 V, 18 % Cr
    stainless 0.50 V, cadmium plated and chromate 0.95 V. The limit in wet marine_c5 is
    0.15 V."""

    def demanded(self, design, registry=REGISTRY) -> bool:
        models = {name: bolt.lower_joint(c, design, registry) for name, c in design.components.items()}
        return GALVANIC_CORROSION in [r.mode for r in coverage.generate(design, models, registry)]

    def pairs(self, design, registry=REGISTRY) -> list:
        model = bolt.lower_joint(design.components["bracket"], design, registry)
        return [f.materials for f in bolt.features(model, design, registry) if f.kind == CONTACT_PAIR]

    def test_a_zinc_plated_bolt_in_steel_plates_makes_a_dissimilar_pair(self):
        """Zinc 1.25 against S355 0.85: 0.40 V apart. The bare 8.8 bolt is 0.85 against
        0.85."""
        zinc = joint(("bolt.M12_A4_70", "bolt.M12_8_8_zn"), ("plate aluminium.6061_T6", "plate steel.S355"))
        self.assertEqual(self.pairs(zinc), [("zinc.electroplate", "steel.S355"), ("steel.S355", "steel.S355")])
        self.assertTrue(self.demanded(zinc))
        bare = joint(("bolt.M12_A4_70", "bolt.M12_8_8"), ("plate aluminium.6061_T6", "plate steel.S355"))
        self.assertEqual(self.pairs(bare), [("steel.bolt_qt", "steel.S355"), ("steel.S355", "steel.S355")])
        self.assertFalse(self.demanded(bare))

    def test_a_zinc_plated_plate_shows_zinc_to_the_bolt_and_to_the_other_plate(self):
        """Zinc 1.25 against the bolt's 0.85 and the bare plate's 0.85: 0.40 V apart."""
        d = joint(("bolt.M12_A4_70", "bolt.M12_8_8"), ("plate aluminium.6061_T6", "plate steel.S355"),
                  ("thickness 10 mm\n  plate", "thickness 10 mm process process.zinc_plate\n  plate"))
        self.assertEqual(self.pairs(d), [("steel.bolt_qt", "zinc.electroplate"), ("steel.bolt_qt", "steel.S355"),
                                         ("zinc.electroplate", "steel.S355")])
        self.assertTrue(self.demanded(d))

    def test_a_cadmium_plated_stainless_bolt_in_aluminium_plates_removes_the_pair(self):
        """Cadmium 0.95 against 6061 0.90: 0.05 V apart. The bare A4 bolt is 0.50 against
        0.90, 0.40 V apart."""
        text = EXAMPLE.read_text(encoding="utf-8")
        plated = parse_design(text.replace("bolt.M12_A4_70", "bolt.M12_A4_70_cd"), "joint.lola", CADMIUM)
        self.assertEqual(self.pairs(plated, CADMIUM), [("cadmium.electroplate", "aluminium.6061_T6"),
                                                        ("aluminium.6061_T6", "aluminium.6061_T6")])
        self.assertFalse(self.demanded(plated, CADMIUM))
        bare = parse_design(text, "joint.lola", CADMIUM)
        self.assertTrue(self.demanded(bare, CADMIUM))


class Tension(unittest.TestCase):
    def test_an_m10_bolt_is_refuted_at_the_worst_corner(self):
        ob = tension(joint(("bolt.M12_A4_70", "bolt.M10_A4_70")))
        result, evidence = solved(ob)
        self.assertIsInstance(result, Refutation)
        point = dict(result.point)
        self.assertEqual({k: point[k] for k in WORST}, WORST)
        self.assertAlmostEqual(at(ob.statement, evidence.body.which, point), 10764.213, places=2)

    def test_a_force_claim_bounds_the_bolt_force_itself(self):
        held = tension(joint(("tension_utilisation <= 0.9", "bolt_tension <= 30 kN")))
        self.assertAlmostEqual(at(held.statement, 0, WORST), 29041.667 - 30000, places=2)
        self.assertIsInstance(solved(held)[0], Theorem)
        broken = tension(joint(("tension_utilisation <= 0.9", "bolt_tension <= 29 kN")))
        self.assertIsInstance(solved(broken)[0], Refutation)

    def test_a_class_with_a_proof_stress_uses_sp(self):
        ob = tension(joint(("bolt.M12_A4_70", "bolt.M12_8_8"), ("tension_utilisation <= 0.9", "tension_utilisation <= 1")))
        labels = {h.label for h in ob.statement.hyps}
        self.assertIn("reg:bolt.M12_8_8.Sp", labels)
        self.assertNotIn("reg:bolt.M12_8_8.Rp02_min", labels)
        self.assertAlmostEqual(at(ob.statement, 0, WORST), 29041.667 - 48874.592, places=2)

    def test_two_bolts_share_the_external_force(self):
        ob = tension(joint(("count 1", "count 2")))
        self.assertAlmostEqual(at(ob.statement, 0, WORST), 26041.667 + 1500 - 34127.948, places=2)

    def test_a_missing_input_is_a_gap_naming_it(self):
        gap = tension(joint(('  torque in [40 Nm, 50 Nm] signed "fitter.lead@example.org" source "assembly spec AS-12 rev C"\n', "")))
        self.assertIsInstance(gap, Gap)
        self.assertEqual(gap.needs, (NeedsInputBound(("bracket",), "torque", "Nm"),))

    def test_a_missing_force_is_a_gap_naming_it(self):
        d = joint(("load wind {\n  on bracket force in [0 kN, 12 kN]\n  signed \"client.structures@example.org\" source \"wind study WS-4, 50-year return\"\n}\n", ""),
                  (" under wind", ""))
        self.assertEqual(tension(d).needs, (NeedsInputBound(("bracket",), "force", "N"),))

    def test_a_lower_bound_on_tension_is_a_gap(self):
        gap = tension(joint(("tension_utilisation <= 0.9", "tension_utilisation >= 0.1")))
        self.assertIsInstance(gap.needs[0], NoRuleForQuantity)


class Lowering(unittest.TestCase):
    def assertRejected(self, *edits, fragment: str, extra: str = ""):
        with self.assertRaises(ComponentError) as ctx:
            lowered(joint(*edits, extra=extra))
        self.assertTrue(any(fragment in p for p in ctx.exception.problems), ctx.exception.problems)

    def test_accepts_a_coated_bolt(self):
        self.assertEqual(lowered(joint(("bolt.M12_A4_70", "bolt.M12_8_8_zn")))["bracket"].bolt, "bolt.M12_8_8_zn")

    def test_accepts_a_coated_plate(self):
        model = lowered(joint(("thickness 10 mm\n  plate", "thickness 10 mm process process.zinc_plate\n  plate")))["bracket"]
        self.assertEqual([p.process for p in model.plates], ["process.zinc_plate", None])

    def test_rejects_an_install_process_on_a_plate(self):
        self.assertRejected(("thickness 10 mm\n  plate", "thickness 10 mm process install.clipped_direct\n  plate"),
                            fragment="coating, cut or weld process; install.clipped_direct is install")

    def test_accepts_a_welded_plate(self):
        model = lowered(joint(("thickness 10 mm\n  plate", "thickness 10 mm process process.mig_weld_6xxx\n  plate")))["bracket"]
        self.assertEqual(model.plates[0].process, "process.mig_weld_6xxx")

    def test_rejects_a_single_plate(self):
        self.assertRejected(("  plate aluminium.6061_T6 thickness 10 mm\n  plate", "  plate"), fragment="at least two plates")

    def test_rejects_a_second_bolt_line(self):
        self.assertRejected(("  bolt bolt.M12_A4_70 count 1\n", "  bolt bolt.M12_A4_70 count 1\n  bolt bolt.M10_A4_70 count 1\n"), fragment="exactly one bolt line")

    def test_rejects_a_registry_id_of_the_wrong_kind(self):
        self.assertRejected(("bolt.M12_A4_70", "cable.cu_pvc_2_5"), fragment="not a bolt")

    def test_rejects_a_fractional_count(self):
        self.assertRejected(("count 1", "count 1.5"), fragment="whole number")

    def test_rejects_a_load_share_outside_zero_to_one(self):
        self.assertRejected(("[0.10, 0.25]", "[0.10, 1.25]"), fragment="within [0, 1]")

    def test_rejects_a_load_field_other_than_force(self):
        self.assertRejected(("on bracket force", "on bracket moment"), fragment="load field is force")

    def test_rejects_an_unknown_joint_quantity(self):
        self.assertRejected(("tension_utilisation <= 0.9", "slip <= 0.9"), fragment="unknown joint quantity")

    def test_rejects_a_force_claim_without_a_force(self):
        self.assertRejected(("tension_utilisation <= 0.9", "bolt_tension <= 0.9"), fragment="bounded by a force")


class Certificate(unittest.TestCase):
    def setUp(self):
        self.stored = json.loads(CERT.read_text(encoding="utf-8"))
        self.fresh = tension(load_design(EXAMPLE, REGISTRY)).statement

    def test_the_stored_certificate_is_for_the_fresh_statement_and_checks(self):
        statement = decode_statement(self.stored["statement"])
        self.assertEqual(statement, self.fresh)
        self.assertEqual(self.stored["statement_hash"], statement_hash(self.fresh))
        self.assertIsInstance(check(self.fresh, decode_evidence(self.stored["evidence"])), Theorem)

    def test_the_stored_evidence_does_not_prove_a_bigger_torque(self):
        d = joint(("[40 Nm, 50 Nm]", "[40 Nm, 80 Nm]"))
        bigger = tension(d).statement
        self.assertNotEqual(statement_hash(bigger), self.stored["statement_hash"])
        self.assertIsInstance(check(bigger, decode_evidence(self.stored["evidence"])), Rejection)


if __name__ == "__main__":
    unittest.main()
