"""The metamorphic relations (scripts/metamorphic.py, docs/metamorphic.md). On one design of
each kind from the gate's stream Petra breaks no relation outside the exemption table, and a
fault planted for each relation is caught by it. The faults are patched in here and never
shipped. The dispatch workflow runs the relations over the whole stream."""
import importlib
import importlib.util
import re
import sys
import unittest
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from unittest import mock

import twin.card
from petra.kernel import Interval
from petra.mechanics import c, div, mul
from petra.models.steel import checks as C
from petra.models.steel import limits as L
from petra.models.steel.fatigue import GENERATORS
from petra.models.steel.generate import generate
from petra.registry import build_registry
from petra.registry.steel import INCH
from petra.units import CUSTOMARY, Quantity

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = build_registry()
DOC = ROOT / "docs" / "metamorphic.md"
LOWERING = importlib.import_module("petra.lang.lower")    # petra.lang's `lower` names a function


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module    # its dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


R = _load("metamorphic")
KINDS = 11
"""The stream deals the kinds in turn, so its first 11 designs are one of each."""
SHEAR_TAB, DOUBLE_ANGLE, SINGLE_ANGLE, STIFFENED_SEAT = 0, 1, 2, 6


def design(i: int):
    return next(generate(1, 1, REGISTRY, i))


def broken(i: int, relation: str, oracle: str = "petra") -> list[dict]:
    row = R.assess(design(i), REGISTRY, [R.BY_NAME[relation]], with_twin=oracle == "twin")
    return row["relations"][relation][oracle]["broken"]


class Stream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [R.assess(design(i), REGISTRY, R.RELATIONS) for i in range(KINDS)]

    def test_one_design_of_each_kind_meets_every_relation(self):
        self.assertEqual(len({row["kind"] for row in self.rows}), KINDS)
        ran = {name for row in self.rows for name in row["relations"]}
        self.assertEqual(ran, set(R.BY_NAME))
        compared = {name for row in self.rows for name, found in row["relations"].items()
                    if found.get("twin", {}).get("status") == "checked"}
        self.assertEqual(set(R.BY_NAME) - compared, {"stiffener_thicker"}, "the twin does not model a stiffened seat")

    def test_petra_breaks_no_relation_outside_the_exemptions(self):
        for row in self.rows:
            for name, found in row["relations"].items():
                with self.subTest(design=row["name"], relation=name):
                    self.assertEqual(R.unexplained(found), [])

    def test_the_exemptions_are_used_here(self):
        used = {int(i) for row in self.rows for found in row["relations"].values() for i in found["petra"]["exempt"]}
        self.assertGreaterEqual(len(used), 10)

    def test_the_twin_reads_a_restated_design_the_same(self):
        for row in self.rows:
            for name in ("units_mm_kn", "units_ft_lbf"):
                found = row["relations"][name].get("twin")
                if found is not None:
                    with self.subTest(design=row["name"], relation=name):
                        self.assertEqual(found["broken"], [])


class Faults(unittest.TestCase):
    """Each fault turns a check the wrong way, in both the design and its variant."""

    def assertCaught(self, found: list[dict], mode: str, what: str = "rose"):
        self.assertTrue(any(b["mode"] == mode and b["what"].startswith(what) for b in found), found)

    def test_a_capacity_that_falls_as_the_plate_thickens(self):
        shear_yield, area = L.shear_yield, c(INCH * INCH)
        inverted = lambda k, fy, agv: shear_yield(k, fy, div(mul(area, area), agv))  # noqa: E731
        with mock.patch.object(L, "shear_yield", inverted):
            self.assertCaught(broken(SHEAR_TAB, "plate_thicker"), "shear_yield")
            self.assertCaught(broken(SHEAR_TAB, "web_thicker"), "shear_yield")

    def test_a_capacity_that_falls_as_fy_rises(self):
        shear_yield, fy0 = L.shear_yield, c(36 * CUSTOMARY["ksi"][0])
        inverted = lambda k, fy, agv: shear_yield(k, div(mul(fy0, fy0), fy), agv)  # noqa: E731
        with mock.patch.object(L, "shear_yield", inverted):
            self.assertCaught(broken(SHEAR_TAB, "fy_up"), "shear_yield")
            self.assertCaught(broken(DOUBLE_ANGLE, "grade_up"), "shear_yield")

    def test_a_group_that_weakens_as_bolts_are_added(self):
        group_total = C.group_total
        inverted = lambda ctx, itf: div(group_total(ctx, itf), c(itf.n * itf.n))  # noqa: E731
        with mock.patch.object(C, "group_total", inverted):
            self.assertCaught(broken(DOUBLE_ANGLE, "rows_plus_one"), "bolts")

    def test_a_force_unit_read_with_a_rounded_factor(self):
        parse_quantity = LOWERING.parse_quantity

        def rounded(number: str, unit: str | None) -> Quantity:
            q = parse_quantity(number, unit)
            if unit != "kN":
                return q
            v = q.value.lo * R.KN_PER_KIP / Fraction("4.45")
            return Quantity(Interval(v, v), q.dim)

        with mock.patch.object(LOWERING, "parse_quantity", rounded):
            self.assertCaught(broken(SHEAR_TAB, "units_mm_kn"), "bolts", "changed")
            self.assertEqual(broken(SHEAR_TAB, "units_ft_lbf"), [])

    def test_a_length_unit_slip_in_the_twin(self):
        with mock.patch.dict(twin.card.UNITS, {"mm": ("length", Fraction(1, 25))}):
            self.assertTrue(broken(SHEAR_TAB, "units_mm_kn", "twin"))

    def test_an_edge_distance_read_from_the_beams_top_only(self):
        beam_web_ply = C._beam_web_ply

        def top_only(ctx, beam, props, columns):
            ply = beam_web_ply(ctx, beam, props, columns)
            return ply if ply.block else replace(ply, edges_min=ply.edges_min + (("beam top", ply.edge),))

        with mock.patch.object(C, "_beam_web_ply", top_only):
            self.assertCaught(broken(SINGLE_ANGLE, "mirror"), "edge_min", "changed")


class KnownDefects(unittest.TestCase):
    """Each defect in R.DEFECTS on a design of the stream where it shows. A fix turns the
    test into an unexpected success: then drop the defect and its test."""

    EXTENDED_PLATE = 1210
    """An extended single plate, PL1/4 x 21 in in A572 Gr. 50 with a = 7.5 in. Lb d/t^2 is 2520
    in, 4.34 E/Fy, so Eq 10-8's Mc is Eq F11-3 read past its range."""

    def test_the_stream_design_shows_the_defect(self):
        found = broken(self.EXTENDED_PLATE, "fy_up")
        self.assertEqual([b.get("defect") for b in found], [0])
        self.assertEqual(R.unexplained({"petra": {"broken": found}}), [])

    @unittest.expectedFailure
    def test_eq_10_8_does_not_fall_as_fy_rises(self):
        self.assertEqual(broken(self.EXTENDED_PLATE, "fy_up"), [])

    @unittest.expectedFailure
    def test_eq_10_8_does_not_fall_as_a_slender_plate_thickens(self):
        """The same plate at 3/16 in: Lb d/t^2 is 7.72 E/Fy, past 5.55 E/Fy, where Eq F11-3 is
        negative and its size grows as the plate thins."""
        g = design(self.EXTENDED_PLATE)
        g = replace(g, text=g.text.replace("thickness 0.25 inch", "thickness 0.1875 inch"))
        row = R.assess(g, REGISTRY, [R.BY_NAME["plate_thicker"]], with_twin=False)
        self.assertEqual(row["relations"]["plate_thicker"]["petra"]["broken"], [])


class Judging(unittest.TestCase):
    FILLET = ("ductility", "plate: fillet at least 5/8 of the plate thickness (Manual Part 10)", 0)
    RUPTURE = ("shear_rupture", "beam web: shear rupture of the net section (J4.2b)", 0)

    def judge(self, relation: str, key, base: R.Check, new: R.Check, status: str = "PASS",
              failing: tuple[str, ...] = ()) -> R.Judged:
        return R.judge(R.BY_NAME[relation], "petra", R.Read("PASS", {key: base}), R.Read(status, {key: new}, failing),
                       R.POINT)

    def test_an_exemption_that_holds_capacity_lets_only_the_demand_rise(self):
        base = R.Check(0.5, False, 0.25, 0.5)
        self.assertEqual(self.judge("plate_thicker", self.FILLET, base, R.Check(0.6, False, 0.3, 0.5)).broken, [])
        found = self.judge("plate_thicker", self.FILLET, base, R.Check(0.6, False, 0.25, 0.25 / 0.6)).broken
        self.assertEqual([b["what"] for b in found], ["rose, capacity fell"])

    def test_an_exemption_that_holds_nothing_lets_the_capacity_fall(self):
        found = self.judge("rows_plus_one", self.RUPTURE, R.Check(0.5, False, 10, 20), R.Check(0.6, False, 10, 10 / 0.6))
        self.assertEqual(found.broken, [])
        self.assertEqual(sum(found.exempt.values()), 1)

    def test_an_exemption_covers_only_its_relations(self):
        found = self.judge("fy_up", self.FILLET, R.Check(0.5, False, 0.25, 0.5), R.Check(0.6, False, 0.3, 0.5))
        self.assertEqual([b["what"] for b in found.broken], ["rose"])

    def test_a_pass_turned_fail_needs_a_check_to_carry_it(self):
        same = R.Check(0.5, False, 0.25, 0.5)
        found = self.judge("fy_up", self.FILLET, same, same, "FAIL", ("bolts",))
        self.assertTrue(found.flip)
        self.assertEqual([b["what"] for b in found.broken], ["verdict"])
        found = self.judge("plate_thicker", self.FILLET, same, R.Check(1.2, False, 0.6, 0.5), "FAIL", ("ductility",))
        self.assertEqual(found.broken, [])

    def test_a_restated_design_must_read_exactly_the_same(self):
        found = R.judge(R.BY_NAME["units_mm_kn"], "petra", R.Read("PASS", {self.FILLET: R.Check(0.5, False, 0.25, 0.5)}),
                        R.Read("PASS", {self.FILLET: R.Check(0.5 + 1e-12, False, 0.25, 0.5)}), 0.0)
        self.assertEqual([b["what"] for b in found.broken], ["changed"])

    def test_the_mirror_swaps_top_for_bottom_in_a_positional_check(self):
        top, bottom = (("beam_fit", f"beam web: {s} bolt hole on the flat web (Manual Part 1)", 0) for s in ("top", "bottom"))
        base = R.Read("PASS", {top: R.Check(0.4, False, 1, 2.5), bottom: R.Check(0.9, False, 1, 1.1)})
        new = R.Read("PASS", {top: R.Check(0.8, False, 1, 1.25), bottom: R.Check(0.5, False, 1, 2)})
        self.assertEqual(R.judge(R.BY_NAME["mirror"], "petra", base, new, R.POINT).broken, [])
        new = R.Read("PASS", {top: R.Check(1.2, False, 1, 1 / 1.2), bottom: R.Check(0.5, False, 1, 2)})
        self.assertEqual([b["what"] for b in R.judge(R.BY_NAME["mirror"], "petra", base, new, R.POINT).broken],
                         ["outcome changed"])


class Exemptions(unittest.TestCase):
    def test_every_exemption_is_narrow_and_cited(self):
        for i, e in enumerate(R.EXEMPT):
            with self.subTest(exemption=i):
                self.assertTrue(e.relations and set(e.relations) <= set(R.BY_NAME))
                self.assertNotIn(R.INVARIANT, {R.BY_NAME[r].kind for r in e.relations},
                                 "a restated design may not move any check")
                self.assertIn(e.oracle, ("petra", "twin"))
                self.assertTrue(e.modes and set(e.modes) <= set(GENERATORS))
                self.assertIn(e.holds, (R.CAPACITY, R.NOTHING))
                self.assertIsNone(re.search(e.check, ""), "a pattern must name something")
                self.assertGreaterEqual(len(e.check), 10)
                self.assertRegex(e.clause, r"AISC 360-22 [A-Z]|AISC Steel Construction Manual")
                self.assertTrue(e.why.endswith("."))

    def test_every_defect_is_narrow(self):
        for i, d in enumerate(R.DEFECTS):
            with self.subTest(defect=i):
                self.assertTrue(d.relations and set(d.relations) <= set(R.BY_NAME))
                self.assertTrue(d.modes and set(d.modes) <= set(GENERATORS))
                self.assertIsNone(re.search(d.check, ""))
                self.assertGreaterEqual(len(d.check), 10)
                self.assertTrue(d.finding.endswith("."))


class Published(unittest.TestCase):
    @unittest.skipUnless(DOC.exists(), "docs/metamorphic.md is written by scripts/metamorphic.py")
    def test_the_published_run_holds_and_matches_the_table(self):
        text = DOC.read_text(encoding="utf-8")
        n = int(re.search(r"The designs are the first (\d+) of seed 1's stream", text).group(1))
        self.assertGreaterEqual(n, 10000)
        self.assertRegex(text, r"Petra broke a relation outside the exemption table on \d+ designs\. On \d+ of them "
                               r"every break is a known defect, so 0 are unexplained\.")
        for title, table in (("Exemptions", R.EXEMPT), ("Known defects", R.DEFECTS)):
            rows = re.findall(r"^\| (\d+) \| .* \| (\d+) \|$", text.split(f"## {title}")[1].split("\n## ")[0], re.M)
            self.assertEqual([int(i) for i, _ in rows], list(range(len(table))), "rerun scripts/metamorphic.py")
            for (i, uses), e in zip(rows, table):
                with self.subTest(table=title, row=int(i)):
                    self.assertIn(f"`{R._cell(e.check)}`", text)
                    self.assertGreater(int(uses), 0, "a row the stream never uses should go")


if __name__ == "__main__":
    unittest.main()
