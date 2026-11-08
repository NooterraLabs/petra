"""Steel deck connections (M3): every element on a connection's load path is checked for
every limit state of its role, coverage is exactly the union along the path and, under a
cyclic load, its details' fatigue modes (cyclic.py), and a force the path cannot carry
stays UNKNOWN.

The examples in examples/steel/ cover each kind. The variants below add the details that
switch limit states on: a coped beam, a welded support side, slip-critical bolts, an
extended single plate, shaped and lapped bracket plates, and an axial force. A plate
thickness the shop deck does not stock
is rejected at lowering.
"""
import unittest
from pathlib import Path

from petra.lang import load_design, parse_design
from petra.models.steel import calc, cyclic
from petra.models.base import ComponentError
from petra.models.steel.domain import required
from petra.models.steel.lower import lower_conn
from petra.models.steel.path import ROLE_LIMITS, path
from petra.models.steel.vocab import MODES, UNMODELLED
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.solvers import SolverSource

REGISTRY = build_registry()
STEEL = Path(__file__).resolve().parents[1] / "examples" / "steel"


def variant(name: str, *edits: tuple[str, str]):
    text = (STEEL / f"{name}.petra").read_text(encoding="utf-8")
    for old, new in edits:
        if old not in text:
            raise AssertionError(f"{old!r} is not in {name}.petra")
        text = text.replace(old, new)
    return parse_design(text, f"{name}.petra", REGISTRY)


VARIANTS = {
    "coped double angle": lambda: variant("double_angle", ("  top 3 inch\n", "  top 3 inch\n  cope top length 4 inch depth 1.5 inch\n  setback 0.5 inch\n")),
    "welded double angle": lambda: variant("double_angle", ("  support_side bolted\n  support_gauge 5.5 inch\n",
                                                            "  support_side welded\n  support_weld electrode.E70 size 0.25 inch\n")),
    "slip-critical shear tab": lambda: variant("shear_tab", ("threads included", "threads included joint slip_critical surface class_a")),
    "extended shear tab": lambda: variant("shear_tab", ("  bolt_line 3 inch\n", "  bolt_line 9 inch\n  form extended\n"),
                                          ("W14x90 flange", "W14x90 web")),
    "welded seat": lambda: variant("seated", ("  support_side bolted\n  bolts bolt_group.120 diameter 0.75 inch threads included\n"
                                              "  rows 2\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  support_gauge 5.5 inch\n",
                                              "  support_side welded\n  support_weld electrode.E70 size 0.3125 inch\n")),
    "welded tee": lambda: variant("shear_tee", ("  support_side bolted\n  support_gauge 5.5 inch\n",
                                                "  support_side welded\n  support_weld electrode.E70 size 0.25 inch\n")),
    "shaped bolt bracket": lambda: variant("bolt_bracket", ("thickness 0.5 inch", "thickness 0.75 inch"),
                                           ("edge_vertical 1.5 inch", "edge_vertical 2.25 inch"),
                                           ("  plate_edge 1.5 inch\n", "  plate_edge 1.5 inch\n  free_edge 8 inch\n")),
    "lapped weld bracket": lambda: variant("weld_bracket", ("thickness 0.5 inch", "thickness 0.75 inch"), ("sides 2", "sides 1"),
                                           ("  weld_length 12 inch\n", "  weld_length 12 inch\n  weld_return 2 inch\n  free_edge 8 inch\n")),
}
"""The bracket variants pass. With the examples' 1/2 in plates their free edges fail: the
40 kip load at 6 to 8 in buckles a 1/2 in shaped plate (B-B ratios 1.14 and 2.1). The shaped
bolt bracket's edge rises from below its front column, so at the example's 1-1/2 in lev the
edge lies 1.5 x 8 / hypot(8, 12) = 0.83 in from the bottom bolt, under Table J3.4's 1-1/8 in;
at 2-1/4 in it lies 1.15 in away."""


def designs():
    for p in sorted(STEEL.glob("*.petra")):
        yield p.name, load_design(p, REGISTRY)
    for name, make in VARIANTS.items():
        yield name, make()


def fields(design, conn) -> set[str]:
    return {e.field for case in design.loads.values() for e in case.entries if e.target == (conn,)}


class LoadPath(unittest.TestCase):
    def test_every_element_on_the_path_is_checked_for_every_limit_state_of_its_role(self):
        for label, d in designs():
            for name in d.components:
                conn = calc.connection(d, name, REGISTRY)
                case = next(iter(d.loads))
                for link in path(conn, fields(d, name)):
                    for mode in ROLE_LIMITS[link.role]:
                        if MODES.get(mode) in UNMODELLED:
                            continue
                        with self.subTest(design=label, element=link.element, mode=mode):
                            found = [v.what for v in calc.values(conn, d, REGISTRY, mode, case)]
                            self.assertTrue(any(w.startswith(f"{link.element}:") for w in found),
                                            f"{label}: no {mode} check names {link.element}; found {found}")

    def test_coverage_is_the_union_along_the_path(self):
        for label, d in designs():
            for name in d.components:
                conn = calc.connection(d, name, REGISTRY)
                union = {m for link in path(conn, fields(d, name)) for m in ROLE_LIMITS[link.role]}
                self.assertEqual(set(required(conn, d)), union | set(cyclic.required(conn, d)), label)

    def test_every_role_limit_state_is_a_mode_of_the_deck(self):
        for role, modes in ROLE_LIMITS.items():
            for mode in modes:
                self.assertIn(mode, {**MODES, "load_path": None, "j10_stiffeners": None}, f"{role}: {mode}")

    def test_details_switch_their_limit_states_on(self):
        built = dict(designs())
        conn = lambda label, name: calc.connection(built[label], name, REGISTRY)
        coped = required(conn("coped double angle", "da1"), built["coped double angle"])
        self.assertIn("cope_buckling", coped)
        welded = required(conn("welded double angle", "da1"), built["welded double angle"])
        self.assertTrue({"weld", "weld_base_metal", "fillet_size"} <= set(welded))
        self.assertNotIn("clearance", set(required(conn("welded seat", "seat1"), built["welded seat"])) - {"weld"})
        self.assertIn("slip", required(conn("slip-critical shear tab", "st1"), built["slip-critical shear tab"]))
        extended = required(conn("extended shear tab", "st1"), built["extended shear tab"])
        self.assertTrue({"plate_buckling", "extended_ductility"} <= set(extended))
        self.assertNotIn("ductility", extended)
        self.assertIn("bracket_edge", required(conn("shaped bolt bracket", "bb1"), built["shaped bolt bracket"]))
        lapped = required(conn("lapped weld bracket", "wb1"), built["lapped weld bracket"])
        self.assertTrue({"bracket_edge", "shear_yield", "flexural_yield", "weld"} <= set(lapped))

    def test_the_bracket_variants_pass(self):
        for label in ("shaped bolt bracket", "lapped weld bracket"):
            report = check_design(VARIANTS[label](), REGISTRY, (SolverSource(),))
            self.assertEqual({type(o).__name__ for o in report.outcomes}, {"Discharged"}, label)


class AxialForce(unittest.TestCase):
    def test_an_axial_force_on_a_shear_connection_stays_unknown(self):
        d = variant("shear_tab", ("  on st1 shear in [0 kip, 45 kip]\n", "  on st1 shear in [0 kip, 45 kip]\n  on st1 axial in [0 kip, 10 kip]\n"))
        report = check_design(d, REGISTRY, (SolverSource(),))
        found = {(o.obligation.requirement if hasattr(o, "obligation") else o.requirement).id: type(o).__name__ for o in report.outcomes}
        self.assertEqual(found.pop("st1/steel.load_path/coverage.steel.load_path"), "Open")
        self.assertEqual(set(found.values()), {"Discharged"})


class StockPlates(unittest.TestCase):
    def lower(self, thickness: str):
        d = variant("shear_tab", ("thickness 0.375 inch", f"thickness {thickness} inch"))
        return lower_conn(next(iter(d.components.values())), d, REGISTRY)

    def test_a_fixed_plate_thickness_must_be_stocked(self):
        with self.assertRaisesRegex(ComponentError, "0.3 in is not a stocked plate thickness"):
            self.lower("0.3")
        self.assertEqual(self.lower("0.4375").kind, "shear_tab")


if __name__ == "__main__":
    unittest.main()
