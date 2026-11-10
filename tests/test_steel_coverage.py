"""Steel coverage from the physics (docs/plan.md P1 item 5): what a connection's parts can
fail by is demanded, or its reason for not arising is recorded, whatever loads the design
declares.
"""
import tempfile
import unittest
from pathlib import Path

import petra

ROOT = Path(__file__).resolve().parents[1]
STEEL = ROOT / "examples" / "steel"


def written(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "design.petra"
        target.write_text(text, encoding="utf-8", newline="\n")
        return petra.check_file(target)


def checks(report, mode: str) -> list[str]:
    return [c["check"] for v in report.to_json()["verdicts"] for o in v["obligations"] if f"/steel.{mode}/" in o["requirement"]
            for c in o["checks"]]


def outcome(report, mode: str) -> str:
    (found,) = {o["outcome"] for v in report.to_json()["verdicts"] for o in v["obligations"] if f"/steel.{mode}/" in o["requirement"]}
    return found


class MaximumSpacing(unittest.TestCase):
    """J3.6 limits the longitudinal spacing of bolts, the pitch along a bolt line, at 24 t
    and 12 in; it says nothing of the gauge across the force (Commentary J3.6). A 1/4 in end
    plate allows 6 in."""

    END_PLATE = (STEEL / "shear_end_plate.petra").read_text(encoding="utf-8")

    def test_a_gauge_past_24_t_is_not_held_to_it(self):
        wide = written(self.END_PLATE.replace("support_gauge 5.5 inch", "support_gauge 6.5 inch").replace(
            "plate_width 8 inch", "plate_width 9 inch"))
        self.assertEqual(outcome(wide, "spacing_max"), "certified")
        self.assertFalse([c for c in checks(wide, "spacing_max") if "gauge" in c])

    def test_a_pitch_past_24_t_fails(self):
        tall = written(self.END_PLATE.replace("pitch 3 inch", "pitch 6.5 inch").replace("rows 4", "rows 2"))
        self.assertEqual(outcome(tall, "spacing_max"), "refuted")

    def test_one_row_has_no_pitch_to_limit(self):
        """A seat bolted to its support by one row of two bolts, the P3 pilot's task 303-003:
        its bolts sit side by side across the reaction, so J3.6 has no pitch to limit. It
        was left open for want of a spacing check; it is not owed, and says why."""
        report = petra.check_file(ROOT / "corpus" / "cases" / "pilot" / "seat_one_row.petra")
        self.assertEqual(report.to_json()["status"], "PASS")
        why = [u["reason"] for u in report.to_json()["unchecked"] if u["mode"] == "steel.spacing_max"]
        self.assertEqual(len(why), 1)
        self.assertIn("no pitch", why[0])
        two = written((STEEL / "seated.petra").read_text(encoding="utf-8"))
        self.assertEqual(outcome(two, "spacing_max"), "certified")


class PanelZone(unittest.TestCase):
    """A flange force may be one flange of a moment connection's couple, which shears the
    column's panel zone (J10.6) whatever loads the design declares. The check reads the
    panel's required shear and the column's axial force, neither of which the force gives:
    left out, each leaves the panel zone open by name, never unchecked or taken as zero."""

    FORCE = (STEEL / "flange_force.petra").read_text(encoding="utf-8")

    def loaded(self, *lines: str):
        return written(self.FORCE.replace("  signed ", "".join(f"  {line}\n" for line in lines) + "  signed ", 1))

    def test_a_force_with_neither_load_leaves_the_panel_zone_open_naming_both(self):
        report = written(self.FORCE)
        self.assertIsInstance(report.verdict, petra.Unknown)
        self.assertEqual(outcome(report, "panel_zone"), "open")
        text = report.render()
        for field in ("panel_shear", "axial"):
            self.assertIn(f"needs signed bound on ff1.{field} [kip]", text)

    def test_each_load_left_out_is_named_alone(self):
        for given, missing in (("on ff1 panel_shear in [0 kip, 100 kip]", "axial"), ("on ff1 axial in [0 kip, 300 kip]", "panel_shear")):
            with self.subTest(missing=missing):
                text = self.loaded(given).render()
                self.assertIn(f"needs signed bound on ff1.{missing} [kip]", text)
                self.assertEqual(text.count("needs signed bound"), 1, text)

    def test_with_both_the_panel_zone_is_checked(self):
        report = self.loaded("on ff1 panel_shear in [0 kip, 100 kip]", "on ff1 axial in [0 kip, 300 kip]")
        self.assertIsInstance(report.verdict, petra.Pass)
        self.assertEqual(outcome(report, "panel_zone"), "certified")

    def test_a_tensile_axial_force_reduces_the_web_as_a_compressive_one_does(self):
        # W14x90: Py = 50 ksi x 26.5 in2 = 1325 kip; 1000 kip is past 0.4 Py, so Eq J10-10 applies.
        def utilisation(axial: str) -> float:
            report = self.loaded("on ff1 panel_shear in [0 kip, 300 kip]", f"on ff1 axial in {axial}")
            (u,) = [c["utilisation"] for v in report.to_json()["verdicts"] for o in v["obligations"]
                    if "/steel.panel_zone/" in o["requirement"] for c in o["checks"]]
            return u
        dc, tw, fy, py = 14.0, 0.44, 50.0, 50.0 * 26.5
        expected = 300 / (0.9 * 0.6 * fy * dc * tw * (1.4 - 1000 / py))
        self.assertAlmostEqual(utilisation("[0 kip, 1000 kip]"), expected, places=3)
        self.assertAlmostEqual(utilisation("[-1000 kip, 0 kip]"), expected, places=3)


class SeatPlate(unittest.TestCase):
    """A stiffened seat's plate bears on the stiffener's fitted top edge. J7 gives the
    bearing strength of the surfaces in contact, so the plate is checked at its own Fy as
    the stiffener is at its: an A36 plate on a Grade 50 stiffener governs."""

    SEAT = (STEEL / "stiffened_seat.petra").read_text(encoding="utf-8")

    def bearing(self, text: str) -> dict[str, float]:
        report = written(text)
        return {c["check"]: c["utilisation"] for v in report.to_json()["verdicts"] for o in v["obligations"]
                if "/steel.bearing/" in o["requirement"] for c in o["checks"]}

    def test_the_seat_plate_and_the_stiffener_each_bear_at_their_own_yield_stress(self):
        found = self.bearing(self.SEAT.replace("stiffener steel.A36", "stiffener steel.A572_50"))
        plate, stiffener = (found[f"{part}: bearing on {edge} fitted top edge (J7)"]
                            for part, edge in (("seat plate", "the stiffener's"), ("stiffener", "its")))
        self.assertAlmostEqual(plate, 60 / (0.75 * 1.8 * 36 * (5 - 0.5) * 0.5), places=4)
        self.assertAlmostEqual(plate / stiffener, 50 / 36, places=6)

    def test_a_soft_seat_plate_fails_where_the_stiffener_would_not(self):
        soft = self.SEAT.replace("stiffener steel.A36", "stiffener steel.A572_50").replace("[0 kip, 60 kip]", "[0 kip, 120 kip]")
        found = self.bearing(soft)
        self.assertGreater(found["seat plate: bearing on the stiffener's fitted top edge (J7)"], 1)
        self.assertLess(found["stiffener: bearing on its fitted top edge (J7)"], 1)
        self.assertEqual(outcome(written(soft), "bearing"), "refuted")


def demand(report, mode: str) -> float:
    (found,) = [c["demand"] for v in report.to_json()["verdicts"] for o in v["obligations"] if f"/steel.{mode}/" in o["requirement"]
                for c in o["checks"]]
    return found


class TeeDuctility(unittest.TestCase):
    """A shear tee's flange must bend as the beam end rotates before its bolts or welds to
    the support fracture: Manual Eq 9-52 (bolted) or 9-51 (welded), with Eq 9-53 the
    alternate where the stem is bolted to the beam, as Companion II.A-30 and II.A-31 apply
    them. The Companion's tee is a WT5x22.5 on a beam with a 0.380 in web, four rows at
    3 in, 1-1/4 in end distances, a 5-1/2 in gauge."""

    TEE = (STEEL / "shear_tee.petra").read_text(encoding="utf-8")
    COMPANION = TEE.replace("WT6x25", "WT5x22_5").replace("beam W18x50", "beam W16x50")

    def test_the_bolted_tee_needs_the_companions_least_bolt(self):
        # II.A-30: b = 2-3/4 - 0.350/2 - 0.380/2 - 13/16 = 1.57 in, p = s = 3 in, l = 11-1/2 in;
        # 0.0941 tf sqrt(...) = 0.810 in, capped at 0.115 sqrt(Fy ts) = 0.481 in.
        report = written(self.COMPANION)
        self.assertAlmostEqual(demand(report, "tee_ductility"), 0.481, places=3)
        self.assertEqual(outcome(report, "tee_ductility"), "certified")

    def test_the_welded_tee_needs_the_companions_least_fillet(self):
        # II.A-31: b = (8.02 - 2 (13/16)) / 2 = 3.20 in; wmin = 0.193 in, under (5/8) ts = 0.219 in.
        welded = self.COMPANION.replace("support_side bolted\n  support_gauge 5.5 inch",
                                        "support_side welded\n  support_weld electrode.E70 size 0.25 inch")
        # The Companion rounds b to 3.20 in; at 3.1975 in wmin is 0.1935 in.
        self.assertAlmostEqual(demand(written(welded), "tee_ductility"), 0.193, delta=0.001)

    def test_a_stiff_welded_tee_fails(self):
        # A WT10.5x36.5 (stem 0.455 in, flange 0.740 in) on a W30x90 (web 0.470 in): both past
        # d/2 + 1/16 = 7/16 in, so Eq 9-53 does not excuse; wmin is about 0.28 in.
        stiff = self.TEE.replace("WT6x25", "WT10_5x36_5").replace("beam W18x50", "beam W30x90").replace(
            "support_side bolted\n  support_gauge 5.5 inch", "support_side welded\n  support_weld electrode.E70 size 0.25 inch")
        self.assertEqual(outcome(written(stiff), "tee_ductility"), "refuted")


class EveryModeOwedOrExplained(unittest.TestCase):
    """Every mode of the steel domain is, for each connection, on its load path
    (domain.required) or given a reason it cannot arise (absent.py), never both and never
    neither, so the readout never says a steel mode is merely not demanded. Held over the
    generator's samplers, rules kept and free, every kind and the details they draw, with
    an axial load on some shear connections and a free end on some flange forces."""

    PER_KIND = 40

    def test_over_the_generators_samples(self):
        import random
        from fractions import Fraction

        from petra.lang import parse_design
        from petra.models.base import ComponentError
        from petra.models.steel import domain, generate as gen
        from petra.pipeline import lower_components
        from petra.registry import build_registry

        registry = build_registry()
        modes = set(domain.DOMAIN.modes)
        seen: dict[str, int] = {}
        for kind, sampler in gen.SAMPLERS.items():
            for i in range(self.PER_KIND):
                rng = random.Random(f"absent:{kind}:{i}")
                s = gen._Sampler(rng, registry)
                sampler(s)
                secondary = list(s.secondary)
                if kind in ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate", "seated",
                            "stiffened_seat") and rng.random() < 0.2:
                    secondary.append(("axial", Fraction(1, 5)))
                lines = [line.replace("end_twist restrained", "end_twist free") if rng.random() < 0.5 else line
                         for line in s.lines]
                text = gen.source(f"absent-{kind}-{i}", kind, rng.choice(("lrfd", "asd")), lines, Fraction(10), tuple(secondary))
                try:
                    design = parse_design(text, "<absent>", registry)
                    conn = lower_components(design, registry)["c1"]
                except ComponentError:
                    continue
                owed = {m for m in modes if m.id.removeprefix("steel.") in set(domain.required(conn, design))}
                why = domain.absent(conn, design)
                with self.subTest(kind=kind, i=i):
                    self.assertFalse(owed & set(why))
                    self.assertEqual(owed | set(why), modes, sorted(m.id for m in modes - owed - set(why)))
                    self.assertTrue(all(why.values()))
                seen[kind] = seen.get(kind, 0) + 1
        self.assertEqual(set(seen), set(gen.SAMPLERS))


def utilisations(report, mode: str) -> dict[str, float]:
    return {c["check"]: c["utilisation"] for v in report.to_json()["verdicts"] for o in v["obligations"]
            if f"/steel.{mode}/" in o["requirement"] for c in o["checks"]}


class SeatShear(unittest.TestCase):
    """A seated beam's end carries its reaction down its web to the seat, so the web yields
    in shear over d tw (J4.2(a)), as a framed beam's does. A stiffened seat's stiffener is
    welded on edge to the support like a bracket plate: its section along the weld carries
    the reaction in shear and, at Table 10-8's 0.8 W from the face, in flexure (J4.5)."""

    SEAT = (STEEL / "seated.petra").read_text(encoding="utf-8")
    STIFFENED = (STEEL / "stiffened_seat.petra").read_text(encoding="utf-8")
    WEB = "beam web: shear yielding of the gross section (J4.2a)"

    def test_a_seated_beams_web_yields_in_shear(self):
        # W16x26: 0.6 (50 ksi)(15.7 in)(0.250 in) = 117.75 kip against 30 kip
        self.assertAlmostEqual(utilisations(written(self.SEAT), "shear_yield")[self.WEB], 30 / 117.75, places=6)

    def test_a_stiffened_seats_beam_web_and_stiffener_yield_in_shear(self):
        found = utilisations(written(self.STIFFENED), "shear_yield")
        self.assertAlmostEqual(found[self.WEB], 60 / (0.6 * 50 * 20.7 * 0.35), places=6)          # W21x44
        self.assertAlmostEqual(found["stiffener: shear yielding of the gross section (J4.2a)"], 60 / (0.6 * 36 * 12 * 0.5), places=6)

    def test_the_stiffener_bends_at_its_weld_line(self):
        # M = 60 kip (0.8)(5 in) = 240 kip-in against 0.9 (36 ksi)(0.5 in)(12 in)^2 / 4
        (u,) = utilisations(written(self.STIFFENED), "flexural_yield").values()
        self.assertAlmostEqual(u, 240 / (0.9 * 36 * 0.5 * 144 / 4), places=6)

    def test_a_short_stiffener_fails_in_flexure(self):
        short = written(self.STIFFENED.replace("stiffener_length 12 inch", "stiffener_length 5 inch"))
        self.assertEqual(outcome(short, "flexural_yield"), "refuted")


class HangerSupportWeb(unittest.TestCase):
    """A hanger's tension pulls the support's flange, which hands it to the support's web:
    J10.2's web local yielding over the bolt rows' extent. The grammar gives no distance to
    the support's end, so Eq J10-3, the lesser, is taken: it holds wherever the hanger is."""

    HANGER = (STEEL / "hanger.petra").read_text(encoding="utf-8")

    def test_the_support_web_yields_under_the_hangers_tension_at_the_end_formula(self):
        # W18x50: 50 ksi (0.355 in)(2.5 (0.972 in) + 3 in) = 96.38 kip against 40 kip
        found = utilisations(written(self.HANGER), "web_local_yielding")
        self.assertAlmostEqual(max(found.values()), 40 / (50 * 0.355 * (2.5 * 0.972 + 3)), places=6)
        self.assertTrue(all(name.startswith("support web: ") for name in found), found)

    def test_a_thin_support_web_fails(self):
        thin = written(self.HANGER.replace("support W18x50 flange", "support W16x26 flange").replace("[0 kip, 40 kip]", "[0 kip, 70 kip]"))
        self.assertEqual(outcome(thin, "web_local_yielding"), "refuted")


class BracketClearance(unittest.TestCase):
    """A bracket's bolts need room to tighten (Manual Part 7) clear of the support's web or
    flanges, at the placement of its columns that leaves the most: centred between a web's
    flanges; on a flange, all on one side of the web, or split across it where that fits. A
    socket on a 7/8 in heavy hex nut needs 1.4375 / sqrt 3 + 1/2 = 1.330 in."""

    BRACKET = (STEEL / "bolt_bracket.petra").read_text(encoding="utf-8")
    NEED = 1.4375 / 3 ** 0.5 + 0.5

    def test_one_side_of_a_wide_flange(self):
        # W14x90: (14.5 - 0.44) / 2 - 3 - 15/32 = 3.561 in to the web
        (u,) = utilisations(written(self.BRACKET), "clearance").values()
        self.assertAlmostEqual(u, self.NEED / ((14.5 - 0.44) / 2 - 3 - 15 / 32), places=6)

    def test_a_split_across_the_web_that_leaves_room_excuses_the_one_sided_check(self):
        # W12x50 (bf 8.08, tw 0.37): split at 4 in leaves (4 - 0.37) / 2 = 1.815 in
        report = written(self.BRACKET.replace("support W14x90", "support W12x50").replace("gauge 3 inch", "gauge 4 inch"))
        self.assertEqual(outcome(report, "clearance"), "certified")
        self.assertIn("excused    bb1/steel.clearance: bracket bolts: room to tighten, clear of the support web", report.render())

    def test_columns_that_fit_the_flange_but_leave_no_room_fail(self):
        # at 3 in the split fits the flange but leaves (3 - 0.37) / 2 = 1.315 in, under 1.330 in
        report = written(self.BRACKET.replace("support W14x90", "support W12x50"))
        self.assertEqual(outcome(report, "flange_fit"), "certified")
        self.assertEqual(outcome(report, "clearance"), "refuted")

    def test_on_a_web_the_columns_are_centred_between_the_flanges(self):
        # W14x90 web: (14.0 - 2 (0.71) - 3) / 2 = 4.79 in to each flange
        (u,) = utilisations(written(self.BRACKET.replace("W14x90 flange", "W14x90 web")), "clearance").values()
        self.assertAlmostEqual(u, self.NEED / ((14.0 - 2 * 0.71 - 3) / 2), places=6)


class UnframedEnd(unittest.TestCase):
    """J10.7 wants a pair of full-depth stiffeners at an unframed member end not otherwise
    restrained against twisting about its axis. A force at a member end says which its end
    is; the deck draws no stiffeners, so a free end stays open, never passed."""

    END = """petra 0

design "flange-force-at-an-end" {
  owner "s.engineer@example.org"
}

flange_force ff1 {
  basis lrfd
  member W14x90 grade steel.A992
  bearing_length 0.5 inch
  location end
  distance 20 inch
  end_twist restrained
  force_kind compressive
  flange_restrained yes
  unbraced_length 144 inch
  moment_at_force below_yield
}

load gravity {
  on ff1 force in [0 kip, 100 kip]
  on ff1 panel_shear in [0 kip, 50 kip]
  on ff1 axial in [0 kip, 100 kip]
  signed "s.engineer@example.org" source "beam reaction"
}
"""

    def test_a_restrained_end_passes_without_stiffeners(self):
        report = written(self.END)
        self.assertIsInstance(report.verdict, petra.Pass)
        self.assertFalse([o for v in report.to_json()["verdicts"] for o in v["obligations"] if "/steel.j10_stiffeners/" in o["requirement"]])

    def test_a_free_end_stays_open_for_its_stiffeners(self):
        report = written(self.END.replace("end_twist restrained", "end_twist free"))
        self.assertIsInstance(report.verdict, petra.Unknown)
        self.assertEqual(outcome(report, "j10_stiffeners"), "open")

    def test_an_end_force_must_say_whether_its_end_can_twist(self):
        with self.assertRaisesRegex(Exception, r"end_twist restrained\|free.*J10\.7"):
            written(self.END.replace("  end_twist restrained\n", ""))

    def test_an_interior_force_takes_no_end_twist(self):
        interior = self.END.replace("location end", "location interior").replace("  distance 20 inch\n", "")
        self.assertIsInstance(written(interior.replace("  end_twist restrained\n", "")).verdict, petra.Pass)
        with self.assertRaisesRegex(Exception, "an interior force takes no end_twist"):
            written(interior)


if __name__ == "__main__":
    unittest.main()
