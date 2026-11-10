"""The task generators (bench/tasks.py): what they generate, and that every legal fill is a
design.

examples/circuit_pass.petra (B10, 2.5 mm2 Cu/PVC clipped direct, 18 m, a 75 degC lever
terminal, 10 A, ambient up to 40 degC, fault level up to 6 kA) passes, and every bound it
checks grows with the draw, the run, the ambient and the fault level, so the same parts
pass any task with at most 10 A over at most 18 m.
"""
import unittest
from fractions import Fraction

from bench.tasks import GENERATORS, family_text, fill, generate
from petra.lang import parse_design
from petra.models import DOMAINS
from petra.registry import PartKind, build_registry

REGISTRY = build_registry()
PASSING = {"cb1.part": "mcb.B10", "w1.cable": "cable.cu_pvc_2_5", "t1.part": "terminal.lever_4mm2_75C"}
SMALL = next(seed for seed in range(500)
             if (lambda g: int(g["current"]) <= 10 and int(g["length"]) <= 18)(dict(generate("circuit", seed, REGISTRY).given)))


class Tasks(unittest.TestCase):
    def test_generators_cover_registered_domains_only(self):
        self.assertTrue(set(GENERATORS) <= set(DOMAINS), "every generator names a registered domain")
        self.assertEqual(set(GENERATORS), {"circuit", "bolt"}, "v0 generates circuit and bolt tasks")

    def test_generation_is_deterministic_in_the_seed(self):
        for domain in GENERATORS:
            self.assertEqual(generate(domain, 5, REGISTRY), generate(domain, 5, REGISTRY), f"{domain} seed 5 repeats")
            self.assertGreater(len({generate(domain, s, REGISTRY).template for s in range(10)}), 1, f"{domain} seeds vary the task")

    def test_an_unknown_domain_is_refused(self):
        with self.assertRaises(KeyError):
            generate("hydraulics", 0, REGISTRY)

    def test_every_legal_fill_parses_with_the_owner_claims(self):
        for domain in GENERATORS:
            for seed in range(3):
                task = generate(domain, seed, REGISTRY)
                design = parse_design(fill(task, {h.name: h.choices[-1] for h in task.holes}), "filled.petra", REGISTRY)
                self.assertTrue(design.claims, f"{task.id} keeps its claims")

    def test_choices_are_registry_parts_cheapest_first(self):
        task = generate("circuit", 0, REGISTRY)
        cables = next(h for h in task.holes if h.name == "w1.cable").choices
        areas = [REGISTRY.parts[c].fixes["area"].lo for c in cables]
        self.assertEqual(areas, sorted(areas), "cables run from the smallest area up")
        self.assertEqual(areas[0], Fraction(3, 2_000_000), "1.5 mm2 is the cheapest cable")
        bolts = next(h for h in generate("bolt", 0, REGISTRY).holes if h.name == "j.bolt").choices
        self.assertTrue(all(REGISTRY.parts[b].kind is PartKind.BOLT for b in bolts), "bolt choices are bolts")
        self.assertFalse(any(b.endswith("_zn") for b in bolts), "coated bolts, which lowering refuses, are not offered")

    def test_fill_refuses_choices_outside_the_holes(self):
        task = generate("circuit", 0, REGISTRY)
        for bad in ({**PASSING, "w1.cable": "cable.unobtainium"}, {k: v for k, v in PASSING.items() if k != "t1.part"}, {**PASSING, "extra": "x"}):
            with self.assertRaises(ValueError, msg=f"{bad} is refused"):
                fill(task, bad)

    def test_a_family_text_widens_the_owner_inputs(self):
        task = generate("circuit", SMALL, REGISTRY)
        box = {"draw": (Fraction(0), Fraction(10)), "run": (Fraction(0), Fraction(18)), "amb": (Fraction(5), Fraction(40))}
        design = parse_design(family_text(task, PASSING, box), "family.petra", REGISTRY)
        self.assertTrue(design.is_family, "the widened design is a family")
        self.assertEqual(set(design.params), {"draw", "run", "amb"}, "with one param per widened input")
        with self.assertRaises(ValueError):
            family_text(task, PASSING, {"draw": (Fraction(0), Fraction(10))})


if __name__ == "__main__":
    unittest.main()
