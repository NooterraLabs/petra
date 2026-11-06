"""Steel deck ground truth, M4: eccentric bolt and weld groups, bracket plates and hangers.

Companion to the AISC Steel Construction Manual, v16.0, Vol. 1 (AISC 2023): II.A-22 (bolted
bracket plate), II.A-23 (welded bracket plate), II.A-24 and 25 (an eccentric bolt group by
the instantaneous-centre and the elastic method), II.A-26 and 27 (an eccentric C-shaped
weld group, likewise) and II.D-1 (a WT hanger with prying). Kulak, Fisher and Struik,
Guide to Design Criteria for Bolted and Riveted Joints, 2nd ed. (1987), Table 13.1: the
instantaneous-centre coefficients C of a line of bolts.

Reproduced: the elastic groups (II.A-25, 27); the bracket plates' section A-A (shear,
flexural yielding) and their free-edge section B-B (shear, the normal force and moment
with local buckling) (II.A-22, 23); the hanger's bolt tension, its flange in shear, and the
flange thickness at which prying uses the bolt up (II.D-1).

Bounded: the deck's groups are elastic, the Companion's instantaneous-centre groups carry
more (II.A-22's bolts, 23's welds, 24, 26), and so do Kulak's coefficients.

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
import unittest
from fractions import Fraction

from petra.kernel import enclose
from petra.models.steel import limits as L
from petra.registry import build_registry
from petra.units import CUSTOMARY

from tests import steel_examples as ex

INCH = CUSTOMARY["inch"][0]
KIP = CUSTOMARY["kip"][0]
KSI = CUSTOMARY["ksi"][0]
REGISTRY = build_registry()


def const(name: str) -> L.Const:
    return L.c(REGISTRY.constants[name].value.lo)


def inch(x) -> L.Const:
    return L.c(Fraction(x) * INCH)


def value(expr, per=1) -> float:
    return float(enclose(expr, {}).lo / per)


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
    # Table 7-8: C = 4.53 at ex = 12 in, times the bolt's 17.9 / 11.9 kips (bolt shear governs).
    bounded = {("bolts", "bracket bolts:"): ("81.1", "53.9")}

    def test_flexural_rupture_at_the_tables_edge_distance(self):
        body = self.body.replace("edge_vertical 2.5 inch", "edge_vertical 1.5 inch")
        for basis, printed in (("lrfd", "1,050"), ("asd", "700")):
            self.near(self.strength(basis, "flexural_rupture", "bracket plate:", body), printed, f"{self.tag} {basis}")

    def test_net_plastic_modulus_of_table_15_2(self):
        z = L.plate_net_modulus(inch("0.375"), inch(18), 6, inch(3), inch(Fraction(7, 8)))
        self.near(value(z, INCH ** 3), "21.5", "Znet")

    def test_normal_force_and_moment_on_the_free_edge(self):
        for basis, printed in (("lrfd", "0.864"), ("asd", "0.862")):
            found, _ = self.values(basis, "bracket_edge")
            ratio = max(v.utilisation for v in found if "normal force and moment" in v.what and not v.excused)
            self.near(ratio, printed, f"{self.tag} {basis}", 0.012)


class IIA23(ex.Example):
    """A welded bracket plate: two PL3/8 A572 Gr. 50 lapped on the column, each welded by a
    3/16 in E70 C-shaped fillet, 18 in long with 3 in returns, the load 11-1/4 in from the
    vertical weld (8-1/4 in from section A-A at the returns' tips), the free edge projecting
    11-1/2 in. Pu = 54.0, Pa = 36.0 kips shared by the two plates; the design models one."""

    tag, kind, plates, loads = "II.A-23", "weld_bracket", 2, ("27.0", "18.0")
    body = ("  plate steel.A572_50 thickness 0.375 inch\n  support W14x90 flange grade steel.A992\n"
            "  weld electrode.E70 size 0.1875 inch sides 1\n  weld_length 18 inch\n  weld_return 3 inch\n"
            "  eccentricity 11.25 inch\n  free_edge 11.5 inch\n")
    printed = {
        ("shear_yield", "bracket plate:"): ("405", "270"),
        ("flexural_yield", "bracket plate:"): ("2,740", "1,820"),
    }
    moments = ("flexural_yield",)
    availables = {("bracket_edge", "bracket plate: shear yielding of the free-edge"): ("218", "145")}
    # Table 8-8: C = 1.46, C1 = 1.00, D = 3, l = 18 in, two plates: 0.75 C C1 D l and C C1 D l / 2.00.
    bounded = {("weld", "bracket weld:"): ("118", "78.8")}

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
        self.near(edge[0].available, "0.3125", "maximum along the edge")
        self.assertTrue(all(v.utilisation <= 1 for v in live.values()))


GROUP_24 = ("  plate steel.A36 thickness 0.875 inch\n  support W14x90 flange grade steel.A992\n"
            "  bolts bolt_group.120 diameter 0.875 inch threads included\n  rows 6\n  columns 2\n  pitch 3 inch\n"
            "  gauge 5.5 inch\n  eccentricity 16 inch\n  edge_vertical 1.5 inch\n  plate_edge 1.5 inch\n")


class IIA24And25(ex.Example):
    """Two columns of six 7/8 in Group 120-N bolts in single shear (gauge 5-1/2, pitch 3), a
    vertical load 16 in from the centroid; bolt shear governs (24.3 / 16.2 kips a bolt).
    II.A-25 is the elastic method; II.A-24 the instantaneous centre (C = 3.55)."""

    tag, kind, body, loads = "II.A-25", "bolt_bracket", GROUP_24, ("60", "40")
    printed = {("bolts", "bracket bolts:"): ("69.0", "46.0")}
    bounded = {("bolts", "bracket bolts:"): ("86.3", "57.5")}


class IIA26And27(ex.Example):
    """A C-shaped 3/8 in E70 fillet, 10 in long with 5 in returns, a vertical load 10 in from
    the vertical weld (ex = 8.75 in from the centroid). II.A-27 is the elastic method;
    II.A-26 the instantaneous centre (C = 1.88)."""

    tag, kind, loads = "II.A-27", "weld_bracket", ("40", "25")
    body = ("  plate steel.A36 thickness 0.5 inch\n  support W14x90 flange grade steel.A992\n"
            "  weld electrode.E70 size 0.375 inch sides 1\n  weld_length 10 inch\n  weld_return 5 inch\n"
            "  eccentricity 10 inch\n")
    printed = {("weld", "bracket weld:"): ("47.2", "31.5")}
    bounded = {("weld", "bracket weld:"): ("84.8", "56.5")}


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
        fx, fy = L.elastic_bolt_force(L.c(1), inch(lever), L.c(n), n, 1, inch(3), L.c(0))
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


if __name__ == "__main__":
    unittest.main()
