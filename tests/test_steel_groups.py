"""Steel deck ground truth, M4: eccentric bolt and weld groups, bracket plates and hangers.

Companion to the AISC Steel Construction Manual, v16.0, Vol. 1 (AISC 2023): II.A-22 (bolted
bracket plate), II.A-23 (welded bracket plate), II.A-24 and 25 (an eccentric bolt group by
the instantaneous-centre and the elastic method), II.A-26 and 27 (an eccentric C-shaped
weld group, likewise) and II.D-1 (a WT hanger with prying). Kulak, Fisher and Struik,
Guide to Design Criteria for Bolted and Riveted Joints, 2nd ed. (1987), Table 13.1: the
instantaneous-centre coefficients C of a line of bolts.

Reproduced: the bolt groups by the instantaneous centre (II.A-22's bolts, II.A-24), and
the elastic method's coefficient (II.A-25), which the deck takes where it is the larger;
Kulak's coefficients; the C-shaped weld groups by the instantaneous centre (II.A-23's
welds, II.A-26, Manual Table 8-8) and the elastic method's coefficient (II.A-27); the
bracket plates' section A-A (shear, flexural yielding) and their free-edge section B-B
(shear, the normal force and moment with local buckling) (II.A-22, 23); the hanger's bolt
tension, its flange in shear, and the flange thickness at which prying uses the bolt up
(II.D-1).

Also reproduced: II.A-2A's Manual Table 8-4 coefficient at k = 0, the group a bracket plate
on edge welded on both faces is, which the deck takes by the instantaneous centre.

The instantaneous centre's premises, measured: along the axis through the centroid across
the load, the eccentricity a centre balances falls as the centre moves out, and the force
the bolts or the welds hold rises (the certificates in checks.py and ic.py rest on it). A
C-shaped weld's C rises with its returns. No weld element's force along its line passes
petra.weld_ic.along_peak.

The P3 pilot's designs (corpus/cases/pilot): the three the deck refused at 38cc6ba and now
passes (303-003 in tests/test_steel_coverage.py, 303-006, 303-022), and a bracket from the
arm with Petra that the deck passed there and now fails by its tearout toward its back edge
(303-021). A bracket's tearout, its edge distances with Table J3.5's C2, and its slots.

Not reproduced, each explained:
- II.A-22's flexural rupture: Manual Table 15-2 takes the vertical edge distance as 1-1/2
  in, a net section 18 in deep, where the plate is 20 in deep. At the table's edge
  distance the deck gives the printed 1,050 / 700 kip-in.
- II.A-24B and 26B: inclined loads. The deck's brackets carry a vertical load.
- II.D-1's angles and their welds, the stem's Whitmore section and the beam's flange
  holes (F13): the hanger kind is the tee and its bolts.

Rounding: II.A-22's lambda is printed as 1.68 (1.686 unrounded), so its Q, Fcr and the
interaction move by about 1 %; its Mn is printed to three figures before Omega, which moves
the ASD flexure by 0.6 %.
"""
import math
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np

import petra
from petra import mechanics as M
from petra.kernel import Const, enclose
from petra.lang import parse_design
from petra.models.steel import calc, checks, ic
from petra.models.steel import limits as L
from petra.registry import build_registry
from petra.units import CUSTOMARY

from tests import steel_examples as ex

ROOT = Path(__file__).resolve().parents[1]
INCH = CUSTOMARY["inch"][0]
KIP = CUSTOMARY["kip"][0]
KSI = CUSTOMARY["ksi"][0]
REGISTRY = build_registry()


def const(name: str) -> Const:
    return L.c(REGISTRY.constants[name].value.lo)


def inch(x) -> Const:
    return L.c(Fraction(x) * INCH)


def value(expr, per=1) -> float:
    return float(enclose(expr, {}).lo / per)


def checked(text: str) -> dict:
    """The deck's report on a design given as text."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "design.petra"
        target.write_text(text, encoding="utf-8", newline="\n")
        return petra.check_file(target).to_json()


def obligation(report: dict, mode: str) -> dict:
    (found,) = [o for v in report["verdicts"] for o in v["obligations"] if f"/steel.{mode}/" in o["requirement"]]
    return found


BRACKET_22 = ("  plate steel.A572_50 thickness 0.375 inch\n  support W14x90 flange grade steel.A992\n"
              "  bolts bolt_group.120 diameter 0.75 inch threads included\n  rows 6\n  columns 2\n  pitch 3 inch\n"
              "  gauge 5.5 inch\n  eccentricity 12 inch\n  edge_vertical 2.5 inch\n  plate_edge 2.25 inch\n"
              "  free_edge 15.25 inch\n")


class IIA22(ex.Example):
    """A bolted bracket plate: PL3/8 A572 Gr. 50, 20 in deep at the column, two columns of six
    3/4 in Group 120-N bolts (gauge 5-1/2, pitch 3), the load 12 in from the group's centroid
    (9-1/4 in from section A-A), the free edge projecting 15-1/4 in. Pu = 36.0, Pa = 24.0
    kips per plate."""

    tag, kind, body, loads = "II.A-22", "bolt_bracket", BRACKET_22, ("36.0", "24.0")
    printed = {
        ("flexural_yield", "bracket plate:"): ("1,690", "1,130", 0.01),
        ("shear_yield", "bracket plate:"): ("225", "150"),
        ("shear_rupture", "bracket plate:"): ("162", "108"),
    }
    moments = ("flexural_yield", "flexural_rupture")
    availables = {("bracket_edge", "bracket plate: shear yielding of the free-edge"): ("136", "90.7")}
    # Table 7-6: C = 4.53 at ex = 12 in, times the bolt's 17.9 / 11.9 kips (bolt shear governs).
    printed = {**printed, ("bolts", "bracket bolts:"): ("81.1", "53.9")}

    def test_flexural_rupture_at_the_tables_edge_distance(self):
        body = self.body.replace("edge_vertical 2.5 inch", "edge_vertical 1.5 inch")
        for basis, printed in (("lrfd", "1,050"), ("asd", "700")):
            self.near(self.strength(basis, "flexural_rupture", "bracket plate:", body), printed, f"{self.tag} {basis}")

    def test_net_plastic_modulus_of_table_15_2(self):
        z = M.rectangle_net_plastic_modulus(inch("0.375"), inch(18), 6, inch(3), inch(Fraction(7, 8)))
        self.near(value(z, INCH ** 3), "21.5", "Znet")

    def test_normal_force_and_moment_on_the_free_edge(self):
        for basis, printed in (("lrfd", "0.864"), ("asd", "0.862")):
            found, _ = self.values(basis, "bracket_edge")
            ratio = max(v.utilisation for v in found if "normal force and moment" in v.what and not v.excused)
            self.near(ratio, printed, f"{self.tag} {basis}", 0.012)


TABLE_8_8 = 0.015
"""How far a C-shaped weld's strength may lie from the Companion's: the deck certifies a bound
up to ic.WELD_LOSS = 0.5 % under the method's C; the Companion interpolates Table 8-8, which
reads II.A-26's C 0.43 % over the method's 1.872, and rounds Rn to three figures (113 kips for
112.8)."""


class IIA23(ex.Example):
    """A welded bracket plate: two PL3/8 A572 Gr. 50 lapped on the column, each welded by a
    3/16 in E70 C-shaped fillet, 18 in long with 3 in returns, the load al = 10-7/8 in from
    the weld's centroid (printed 10.9), which lies xl = 9 / 24 = 0.375 in inside the vertical
    weld. So the load is 11-1/4 in from the vertical weld and 8-1/4 in from section A-A at
    the returns' tips. The free edge projects 11-1/2 in. Pu = 54.0, Pa = 36.0 kips shared by
    the two plates; the design models one."""

    tag, kind, plates, loads = "II.A-23", "weld_bracket", 2, ("27.0", "18.0")
    body = ("  plate steel.A572_50 thickness 0.375 inch\n  support W14x90 flange grade steel.A992\n"
            "  weld electrode.E70 size 0.1875 inch sides 1\n  weld_length 18 inch\n  weld_return 3 inch\n"
            "  eccentricity 10.875 inch\n  free_edge 11.5 inch\n")
    printed = {
        ("shear_yield", "bracket plate:"): ("405", "270"),
        ("flexural_yield", "bracket plate:"): ("2,740", "1,820"),
        # Table 8-8: C = 1.46, C1 = 1.00, D = 3, l = 18 in, two plates: 0.75 C C1 D l and C C1 D l / 2.00
        ("weld", "bracket weld:"): ("118", "78.8", TABLE_8_8),
    }
    moments = ("flexural_yield",)
    availables = {("bracket_edge", "bracket plate: shear yielding of the free-edge"): ("218", "145")}

    def test_normal_force_and_moment_on_the_free_edge(self):
        for basis, printed in (("lrfd", "0.630"), ("asd", "0.631")):
            found, _ = self.values(basis, "bracket_edge")
            ratio = max(v.utilisation for v in found if "normal force and moment" in v.what and not v.excused)
            self.near(ratio, printed, f"{self.tag} {basis}")

    def test_fillet_size_limits(self):
        """3/16 in is the minimum for the 3/8 in plate, and at most 3/8 - 1/16 = 5/16 in along its edge."""
        found, _ = self.values("lrfd", "fillet_size")
        live = {v.what: v for v in found if not v.excused}
        edge = [v for what, v in live.items() if "along the edge" in what]
        self.assertEqual(len(edge), 1)
        self.near(edge[0].capacity, "0.3125", "maximum along the edge")
        self.assertTrue(all(v.utilisation <= 1 for v in live.values()))


GROUP_24 = ("  plate steel.A36 thickness 0.875 inch\n  support W14x90 flange grade steel.A992\n"
            "  bolts bolt_group.120 diameter 0.875 inch threads included\n  rows 6\n  columns 2\n  pitch 3 inch\n"
            "  gauge 5.5 inch\n  eccentricity 16 inch\n  edge_vertical 1.5 inch\n  plate_edge 1.5 inch\n")


class IIA24And25(ex.Example):
    """Two columns of six 7/8 in Group 120-N bolts in single shear (gauge 5-1/2, pitch 3), a
    vertical load 16 in from the centroid; bolt shear governs (24.3 / 16.2 kips a bolt).
    II.A-24 is the instantaneous centre (C = 3.55), which the deck takes; II.A-25 the
    elastic method, whose coefficient the deck takes only where it is the larger."""

    tag, kind, body, loads = "II.A-24", "bolt_bracket", GROUP_24, ("60", "40")
    printed = {("bolts", "bracket bolts:"): ("86.3", "57.5")}

    def test_the_elastic_coefficient_of_II_A_25(self):
        fx, fy = M.elastic_bolt_force(L.c(1), inch(16), L.c(12), 6, 2, inch(3), inch("5.5"))
        elastic = 1 / math.hypot(value(fx), value(fy))
        bolt = value(L.bolt_shear(L.c(54 * KSI), inch("0.875"), L.c(1)), KIP)
        for factor, printed in ((0.75, "69.0"), (1 / 2.00, "46.0")):
            self.near(elastic * bolt * factor, printed, "II.A-25")


class IIA26And27(ex.Example):
    """A C-shaped 3/8 in E70 fillet, 10 in long with 5 in returns, a vertical load ex = 8.75
    in from the centroid, which lies 25 / 20 = 1.25 in inside the vertical weld, so 10 in
    from that weld. II.A-26 is the instantaneous centre (C = 1.88), which the deck takes;
    II.A-27 the elastic method, whose coefficient the deck takes only where it is the
    larger."""

    tag, kind, loads = "II.A-26", "weld_bracket", ("40", "25")
    body = ("  plate steel.A36 thickness 0.5 inch\n  support W14x90 flange grade steel.A992\n"
            "  weld electrode.E70 size 0.375 inch sides 1\n  weld_length 10 inch\n  weld_return 5 inch\n"
            "  eccentricity 8.75 inch\n")
    printed = {("weld", "bracket weld:"): ("84.8", "56.5", TABLE_8_8)}

    def test_the_elastic_coefficient_of_II_A_27(self):
        fx, tip, heel = M.elastic_weld_c(L.c(1), inch(10), inch(10), inch(5))
        peak = max(math.hypot(value(fx), value(f)) for f in (tip, heel))
        line = value(L.fillet_per_length(const, L.c(70 * KSI), inch("0.375")))
        for factor, printed in ((0.75, "47.2"), (1 / 2.00, "31.5")):
            self.near(line * factor / peak / KIP, printed, "II.A-27")


class IID1(ex.Example):
    """A WT6x17.5 hanger (A992) bolted to a W21x57's bottom flange by four 3/4 in Group 120-N
    bolts, gauge 3-1/2, rows 5 in apart on a 9 in length. Pu = 60.0, Pa = 40.0 kips."""

    tag, kind, field, loads = "II.D-1", "hanger", "tension", ("60.0", "40.0")
    body = ("  tee WT6x17_5 grade steel.A992\n  support W21x57 flange grade steel.A992\n"
            "  bolts bolt_group.120 diameter 0.75 inch threads included\n  rows 2\n  pitch 5 inch\n"
            "  tee_gauge 3.5 inch\n  edge_vertical 2 inch\n")
    availables = {("bolt_tension", "hanger bolts:"): ("29.8", "19.9")}
    printed = {
        ("shear_yield", "tee flange:"): ("281", "187"),
        ("shear_rupture", "tee flange:"): ("221", "147"),
    }

    def test_prying_uses_the_bolt_up_at_the_minimum_flange_thickness(self):
        """The Companion's tmin = 0.393 in (Manual Eq 9-23, alpha' = 1): at that flange the
        deck's available tension with prying is the bolt's required 15.0 / 10.0 kips."""
        fu = L.c(65 * KSI)
        for b_avail, phi, printed in (("29.8", L.c("0.90"), "15.0"), ("19.9", L.c(Fraction(100, 167)), "10.0")):
            t = L.prying_available(const, L.c(Fraction(b_avail) * KIP), inch("0.75"), inch(Fraction(13, 16)), inch("4.5"),
                                   inch("1.60"), inch("1.53"), inch("0.393"), fu, phi)
            self.near(value(t, KIP), printed, f"T at tmin, B = {b_avail}")

    def test_the_flange_is_thicker_than_tmin(self):
        for basis in ("lrfd", "asd"):
            found, _ = self.values(basis, "prying")
            self.assertTrue(found and all(v.utilisation < 1 for v in found))


class KulakTable13_1(unittest.TestCase):
    """Kulak Table 13.1 (from the AISC Manual, 8th ed.): C of a vertical line of n bolts at
    3 in, a vertical load at lever arm l. Its C is P over the bolt's ultimate shear Rult,
    where the critical bolt reaches only Rult (1 - e^(-10 x 0.34))^0.55 = 0.9815 Rult, so
    the instantaneous-centre strength in units of the critical bolt's strength is C / 0.9815.
    The deck's elastic strength never exceeds it: for two bolts, each equally far from the
    instantaneous centre, the two methods agree."""

    TABLE = {   # (n, l in.): C, a subset of the printed table
        (2, 3): "0.88", (3, 3): "1.75", (4, 3): "2.81", (6, 3): "4.98", (8, 3): "7.12", (12, 3): "11.3",
        (2, 6): "0.48", (3, 6): "0.97", (4, 6): "1.73", (6, 6): "3.55", (8, 6): "5.63", (12, 6): "9.96",
        (2, 12): "0.24", (3, 12): "0.49", (4, 12): "0.92", (6, 12): "2.00", (8, 12): "3.44", (12, 12): "7.06",
        (2, 24): "0.12", (3, 24): "0.25", (4, 24): "0.47", (6, 24): "1.03", (8, 24): "1.82", (12, 24): "3.99",
        (2, 36): "0.08", (3, 36): "0.16", (4, 36): "0.31", (6, 36): "0.69", (8, 36): "1.22", (12, 36): "2.72",
    }
    CRITICAL = (1 - math.exp(-3.4)) ** 0.55

    def elastic_c(self, n: int, lever: int) -> float:
        fx, fy = M.elastic_bolt_force(L.c(1), inch(lever), L.c(n), n, 1, inch(3), L.c(0))
        return 1 / math.hypot(value(fx), value(fy))

    def test_the_elastic_group_never_exceeds_the_instantaneous_centre(self):
        for (n, lever), printed in self.TABLE.items():
            with self.subTest(n=n, l=lever):
                half_unit = 0.005 if float(printed) < 10 else 0.05
                self.assertLessEqual(self.elastic_c(n, lever), (float(printed) + half_unit) / self.CRITICAL)

    def test_two_bolts_agree(self):
        for lever in (3, 6, 12, 24, 36):
            with self.subTest(l=lever):
                self.assertAlmostEqual(self.elastic_c(2, lever) * self.CRITICAL, float(self.TABLE[(2, lever)]), delta=0.006)

    def test_the_certificate_reproduces_the_table(self):
        """The deck's certified C (checks._ic_coefficient's bound at ic.bolt_centre's
        centre) is at most the printed C plus half its last digit, and within 1/2 % of it
        or one unit of its last digit."""
        for (n, lever), printed in self.TABLE.items():
            with self.subTest(n=n, l=lever):
                s, e = inch(3), inch(lever)
                r = ic.bolt_centre(REGISTRY, n, 1, s, L.c(0), e, {})
                self.assertIsNotNone(r)
                v, m = M.instantaneous_centre(r, n, 1, s, L.c(0), L.ic_bolt_curve(const))
                found = min(value(v), value(M.sub(m, M.mul(v, M.add(e, r)))) / value(const("petra.switch.length")))
                unit = 0.01 if float(printed) < 10 else 0.1
                self.assertLessEqual(found, float(printed) + unit / 2)
                self.assertLessEqual(abs(found - float(printed)), max(unit, 0.005 * float(printed)))


class InstantaneousCentrePremise(unittest.TestCase):
    """The certificate's premise (ic.py): along the axis through the centroid across the
    load, a centre r from the centroid balances the eccentricity e(r) = M(r)/V(r) - r with
    the force V(r), e falls and V rises as r grows, so the centre that balances a smaller e
    lies farther out and holds more. Measured with the deck's curve over patterns of 1 to 12
    rows and 1 to 4 columns, gauge from a fifth to five times the pitch, and centres from a
    ten-thousandth of the pitch to ten thousand pitches."""

    def test_e_falls_and_v_rises_along_the_axis(self):
        exponent, power = ic.curve(REGISTRY)
        rs = np.geomspace(1e-4, 1e4, 4000)
        for rows in range(1, 13):
            for cols in range(1, 5):
                if rows * cols < 2:
                    continue
                for ratio in ((0.0,) if cols == 1 else (0.2, 1.0, 5.0)):
                    x, y = ic._pattern(rows, cols, 1.0, ratio)
                    sums = np.array([ic._sums(r, x, y, exponent, power) for r in rs])
                    e = sums[:, 1] / sums[:, 0] - rs
                    with self.subTest(rows=rows, cols=cols, gauge=ratio):
                        self.assertTrue((np.diff(e) < 0).all())
                        self.assertTrue((np.diff(sums[:, 0]) > 0).all())


class TableTenNine(unittest.TestCase):
    """A conventional single plate's bolt group takes Manual Table 10-9's eccentricity a/2
    for 2 to 5 rows in standard or short-slotted holes, and a past it. The P3 pilot's task
    303-006, four rows at a = 2-1/2 in, failed by the elastic method at e = a (1.08); by the
    instantaneous centre at a/2 it uses 0.84 of the group, at a 0.999."""

    PILOT = ROOT / "corpus" / "cases" / "pilot" / "tab_half_a.petra"

    def bolts(self, *edits: tuple[str, str]) -> float:
        text = self.PILOT.read_text(encoding="utf-8")
        for old, new in edits:
            self.assertIn(old, text)
            text = text.replace(old, new)
        d = parse_design(text, "303-006.petra", REGISTRY)
        (found,) = calc.values(calc.connection(d, "st1", REGISTRY), d, REGISTRY, "bolts", "service")
        return found.utilisation

    def test_the_pilots_plate_passes_at_half_a(self):
        self.assertEqual(petra.check_file(self.PILOT).to_json()["status"], "PASS")
        self.assertAlmostEqual(self.bolts(), 0.836, delta=0.001)
        self.assertAlmostEqual(self.bolts(("  form conventional", "  form conventional\n  eccentricity 2.5 inch")), 0.999,
                               delta=0.001)

    def test_six_rows_keep_a(self):
        six = (("rows 4", "rows 6"),)
        self.assertEqual(self.bolts(*six), self.bolts(*six, ("  form conventional", "  form conventional\n  eccentricity 2.5 inch")))

    def test_a_plate_edge_short_of_2d_keeps_a(self):
        """The configuration has Leh at least 2d = 1-1/2 in on the plate."""
        short = (("plate_edge 1.75 inch", "plate_edge 1.4375 inch"),)
        explicit = ("  form conventional", "  form conventional\n  eccentricity 2.5 inch")
        self.assertEqual(self.bolts(*short), self.bolts(*short, explicit))
        self.assertGreater(self.bolts(*short), 0.99)


class WeldInstantaneousCentrePremise(unittest.TestCase):
    """The weld certificate's premises (checks.weld_coefficient, gen_weld_base_metal). A
    group turns about a centre r behind its centroid, on the line through the centroid
    across the load; e(r) = M/V - r is the eccentricity, over the line's length, that the
    centre balances. Measured with the deck's curve on the line (Table 8-4 with k = 0): e
    falls as r grows, and V rises up to r = 0.81, the centre that balances a = 0.102, and
    falls past it, so it rises up to the centre for every a at least petra.weld_ic.a_min =
    1/8. On a C with returns k up to 5 (Table 8-8): e falls wherever V is positive, and V
    peaks at a centre that balances at most a = 0.111 (k = 0.05). C rises with k up to
    petra.weld_ic.k_max = 2 at every a from 1/8 to 10, and falls as a grows (it follows
    from the two above). An element's force along its weld is at most max (1 + 0.50
    sin^1.5 theta) cos theta = 1.0337 times max f(p) = 1.0008, under
    petra.weld_ic.along_peak = 1.04."""

    curve = ic.weld_curve(REGISTRY)
    a_min = float(REGISTRY.constants["petra.weld_ic.a_min"].value.lo)

    def group(self, k) -> tuple:
        return ic.pieces(checks.turning_group(Fraction(k)))

    def test_e_falls_and_v_rises_up_to_the_centre(self):
        rs = np.geomspace(1e-5, 1e3, 1500)
        sums = np.array([ic.weld_sums(r, self.curve, self.group(0)) for r in rs])
        e = sums[:, 1] / sums[:, 0] - rs
        self.assertTrue((np.diff(e) < 0).all())
        for a, rises in ((0.103, True), (self.a_min, True), (0.10, False)):
            with self.subTest(a=a):
                far = ic.weld_balancing(a, self.curve, self.group(0))
                self.assertIsNotNone(far)
                self.assertEqual(bool((np.diff(sums[rs <= far, 0]) > 0).all()), rises)

    def test_on_a_c_e_falls_and_v_rises_up_to_the_centre(self):
        rs = np.geomspace(1e-4, 1e3, 600)
        for k in ("1/20", "1/10", "1/5", "3/10", "1/2", "3/4", "1", "3/2", "2", "3", "5"):
            with self.subTest(k=k):
                sums = np.array([ic.weld_sums(r, self.curve, self.group(k)) for r in rs])
                held = sums[:, 0] > 0
                # V is positive from some centre out, and e falls there
                self.assertTrue(held[np.argmax(held):].all())
                e = sums[held, 1] / sums[held, 0] - rs[held]
                self.assertTrue((np.diff(e) < 0).all())
                peak = int(np.argmax(sums[:, 0]))
                self.assertLess(sums[peak, 1] / sums[peak, 0] - rs[peak], 0.112)
                far = ic.weld_balancing(self.a_min, self.curve, self.group(k))
                self.assertTrue((np.diff(sums[rs <= far, 0]) > 0).all())

    def test_c_rises_with_k_and_falls_with_a(self):
        ks = [Fraction(i, 20) for i in range(41)]
        k_max = REGISTRY.constants["petra.weld_ic.k_max"].value.lo
        self.assertEqual(ks[-1], k_max)
        table = []
        for a in (self.a_min, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0):
            row = []
            for k in ks:
                group = self.group(k)
                row.append(ic.weld_sums(ic.weld_balancing(a, self.curve, group), self.curve, group)[0])
            table.append(row)
        table = np.array(table)
        self.assertTrue((np.diff(table, axis=1) > 0).all())
        self.assertTrue((np.diff(table, axis=0) < 0).all())

    def test_the_force_along_the_weld(self):
        def k(name: str) -> float:
            return float(REGISTRY.constants[name].value.lo)

        theta = np.radians(np.linspace(0.0, 90.0, 900_001))
        along = float(np.max((1 + k("aisc360.j2_4.kds") * np.sin(theta) ** k("aisc360.j2_4.kds_power")) * np.cos(theta)))
        a, b = k("aisc_manual.p8.ic_curve_a"), k("aisc_manual.p8.ic_curve_b")
        p = a / (2 * b)
        peak = (p * (a - b * p)) ** k("aisc_manual.p8.ic_curve_power")
        self.assertAlmostEqual(along, 1.0337, delta=0.0001)
        self.assertAlmostEqual(peak, 1.0008, delta=0.0001)
        self.assertLessEqual(along * peak, k("petra.weld_ic.along_peak"))


PILOT_022 = ROOT / "corpus" / "cases" / "pilot" / "weld_bracket_thin_plate.petra"


def certificate(segments: tuple, a: Fraction) -> tuple:
    """(V_lo, gap_lo) of the deck's certificate on a weld group at a, in units of Fnw Aw per
    unit of its line's length, its held constants each inside its bound."""
    found = ic.weld_centre(ic.weld_curve(REGISTRY), segments, a)
    assert found is not None
    r, runs = found
    v, gap, held = checks.weld_certificate(const, ic.weld_curve(REGISTRY), a, r, runs)
    assert all(enclose(m, {}).lo > 0 for m in held)
    return v, gap


class TableEightFour(unittest.TestCase):
    """A bracket plate on edge, welded to its support on both faces with the load in its
    plane, is Manual Table 8-4's group at k = 0: two lines of length L at one place, the
    load a L from them. C is in kips per sixteenth of an E70 fillet per inch of L, both
    lines, so the deck's V per unit of Fnw Aw on one line counts 2 x 0.6 x 70 x (sqrt 2 / 2)
    / 16 = 3.712 times. Companion II.A-2A interpolates the table at a = 4 / 23.5 = 0.170 for
    C = 3.61.

    The P3 pilot's task 303-022: two 3/16 in E70 fillets 13 in long on a 5/16 in A572 Gr. 50
    plate, the load 5 in out (a = 0.385), 48.4 kips ASD. At 38cc6ba the elastic method failed
    the welds (1.68) and the plate's base metal (1.54), reading the base metal against the
    whole force at the weld's end. By the instantaneous centre the welds use 0.915 and the
    base metal, against the force along the weld, 0.869 (the twin's quadrature 0.911 and
    0.866)."""

    def test_the_certificate_reproduces_the_companion(self):
        v, gap = certificate(checks.turning_group(Fraction(0)), Fraction(4, 1) / Fraction(47, 2))
        self.assertGreater(value(gap), 0)
        per_sixteenth = 2 * 0.6 * 70 * math.sqrt(2) / 2 / 16
        self.assertLessEqual(value(v) * per_sixteenth, 3.61 + 0.005)
        self.assertGreater(value(v) * per_sixteenth, 3.61 * 0.99)

    def values(self, text: str, mode: str) -> list:
        d = parse_design(text, "303-022.petra", REGISTRY)
        return calc.values(calc.connection(d, "wb1", REGISTRY), d, REGISTRY, mode, "service")

    def test_the_pilots_bracket_passes(self):
        self.assertEqual(petra.check_file(PILOT_022).to_json()["status"], "PASS")
        text = PILOT_022.read_text(encoding="utf-8")
        (weld,) = self.values(text, "weld")
        self.assertIn("instantaneous center", weld.what)
        self.assertAlmostEqual(weld.utilisation, 0.915, delta=0.001)
        (base,) = self.values(text, "weld_base_metal")
        self.assertAlmostEqual(base.utilisation, 0.869, delta=0.001)

    def test_a_short_lever_keeps_the_elastic_method(self):
        """At e = 1.5 in on 13 in, a = 0.115 is under a_min."""
        text = PILOT_022.read_text(encoding="utf-8").replace("eccentricity 5 inch", "eccentricity 1.5 inch")
        welds = self.values(text, "weld")
        self.assertTrue(welds and all("most stressed point" in w.what for w in welds))
        self.assertFalse(any("instantaneous center" in w.what for w in welds))


RETURNS = """petra 0

design "gate-1-06114" {
  owner "gate@petra.dev"
}

weld_bracket c1 {
  basis lrfd
  plate steel.A36 thickness 0.625 inch
  support W10x49 flange grade steel.A992
  weld electrode.E70 size 0.375 inch sides 1
  weld_length 10 inch
  weld_return 2 inch
  eccentricity 5 inch
  free_edge 8 inch
}

load gate {
  on c1 shear in [0 kip, 47.784 kip]
  signed "gate@petra.dev" source "steel gate generator"
}
"""


class TableEightEight(unittest.TestCase):
    """A plate lapped on its support and welded all round its edge but the free one is
    Manual Table 8-8's C-shaped group: a line of length l along the load with returns kl at
    both ends toward it, the load al from the group's centroid. C is in kips per sixteenth
    of an E70 fillet per inch of l, so the deck's V per unit of Fnw Aw counts 0.6 x 70 x
    (sqrt 2 / 2) / 16 = 1.856 times. The Companion interpolates the table: II.A-23 at k = 3 /
    18, a = 10.875 / 18 for C = 1.46, II.A-26 at k = 0.5, a = 8.75 / 10 for C = 1.88. The
    method's own C is 1.4569 and 1.8719 (measured, and the twin's quadrature agrees to
    1e-14).

    The gate's bracket gate-1-06114: a 5/8 in A36 plate on a 3/8 in E70 C, 10 in long with
    2 in returns, the load 5 in from the centroid, 47.784 kips LRFD. At 48c8773 the deck
    read the C by the elastic method alone, 1.015, and failed it; the clean-room twin's
    instantaneous centre reads 0.592."""

    per_sixteenth = 0.6 * 70 * math.sqrt(2) / 2 / 16

    def test_the_certificate_reproduces_the_companion(self):
        for tag, k, a, printed in (("II.A-23", Fraction(1, 6), Fraction(29, 48), 1.46),
                                   ("II.A-26", Fraction(1, 2), Fraction(7, 8), 1.88)):
            with self.subTest(tag):
                v, gap = certificate(checks.turning_group(k), a)
                self.assertGreater(value(gap), 0)
                self.assertLessEqual(value(v) * self.per_sixteenth, printed + 0.005)
                self.assertGreater(value(v) * self.per_sixteenth, printed * 0.99)

    def test_the_gates_bracket_passes(self):
        report = checked(RETURNS)
        self.assertEqual(report["status"], "PASS")
        found = obligation(report, "weld")
        self.assertGreaterEqual(found["utilisation"], 0.592)
        self.assertLessEqual(found["utilisation"], 0.592 / (1 - ic.WELD_LOSS) + 0.001)

    def test_long_returns_keep_the_elastic_method(self):
        """Returns 9 in on a 4 in line, kl / L = 2.25, lie past petra.weld_ic.k_max = 2."""
        text = RETURNS.replace("weld_length 10 inch", "weld_length 4 inch").replace("weld_return 2 inch", "weld_return 9 inch")
        d = parse_design(text, "gate.petra", REGISTRY)
        welds = calc.values(calc.connection(d, "c1", REGISTRY), d, REGISTRY, "weld", "gate")
        self.assertTrue(welds and all("most stressed point" in w.what for w in welds))
        self.assertFalse(any("instantaneous center" in w.what for w in welds))


class WeldSegmentLists(unittest.TestCase):
    """ic's weld group is a list of straight welds (ic.Segment). Any group whose welds lie
    along or across the load and that is its own mirror image in the line through its
    centroid across the load runs the same search and certificate: two parallel lines 1/2
    apart and a box 1/2 by 1 at a = 1/2, against the clean-room twin's two-dimensional
    search over 2,000 elements a weld (twin/groups.py), to 1e-4 (measured 2e-5). The deck
    feeds only the line and the C, whose premises WeldInstantaneousCentrePremise measures.
    An L's centre leaves the line, and an inclined weld is not encoded: both are refused."""

    def test_two_lines_and_a_box(self):
        from twin import groups
        half, quarter = Fraction(1, 2), Fraction(1, 4)
        sides = (((-quarter, -half), (-quarter, half), Fraction(1)), ((quarter, -half), (quarter, half), Fraction(1)))
        ends = (((-quarter, half), (quarter, half), Fraction(1)), ((-quarter, -half), (quarter, -half), Fraction(1)))
        curve, a = ic.weld_curve(REGISTRY), Fraction(1, 2)
        for name, segments in (("two lines", sides), ("box", sides + ends)):
            with self.subTest(name):
                group = ic.pieces(segments)
                method = ic.weld_sums(ic.weld_balancing(float(a), curve, group), curve, group)[0]
                lines = [((float(p[0]), float(p[1])), (float(q[0]), float(q[1]))) for p, q, _ in segments]
                twin = groups.weld_strength(lines, float(a), 1.0, 70.0, elements=2000) / (0.6 * 70.0 * math.sqrt(2) / 2)
                self.assertAlmostEqual(method / twin, 1.0, delta=1e-4)
                v, gap = certificate(segments, a)
                self.assertGreater(value(gap), 0)
                self.assertLessEqual(value(v), method)
                self.assertGreater(value(v), method * (1 - 2 * ic.WELD_LOSS))

    def test_an_l_and_an_inclined_weld_are_refused(self):
        half = Fraction(1, 2)
        line = ((Fraction(0), -half), (Fraction(0), half), Fraction(1))
        self.assertIsNone(ic.pieces((line, ((Fraction(0), -half), (half, -half), Fraction(1)))))
        self.assertIsNone(ic.pieces((((Fraction(0), -half), (half, half), Fraction(1)),)))


BACK_EDGE = """petra 0

design "tearout-back-edge" {
  owner "twin@petra.dev"
}

bolt_bracket c1 {
  basis lrfd
  plate steel.A36 thickness 0.5 inch
  support W14x61 flange grade steel.A992
  bolts bolt_group.150 diameter 1 inch threads excluded
  rows 2
  columns 1
  pitch 3 inch
  gauge 3 inch
  eccentricity 6 inch
  edge_vertical 2 inch
  plate_edge 1.5 inch
}

load gate {
  on c1 shear in [0 kip, 16 kip]
  signed "twin@petra.dev" source "twin check"
}
"""


class BracketTearout(unittest.TestCase):
    """J3.11a measures tearout's clear distance lc in the direction of the force. Two 1 in
    bolts (holes 1-1/8 in) at 3 in in a 1/2 in A36 plate, the load 6 in out: both methods
    turn the group about R = s^2 (n^2 - 1) / (12 e) = 0.375 in behind the bolts, so the
    top bolt pushes the plate along (-1.5, 0.375), almost straight back. Its back edge,
    1-1/2 in away, lies 1.5 x 1.546 / 1.5 along that force, lc = 1.546 - 0.5625 = 0.984 in.
    The elastic method's C = 1 / sqrt(0.5^2 + 2^2) = 0.485 is the larger here. At 38cc6ba the
    deck took that bolt's tearout up to the top edge, lc = 2 - 0.5625 = 1.4375 in, and
    passed the bracket at 0.879; along the force it fails at 1.285."""

    C = 1 / math.hypot(0.5, 6 * 1.5 / (2 * 1.5 ** 2))

    def test_the_top_bolt_tears_toward_the_back_edge(self):
        found = obligation(checked(BACK_EDGE), "bolts")
        self.assertEqual(found["outcome"], "refuted")
        lc = 1.5 * math.hypot(1.5, 0.375) / 1.5 - 1.125 / 2
        self.assertAlmostEqual(found["utilisation"], 16 / (0.75 * self.C * 1.2 * lc * 0.5 * 58), places=6)

    def test_with_room_behind_it_the_top_edge_governs(self):
        found = obligation(checked(BACK_EDGE.replace("plate_edge 1.5 inch", "plate_edge 2.5 inch")), "bolts")
        self.assertEqual(found["outcome"], "certified")
        self.assertAlmostEqual(found["utilisation"], 16 / (0.75 * self.C * 1.2 * 1.4375 * 0.5 * 58), places=6)

    def test_the_pilots_bracket_from_the_arm_with_petra_fails(self):
        """Task 303-021 with Petra: four rows of two 7/8 in Group 120-N bolts at 2-3/4 in by
        5 in in a 5/16 in A572 Gr. 50 plate, its back edge 1-3/8 in from the bolts, 39.9
        kips ASD at 8 in. The deck passed it at 38cc6ba. The centre lies 2.32 in behind the
        centroid, inside the group, so the back column's top bolt pushes the plate 2.5
        degrees off straight back: lc = 0.908 in, 22.1 kips against 32.5 in shear, and C =
        3.08 times that holds 34.1 kips. The clean-room twin fails it too (1.17)."""
        report = petra.check_file(ROOT / "corpus" / "cases" / "pilot" / "bracket_from_the_arm.petra").to_json()
        self.assertEqual(report["status"], "FAIL")
        self.assertAlmostEqual(obligation(report, "bolts")["utilisation"], 1.17, delta=0.005)


SLOTTED = """petra 0

design "gate-1-01460" {
  owner "gate@petra.dev"
}

bolt_bracket c1 {
  basis lrfd
  plate steel.A36 thickness 0.75 inch
  support W10x49 flange grade steel.A992
  bolts bolt_group.150 diameter 1 inch threads excluded joint pretensioned
  holes plate lsl
  rows 3
  columns 1
  pitch 3 inch
  gauge 3 inch
  eccentricity 8 inch
  edge_vertical 2 inch
  plate_edge 1.5 inch
  free_edge 6 inch
}

load gate {
  on c1 shear in [0 kip, 21.044 kip]
  signed "gate@petra.dev" source "steel gate generator"
}
"""


class BracketHoles(unittest.TestCase):
    """A shaped bracket from the steel gate's stream (gate-1-01460), three 1 in bolts in
    long slots across the depth. Table J3.5 adds C2 = 3/4 d to Table J3.4's 1-1/4 in at an
    edge a slot runs toward, so the back edge needs 2 in and has 1-1/2. The sloping free
    edge runs from the bottom of section A-A to the top edge b = 6 in ahead (Manual Figure
    15-2(a)), 2 x 6 / sqrt(6^2 + 10^2) = 1.029 in from the bottom bolt, and partly along the
    slot, so it takes C2 too. J3.3 admits a long slot in a bearing-type joint only normal to
    the load, and a bracket's bolts push across the depth: the slots need a slip-critical
    joint. The deck passed it at 38cc6ba."""

    def edges(self, text: str) -> dict[str, float]:
        return {c["check"]: c["utilisation"] for c in obligation(checked(text), "edge_min")["checks"]}

    def test_the_edges_take_c2(self):
        found = self.edges(SLOTTED)
        self.assertAlmostEqual(found["bracket plate: plate side edge distance at least Table J3.4's plus Table J3.5's C2 "
                                     "for its lsl holes (J3.5)"], 2.0 / 1.5, places=6)
        self.assertAlmostEqual(found["bracket plate: plate free edge distance at least Table J3.4's plus Table J3.5's C2 "
                                     "for its lsl holes (J3.5)"], 2.0 / (2 * 6 / math.hypot(6, 10)), places=6)
        self.assertAlmostEqual(found["bracket plate: plate top and bottom edge distance at least Table J3.4's (J3.5)"],
                               1.25 / 2, places=6)

    def test_standard_holes_take_none(self):
        found = self.edges(SLOTTED.replace("  holes plate lsl\n", ""))
        self.assertAlmostEqual(found["bracket plate: plate side edge distance at least Table J3.4's (J3.5)"], 1.25 / 1.5,
                               places=6)

    def test_the_slots_need_a_slip_critical_joint(self):
        self.assertEqual(obligation(checked(SLOTTED), "hole_use")["outcome"], "refuted")
        slip = SLOTTED.replace("joint pretensioned", "joint slip_critical surface class_a")
        self.assertEqual(obligation(checked(slip), "hole_use")["outcome"], "certified")


SLOT_SLIP = """petra 0

design "gate-1-01042" {
  owner "gate@petra.dev"
}

bolt_bracket c1 {
  basis asd
  plate steel.A36 thickness 0.625 inch
  support W10x49 flange grade steel.A992
  bolts bolt_group.120 diameter 0.875 inch threads included joint slip_critical surface class_b fillers one
  holes plate ssl
  rows 3
  columns 1
  pitch 3 inch
  gauge 3 inch
  eccentricity 8 inch
  edge_vertical 1.5 inch
  plate_edge 2 inch
}

load gate {
  on c1 shear in [0 kip, 9.474 kip]
  signed "gate@petra.dev" source "steel gate generator"
}
"""


class BracketSlip(unittest.TestCase):
    """J3.9 gives a short slot normal to the load phi = 1.00 and Omega = 1.50, and one
    parallel to it 0.85 and 1.76. A bracket's bolts above and below its centroid push
    mostly across the depth, along a plain slot, as hole_use already reads them. The
    gate's bracket gate-1-01042: three 7/8 in Group 120 bolts, class B, one filler, so
    each holds mu Du hf Tb = 0.50 x 1.13 x 1.0 x 39 = 22.04 kips. The elastic method puts
    9.474 / 3 = 3.158 kips down on the top bolt and 9.474 x 8 x 3 / 18 = 12.63 kips across
    it. The deck passed it at 97407e3 against Omega = 1.50, at 0.886."""

    def test_a_plain_short_slot_in_a_bracket_takes_the_parallel_factor(self):
        report = checked(SLOT_SLIP)
        self.assertEqual(report["status"], "FAIL")
        found = obligation(report, "slip")
        self.assertEqual(found["outcome"], "refuted")
        force = math.hypot(9.474 / 3, 9.474 * 8 * 3 / 18)
        self.assertAlmostEqual(found["utilisation"], force / (0.50 * 1.13 * 1.0 * 39 / 1.76), places=6)

    def test_a_shear_tabs_short_slot_stays_normal_to_the_load(self):
        """Manual Part 10 details a shear tab's short slots horizontal, normal to its
        reaction, so a slip-critical tab keeps Omega = 1.50: four 3/4 in Group 120 bolts,
        class A, 0.30 x 1.13 x 1.0 x 28 = 9.49 kips each."""
        text = (ROOT / "examples" / "steel" / "shear_tab.petra").read_text(encoding="utf-8")
        text = text.replace("threads included", "threads included joint slip_critical surface class_a")
        text = text.replace("  rows 4\n", "  holes plate ssl\n  rows 4\n").replace("basis lrfd", "basis asd")
        found = obligation(checked(text), "slip")
        self.assertAlmostEqual(found["capacity"], 0.30 * 1.13 * 1.0 * 28 / 1.50, places=6)


WELD_ARM = """petra 0

design "gate-1-00009" {
  owner "gate@petra.dev"
}

weld_bracket c1 {
  basis asd
  plate steel.A36 thickness 0.75 inch
  support W12x50 flange grade steel.A992
  weld electrode.E70 size 0.3125 inch sides 1
  weld_length 14 inch
  weld_return 3 inch
  eccentricity 8 inch
  free_edge 6 inch
}

load gate {
  on c1 shear in [0 kip, 30.515 kip]
  signed "gate@petra.dev" source "steel gate generator"
}
"""


class WeldBracketArm(unittest.TestCase):
    """A weld bracket's eccentricity is the load's distance from its weld group's centroid
    (docs/reference.md). A C-shaped weld's centroid lies kl^2 / (L + 2 kl) inside its
    vertical line (Manual Part 8), and the load's arm to section A-A runs from the returns'
    tips. The gate's bracket gate-1-00009: a 3/4 in A36 plate on a 14 in weld with 3 in
    returns, the load 8 in from the centroid. The centroid lies 9 / 20 = 0.45 in inside the
    line, so the arm is 8 + 0.45 - 3 = 5.45 in. The free edge projects 6 in: theta =
    atan(6 / 14), b' = 14 sin theta = 5.515 in, lambda = 0.354, so Q = 1 (Manual Part 15).
    The deck read the arm from the vertical line, 5.00 in, and passed it at 03a6fbf at 0.927."""

    def test_the_arm_runs_from_the_centroid(self):
        report = checked(WELD_ARM)
        self.assertEqual(report["status"], "FAIL")
        found = obligation(report, "bracket_edge")
        self.assertEqual(found["outcome"], "refuted")
        arm = 8 + 9 / 20 - 3
        hyp = math.hypot(14, 6)
        cos, b1 = 14 / hyp, 14 * 6 / hyp
        nc = 36 * 0.75 * b1 / 1.67
        mc = 36 * 0.75 * b1 ** 2 / 4 / 1.67
        self.assertAlmostEqual(found["utilisation"], 30.515 * (cos / nc + (arm - cos * b1 / 2) / mc), places=6)


if __name__ == "__main__":
    unittest.main()
