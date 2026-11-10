"""The fit of the drawn parts (petra/models/steel/geometry.py, docs/steel_connections.md §5a).

Each class of misfit fails the check that names it: bolt rows past the beam's depth, a
plate on the beam's fillet, a beam too wide to pass between a column's flanges, support
bolt lines wider than the face, a seat's holes off its leg. A coped flange frees the part's
edge it clears, and a beam end at or past the column's flange tips frees the beam's
flange. A buildable design fits every check, a web support's PASS carries web_fit's
premise that the support is a column, and the generator's samplers that keep to the rules
draw only designs that fit and that the outside judge finds buildable."""
import random
import re
import unittest
from fractions import Fraction
from pathlib import Path

from judges import judge
from petra.files import read_pair
from petra.lang import parse_design
from petra.models.steel import calc, domain
from petra.models.steel import generate as gen
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource
from petra.verdict import STATUS

REGISTRY = build_registry()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "steel"
FIT = ("beam_fit", "flange_fit", "web_fit")

SHEAR_TAB_CARD = """petra 0

card "steel-geometry" {{
  owner "s.engineer@example.org"
}}

load gravity {{
  on st1 shear in [0 kip, {load}]
  signed "s.engineer@example.org" source "geometry test"
}}
"""

SHEAR_TAB = """petra 0

shear_tab st1 {{
  basis lrfd
  beam {beam} grade steel.A992
  support {support} grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows {rows}
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line {bolt_line}
  beam_edge 1.75 inch
  top {top}{extra}
  weld electrode.E70 size 0.25 inch sides 2
}}
"""


def shear_tab(beam="W16x26", support="W14x90 flange", rows=3, top="3 inch", bolt_line="3 inch", extra="", load="20 kip"):
    """A card and the shear tab that answers it."""
    return (SHEAR_TAB_CARD.format(load=load),
            SHEAR_TAB.format(beam=beam, support=support, rows=rows, top=top, bolt_line=bolt_line, extra=extra))


def example(name: str, **fields: str) -> tuple[str, str]:
    """An example's card, and its design with each named field set to a new value."""
    card, text = read_pair(EXAMPLES / f"{name}.petra")
    for key, value in fields.items():
        text, n = re.subn(rf"^(\s+){key} .*$", rf"\g<1>{key} {value}", text, count=1, flags=re.M)
        assert n == 1, key
    return card, text


def fits(card: str, text: str) -> dict[str, list[calc.Value]]:
    """Each fit mode the design's connection owes -> its checks under the card's load case."""
    design = parse_design(card, text, "geometry.petra", REGISTRY)
    name = re.search(r"^\w+ (\w+) \{\n  basis ", text, re.M).group(1)
    case = re.search(r"^load (\w+) \{", card, re.M).group(1)
    conn = calc.connection(design, name, REGISTRY)
    return {m: calc.values(conn, design, REGISTRY, m, case) for m in FIT if m in domain.required(conn, design)}


def failing(found: dict[str, list[calc.Value]]) -> set[tuple[str, str]]:
    """(mode, check name without its citation) of every check that does not fit."""
    return {(m, v.what.rsplit(" (", 1)[0]) for m, vs in found.items() for v in vs if not v.excused and v.utilisation > 1}


def excused(found: dict[str, list[calc.Value]]) -> set[tuple[str, str]]:
    return {(m, v.what.rsplit(" (", 1)[0]) for m, vs in found.items() for v in vs if v.excused}


class Misfits(unittest.TestCase):
    def test_a_buildable_shear_tab_fits_every_check(self):
        found = fits(*shear_tab())
        self.assertEqual(set(found), {"beam_fit", "flange_fit"})
        self.assertTrue(all(found.values()))
        self.assertEqual(failing(found), set())

    def test_rows_past_the_depth_put_the_plate_and_holes_off_the_web(self):
        found = failing(fits(*shear_tab(beam="W12x26", rows=8)))
        self.assertIn(("beam_fit", "plate: bottom edge on the beam's flat web"), found)
        self.assertIn(("beam_fit", "beam web: bottom bolt hole on the flat web"), found)

    def test_a_plate_on_the_fillet_does_not_fit(self):
        found = failing(fits(*shear_tab(top="2 inch")))
        self.assertEqual(found, {("beam_fit", "plate: top edge on the beam's flat web")})

    def test_a_top_cope_past_the_plate_frees_its_top_edge(self):
        found = fits(*shear_tab(top="2 inch", extra="\n  setback 0.5 inch\n  cope top depth 1.5 inch length 6 inch"))
        self.assertEqual(failing(found), set())
        self.assertIn(("beam_fit", "plate: top edge on the beam's flat web"), excused(found))

    def test_a_cope_short_of_the_plate_frees_nothing(self):
        found = fits(*shear_tab(top="2 inch", extra="\n  setback 0.5 inch\n  cope top depth 1.5 inch length 2 inch"))
        self.assertIn(("beam_fit", "plate: top edge on the beam's flat web"), failing(found))

    def test_a_beam_too_wide_for_the_columns_web(self):
        found = fits(*shear_tab(beam="W24x76", support="W10x49 web", rows=4, top="3.5 inch"))
        self.assertEqual(set(found), {"beam_fit", "web_fit"})
        self.assertEqual(failing(found), {("web_fit", "support web: the beam's flange passes between the column's flanges")})

    def test_a_beam_end_past_the_flange_tips_passes_them(self):
        found = fits(*shear_tab(beam="W24x76", support="W10x49 web", rows=4, bolt_line="7 inch"))
        self.assertNotIn("web_fit", {m for m, _ in failing(found)})
        self.assertIn(("web_fit", "support web: the beam's flange passes between the column's flanges"), excused(found))

    def test_support_bolt_lines_wider_than_the_flange(self):
        found = failing(fits(*example("double_angle", support_gauge="20 inch")))
        self.assertIn(("flange_fit", "support flange: the bolt lines' holes within the flange's width"), found)

    def test_a_gauge_that_puts_holes_on_the_web_behind_a_flange(self):
        found = failing(fits(*example("double_angle", support_gauge="0.75 inch")))
        self.assertIn(("flange_fit", "support flange: the bolt lines' holes clear of the web between them"), found)

    def test_seat_holes_past_the_vertical_leg(self):
        found = failing(fits(*example("seated", rows="6")))
        self.assertIn(("flange_fit", "seat angle: bottom bolt hole on its vertical leg, below the outstanding leg"), found)

    def test_bracket_columns_wider_than_the_flange(self):
        found = failing(fits(*example("bolt_bracket", columns="2", gauge="16 inch")))
        self.assertEqual({m for m, _ in found}, {"flange_fit"})


class JudgeReadings(unittest.TestCase):
    """Three readings where the deck stood stricter than the outside judge until the judge
    took them up (docs/steel_connections.md §5a): a fillet weld's leg past the edge it runs
    along, a cope too shallow to clear the fillet, and a declared slot's length across the
    face. Each misfit fails the deck's check and raises the judge's condition, and its
    counterpart passes both."""

    @staticmethod
    def both(card: str, text: str) -> tuple[set[tuple[str, str]], set[str]]:
        found = failing(fits(card, text))
        return found, {v.id for v in judge(parse_design(card, text, "g.petra", REGISTRY), REGISTRY).violations}

    @staticmethod
    def welded_seat(size: str) -> tuple[str, str]:
        """Absurd-gap design 4925 (seed 1): a 6 in seat welded at its ends to a W12x26's
        6.49 in flange."""
        card, text = example("seated", support="W12x26 flange grade steel.A992", angle="L6x4x1_2 grade steel.A36 outstanding short",
                             seat_length="6 inch", support_side="welded")
        text = re.sub(r"  bolts .*\n(  (rows|pitch|edge_vertical|support_gauge) .*\n)+", "", text)
        return card, text.replace("  support_side welded\n", f"  support_side welded\n  support_weld electrode.E70 size {size}\n")

    def test_a_weld_at_a_seats_end_lays_its_leg_on_the_flange(self):
        found, ids = self.both(*self.welded_seat("0.25 inch"))
        self.assertEqual(found, {("flange_fit", "support flange: the welds at the seat angle's ends within the flange's width")})
        self.assertEqual(ids, {"steel.support_side.flange_width"})
        self.assertEqual(self.both(*self.welded_seat("0.1875 inch")), (set(), set()))

    def test_a_cope_shallower_than_the_fillet_frees_no_edge(self):
        coped = lambda depth: shear_tab(top="2 inch", extra=f"\n  setback 0.5 inch\n  cope top depth {depth} length 6 inch")
        # W16x26: tf 0.345 in, kdes 0.747 in, and its fillet reaches (d - T)/2 = 1.0375 in
        for shallow in ("0.5 inch", "0.875 inch"):
            with self.subTest(depth=shallow):
                found, ids = self.both(*coped(shallow))
                self.assertEqual(found, {("beam_fit", "plate: top edge on the beam's flat web")})
                self.assertEqual(ids, {"steel.beam_side.fillet"})
        self.assertEqual(self.both(*coped("1.125 inch")), (set(), set()))

    def test_a_declared_slot_across_the_face_needs_its_length_on_the_flange(self):
        card, text = example("hanger", tee_gauge="6 inch")
        hanger = lambda holes: (card, text.replace("  edge_vertical 1.5 inch\n", f"  edge_vertical 1.5 inch\n  holes support {holes}\n"))
        found, ids = self.both(*hanger("lsl"))           # 6 in + 1-7/8 in on a W18x50's 7.50 in flange
        self.assertEqual(found, {("flange_fit", "support flange: the bolt lines' holes within the flange's width")})
        self.assertEqual(ids, {"steel.support_side.flange_width"})
        for holes in ("std", "lsl_parallel"):
            with self.subTest(holes=holes):
                self.assertEqual(self.both(*hanger(holes)), (set(), set()))


class FlatWebIsT(unittest.TestCase):
    """The flat web is T, the workable depth between the fillets' toes that Manual Part 1
    tabulates, not d - 2 kdes. Petra 0.1.0 read kdes, so a part on the band between them
    passed the deck and the judge. The Companion gives T = 15-1/2 in for a W18x35, where
    d - 2 kdes = 16.05 in."""

    @staticmethod
    def judged(card: str, text: str) -> set[str]:
        return {v.id for v in judge(parse_design(card, text, "g.petra", REGISTRY), REGISTRY).violations}

    def test_a_plate_edge_below_kdes_but_on_the_fillet_fails_and_the_judge_rejects_it(self):
        # W18x35: kdes 0.827 in, d 17.7 in, T 15.5 in, so the fillet reaches 1.1 in. The
        # plate's top edge, Lev = 1.5 in above the top row, lies 1 in down.
        band = shear_tab(beam="W18x35", top="2.5 inch")
        self.assertEqual(failing(fits(*band)), {("beam_fit", "plate: top edge on the beam's flat web")})
        self.assertEqual(self.judged(*band), {"steel.beam_side.fillet"})
        report = check_design(parse_design(*band, "g.petra", REGISTRY), REGISTRY, (SolverSource(),))
        self.assertEqual(STATUS[type(report.verdict)], "FAIL")
        clear = shear_tab(beam="W18x35", top="2.75 inch")
        self.assertEqual((failing(fits(*clear)), self.judged(*clear)), (set(), set()))

    def test_a_part_wider_than_a_column_webs_T_fails_and_the_judge_rejects_it(self):
        # W14x90: T 10 in, d - 2 kdes 11.38 in, d - 2 tf 12.58 in.
        plate = lambda width: example("shear_end_plate", support="W14x90 web grade steel.A992", plate_width=width)
        self.assertEqual(failing(fits(*plate("10.5 inch"))), {("web_fit", "support web: the end plate within the web's flat between its fillets")})
        self.assertEqual(self.judged(*plate("10.5 inch")), {"steel.support_side.web_fillet"})
        self.assertEqual((failing(fits(*plate("9.5 inch"))), self.judged(*plate("9.5 inch"))), (set(), set()))


class Verdicts(unittest.TestCase):
    def test_a_misfit_fails_on_its_fit_mode(self):
        report = check_design(parse_design(*shear_tab(beam="W24x76", support="W10x49 web", rows=4), "g.petra", REGISTRY),
                              REGISTRY, (SolverSource(),))
        self.assertEqual(STATUS[type(report.verdict)], "FAIL")
        refuted = {o["requirement"].split("/")[1] for v in report.to_json()["verdicts"] for o in v["obligations"]
                   if o["outcome"] == "refuted"}
        self.assertIn("steel.web_fit", refuted)

    def test_a_web_support_pass_rests_on_the_column_premise(self):
        report = check_design(parse_design(*shear_tab(support="W14x90 web"), "g.petra", REGISTRY), REGISTRY, (SolverSource(),))
        self.assertEqual(STATUS[type(report.verdict)], "PASS")
        premise = next(p for p in report.verdict.footprint.premises if str(p.label).startswith("model:steel.web_fit@"))
        self.assertIn("read as a column", premise.statement)


class Samplers(unittest.TestCase):
    """Absurd-gap and gate designs come from the same samplers; a sample that keeps to the
    rules (not one of the free share) must fit and be buildable by the judge's reading."""

    def test_samples_that_keep_to_the_rules_fit_and_are_buildable(self):
        for kind, sampler in gen.SAMPLERS.items():
            drawn = 0
            for i in range(60):
                s = gen._Sampler(random.Random(f"geometry:{kind}:{i}"), REGISTRY)
                sampler(s)
                if s.free:
                    continue
                drawn += 1
                card, text = gen.source("geometry", kind, "lrfd", s.lines, Fraction(10), tuple(s.secondary))
                with self.subTest(kind=kind, i=i):
                    self.assertEqual(failing(fits(card, text)), set(), text)
                    self.assertEqual([v.id for v in judge(parse_design(card, text, "g.petra", REGISTRY), REGISTRY).violations], [])
            self.assertGreater(drawn, 0, kind)


if __name__ == "__main__":
    unittest.main()
