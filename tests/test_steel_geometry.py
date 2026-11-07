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

SHEAR_TAB = """petra 0

design "steel-geometry" {{
  owner "s.engineer@example.org"
}}

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

load gravity {{
  on st1 shear in [0 kip, {load}]
  signed "s.engineer@example.org" source "geometry test"
}}
"""


def shear_tab(beam="W16x26", support="W14x90 flange", rows=3, top="3 inch", bolt_line="3 inch", extra="", load="20 kip"):
    return SHEAR_TAB.format(beam=beam, support=support, rows=rows, top=top, bolt_line=bolt_line, extra=extra, load=load)


def example(name: str, **fields: str) -> str:
    """An example design with each named field set to a new value."""
    text = (EXAMPLES / f"{name}.petra").read_text(encoding="utf-8")
    for key, value in fields.items():
        text, n = re.subn(rf"^(\s+){key} .*$", rf"\g<1>{key} {value}", text, count=1, flags=re.M)
        assert n == 1, key
    return text


def fits(text: str) -> dict[str, list[calc.Value]]:
    """Each fit mode the design's connection owes -> its checks under its load case."""
    design = parse_design(text, "geometry.petra", REGISTRY)
    name = re.search(r"^\w+ (\w+) \{\n  basis ", text, re.M).group(1)
    case = re.search(r"^load (\w+) \{", text, re.M).group(1)
    conn = calc.connection(design, name, REGISTRY)
    return {m: calc.values(conn, design, REGISTRY, m, case) for m in FIT if m in domain.required(conn, design)}


def failing(found: dict[str, list[calc.Value]]) -> set[tuple[str, str]]:
    """(mode, check name without its citation) of every check that does not fit."""
    return {(m, v.what.rsplit(" (", 1)[0]) for m, vs in found.items() for v in vs if not v.excused and v.utilisation > 1}


def excused(found: dict[str, list[calc.Value]]) -> set[tuple[str, str]]:
    return {(m, v.what.rsplit(" (", 1)[0]) for m, vs in found.items() for v in vs if v.excused}


class Misfits(unittest.TestCase):
    def test_a_buildable_shear_tab_fits_every_check(self):
        found = fits(shear_tab())
        self.assertEqual(set(found), {"beam_fit", "flange_fit"})
        self.assertTrue(all(found.values()))
        self.assertEqual(failing(found), set())

    def test_rows_past_the_depth_put_the_plate_and_holes_off_the_web(self):
        found = failing(fits(shear_tab(beam="W12x26", rows=8)))
        self.assertIn(("beam_fit", "plate: bottom edge on the beam's flat web"), found)
        self.assertIn(("beam_fit", "beam web: bottom bolt hole on the flat web"), found)

    def test_a_plate_on_the_fillet_does_not_fit(self):
        found = failing(fits(shear_tab(top="2 inch")))
        self.assertEqual(found, {("beam_fit", "plate: top edge on the beam's flat web")})

    def test_a_top_cope_past_the_plate_frees_its_top_edge(self):
        found = fits(shear_tab(top="2 inch", extra="\n  setback 0.5 inch\n  cope top depth 1.5 inch length 6 inch"))
        self.assertEqual(failing(found), set())
        self.assertIn(("beam_fit", "plate: top edge on the beam's flat web"), excused(found))

    def test_a_cope_short_of_the_plate_frees_nothing(self):
        found = fits(shear_tab(top="2 inch", extra="\n  setback 0.5 inch\n  cope top depth 1.5 inch length 2 inch"))
        self.assertIn(("beam_fit", "plate: top edge on the beam's flat web"), failing(found))

    def test_a_beam_too_wide_for_the_columns_web(self):
        found = fits(shear_tab(beam="W24x76", support="W10x49 web", rows=4))
        self.assertEqual(set(found), {"beam_fit", "web_fit"})
        self.assertEqual(failing(found), {("web_fit", "support web: the beam's flange passes between the column's flanges")})

    def test_a_beam_end_past_the_flange_tips_passes_them(self):
        found = fits(shear_tab(beam="W24x76", support="W10x49 web", rows=4, bolt_line="7 inch"))
        self.assertNotIn("web_fit", {m for m, _ in failing(found)})
        self.assertIn(("web_fit", "support web: the beam's flange passes between the column's flanges"), excused(found))

    def test_support_bolt_lines_wider_than_the_flange(self):
        found = failing(fits(example("double_angle", support_gauge="20 inch")))
        self.assertIn(("flange_fit", "support flange: the bolt lines' holes within the flange's width"), found)

    def test_a_gauge_that_puts_holes_on_the_web_behind_a_flange(self):
        found = failing(fits(example("double_angle", support_gauge="0.75 inch")))
        self.assertIn(("flange_fit", "support flange: the bolt lines' holes clear of the web between them"), found)

    def test_seat_holes_past_the_vertical_leg(self):
        found = failing(fits(example("seated", rows="6")))
        self.assertIn(("flange_fit", "seat angle: bottom bolt hole on its vertical leg, below the outstanding leg"), found)

    def test_bracket_columns_wider_than_the_flange(self):
        found = failing(fits(example("bolt_bracket", columns="2", gauge="16 inch")))
        self.assertEqual({m for m, _ in found}, {"flange_fit"})


class Verdicts(unittest.TestCase):
    def test_a_misfit_fails_on_its_fit_mode(self):
        report = check_design(parse_design(shear_tab(beam="W24x76", support="W10x49 web", rows=4), "g.petra", REGISTRY),
                              REGISTRY, (SolverSource(),))
        self.assertEqual(STATUS[type(report.verdict)], "FAIL")
        refuted = {o["requirement"].split("/")[1] for v in report.to_json()["verdicts"] for o in v["obligations"]
                   if o["outcome"] == "refuted"}
        self.assertIn("steel.web_fit", refuted)

    def test_a_web_support_pass_rests_on_the_column_premise(self):
        report = check_design(parse_design(shear_tab(support="W14x90 web"), "g.petra", REGISTRY), REGISTRY, (SolverSource(),))
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
                text = gen.source("geometry", kind, "lrfd", s.lines, Fraction(10), tuple(s.secondary))
                with self.subTest(kind=kind, i=i):
                    self.assertEqual(failing(fits(text)), set(), text)
                    self.assertEqual([v.id for v in judge(parse_design(text, "g.petra", REGISTRY), REGISTRY).violations], [])
            self.assertGreater(drawn, 0, kind)


if __name__ == "__main__":
    unittest.main()
