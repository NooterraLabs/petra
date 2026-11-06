"""Steel deck ground truth: the Companion to the AISC Steel Construction Manual, v16.0,
Vol. 1 Design Examples (AISC 2023), reproduced to rounding.

Each test names its example. It states the example's inputs and the numbers the Companion
prints, nothing more. It recomputes those numbers through petra.models.steel.limits from
the registry's rows, or through the connection elaborator for a whole connection.

"To rounding" means within one unit of the printed number's last digit. The Companion
rounds its intermediate values to three figures, and a value computed from those rounded
intermediates can move its last digit by one. Example J.3's ASD F'nt, printed 76.7 ksi,
is 76.8 ksi from the unrounded shear stress.

Out of scope here: J.2A, a fillet loaded at 60 degrees to its axis (the deck takes kds = 1
and never Eq J2-5's directional increase, so it has no such weld to check), J.2B, a PJP
groove weld (groove welds join the deck in v1.1), and J.6, bearing on concrete (Section
J8, v1.1).
"""
import unittest
from decimal import Decimal
from fractions import Fraction

from petra.kernel import enclose
from petra.lang import parse_design
from petra.models.steel import calc
from petra.models.steel import limits as L
from petra.registry import build_registry
from petra.units import CUSTOMARY

REGISTRY = build_registry()
INCH, KIP, KSI = (CUSTOMARY[u][0] for u in ("inch", "kip", "ksi"))


def const(name: str):
    return L.c(REGISTRY.constants[name].value.lo)


def prop(material: str, name: str):
    return L.c(REGISTRY.materials[material].props[name].value.lo)


def value(expr, per=KIP) -> float:
    return float(enclose(expr, {}).lo / per)


def inch(x) -> L.Const:
    return L.c(Fraction(x) * INCH)


def kips(x) -> L.Const:
    return L.c(Fraction(x) * KIP)


def three(x: float) -> float:
    """x rounded to three significant figures, as the Companion rounds an intermediate."""
    return float(f"{x:.3g}")


class Published(unittest.TestCase):
    def published(self, computed: float, printed: str, what: str = "", rel: float | None = None) -> None:
        """`computed` is within one unit of `printed`'s last digit, or within `rel` of it
        where the test says which rounded intermediate the Companion carried forward."""
        digits = Decimal(printed.replace(",", ""))
        unit = float(Decimal(1).scaleb(digits.as_tuple().exponent))
        allowed = unit if rel is None else rel * float(digits)
        self.assertLessEqual(abs(computed - float(digits)), allowed, f"{what}: computed {computed:.4f}, printed {printed}")


class J1FilletWeldInLongitudinalShear(Published):
    """A 1/4 in plate lapped on a 3/8 in plate, A572 Gr. 50, two 3/16 in E70 fillets 27 in
    long, end-loaded. Pu = 200 kips, Pa = 133 kips."""

    w, length = inch(Fraction(3, 16)), inch(27)

    def test_weld_strength_with_the_end_loaded_reduction(self):
        fexx = prop("electrode.E70", "FEXX")
        per_inch = L.fillet_per_length(const, fexx, self.w)
        self.published(value(per_inch, KIP / INCH), "5.57", "Rn per inch")
        beta = value(L.end_loaded_length(const, self.length, self.w), INCH) / 27
        self.published(beta, "0.912", "beta, Eq J2-1")
        rn = L.mul(L.c(2), L.fillet_line(const, fexx, self.w, L.end_loaded_length(const, self.length, self.w)))
        self.published(value(rn), "274", "Rn")
        self.published(value(L.mul(const("aisc360.j2_4.phi"), rn)), "206", "phi Rn")
        self.published(value(L.div(rn, const("aisc360.j2_4.omega"))), "137", "Rn / Omega")

    def test_base_metal_of_the_thinner_plate(self):
        rn = L.mul(L.base_metal_per_length(const, prop("steel.A572_50", "fu"), inch(Fraction(1, 4))), L.c(2), self.length)
        self.published(value(rn), "527", "Rn")
        self.published(value(L.mul(const("aisc360.j2_4.phi"), rn)), "395", "phi Rn")
        self.published(value(L.div(rn, const("aisc360.j2_4.omega"))), "264", "Rn / Omega")

    def test_effective_length_limits(self):
        w = inch(Fraction(1, 4))
        for l_over_w, effective in ((50, 50), (100, 100), (200, 200 * Fraction(4, 5)), (300, 180), (400, 180)):
            got = value(L.end_loaded_length(const, L.mul(L.c(l_over_w), w), w), INCH / 4)
            self.assertAlmostEqual(got, float(effective), places=9, msg=f"l/w = {l_over_w}")


class J3CombinedTensionAndShearInBearing(Published):
    """A 3/4 in Group 120 bolt, threads included: Tu = 23.4, Vu = 8.00; Ta = 15.5, Va = 5.33."""

    d = const("bolt_us.3_4.d")

    def test_lrfd_and_asd(self):
        fnt, fnv = prop("bolt_group.120", "Fnt"), prop("bolt_group.120", "Fnv_N")
        ab = L.bolt_area(self.d)
        for basis, factor, v, printed in (("lrfd", "phi", "8.00", ("40.5", "18.1", "76.8", "25.5")),
                                          ("asd", "omega", "5.33", ("27.0", "12.1", "76.7", "17.0"))):
            with self.subTest(basis=basis):
                lrfd = basis == "lrfd"
                f = const(f"rcsc2025.s5_1.{factor}")
                available_fnv = L.mul(f, fnv) if lrfd else L.div(fnv, f)
                frv = L.div(kips(Fraction(v)), ab)
                fnt_prime = L.combined_fnt(const, fnt, fnv, frv, f, lrfd)
                rn = L.mul(fnt_prime, ab)
                self.published(value(available_fnv, KSI), printed[0], "available Fnv")
                self.published(value(frv, KSI), printed[1], "frv")
                self.published(value(fnt_prime, KSI), printed[2], "F'nt, Eq J3-3")
                self.published(value(L.mul(f, rn) if lrfd else L.div(rn, f)), printed[3], "available tension")


class J4SlipCritical(Published):
    """3/4 in Group 120 bolts, Class A, no fillers, two slip planes; Pu = 102, Pa = 68.0 kips."""

    def per_bolt(self):
        return L.slip(const("rcsc2025.s5_4.mu_a"), const("rcsc2025.s5_4.Du"), const("rcsc2025.s5_4.hf_one"),
                      const("bolt_us.3_4.Tm_g120"), L.c(2), L.c(1))

    def check(self, suffix: str, printed: tuple[str, str, str, str, str]) -> None:
        rn = self.per_bolt()
        self.published(value(rn), printed[0], "Rn per bolt, Eq J3-4")
        lrfd = value(L.mul(const(f"rcsc2025.s5_4.phi{suffix}"), rn))
        asd = value(L.div(rn, const(f"rcsc2025.s5_4.omega{suffix}")))
        self.published(lrfd, printed[1], "phi Rn")
        self.published(asd, printed[2], "Rn / Omega")
        # The Companion divides by its per-bolt strength rounded to three figures.
        self.published(102 / three(lrfd), printed[3], "bolts needed, LRFD")
        self.published(68 / three(asd), printed[4], "bolts needed, ASD")

    def test_j4a_short_slots_transverse_to_the_load(self):
        self.check("_std", ("19.0", "19.0", "12.7", "5.37", "5.35"))

    def test_j4b_long_slots(self):
        self.check("_lsl", ("19.0", "13.3", "8.88", "7.67", "7.66"))


class J5CombinedTensionAndShearSlipCritical(Published):
    """Eight 3/4 in Group 120 bolts, one slip plane, Class A, standard holes:
    Tu = 72.0, Vu = 54.0; Ta = 48.0, Va = 36.0 kips."""

    def test_tension_and_reduced_slip(self):
        d, tb, du = const("bolt_us.3_4.d"), const("bolt_us.3_4.Tm_g120"), const("rcsc2025.s5_4.Du")
        rn_t = L.bolt_tension(prop("bolt_group.120", "Fnt"), d)
        self.published(value(rn_t), "39.8", "Rn tension")
        self.published(value(L.mul(const("rcsc2025.s5_1.phi"), rn_t)), "29.9", "phi Rn")
        self.published(value(L.div(rn_t, const("rcsc2025.s5_1.omega"))), "19.9", "Rn / Omega")
        for basis, t, factor, printed in (("lrfd", "72.0", None, ("9.49", "54.4")), ("asd", "48.0", L.c("1.5"), ("6.33", "36.3"))):
            with self.subTest(basis=basis):
                ksc = L.slip_ksc(L.div(kips(Fraction(t)), L.c(8)), du, tb, factor)
                self.published(value(ksc, 1), "0.716", "ksc, Eq J3-5")
                rn = L.slip(const("rcsc2025.s5_4.mu_a"), du, const("rcsc2025.s5_4.hf_one"), tb, L.c(1), L.c(1))
                per_bolt = L.mul(const("rcsc2025.s5_4.phi_std"), rn) if factor is None else L.div(rn, const("rcsc2025.s5_4.omega_std"))
                self.published(value(per_bolt), printed[0], "available slip per bolt")
                self.published(value(L.mul(per_bolt, ksc, L.c(8))), printed[1], "available slip of the group")


GIRDER = """petra 0

design "companion-j7" {{
  owner "s.engineer@example.org"
}}

flange_force girder {{
  basis {basis}
  member W24x55 grade steel.A992
  bearing_length 7.5 inch
  location interior
  force_kind compressive
  flange_restrained yes
  unbraced_length 240 inch
  moment_at_force below_yield
}}

load reaction {{
  on girder force in [0 kip, {force} kip]
  signed "s.engineer@example.org" source "Companion Example J.7"
}}
"""


class J7ConcentratedForcesOnAGirder(Published):
    """A W18x50 beam bearing on the top flange of a W24x55 girder, A992, lb = 7.50 in, away
    from the girder's ends, compression flange restrained, Lb = 20 ft; Ru = 66.0, Ra = 45.0
    kips. Through the elaborator, as a flange_force connection.

    Sidesway buckling (Eq J10-6) cubes r = (h/tw)/(Lb/bf), which the Companion rounds to
    1.59 before cubing; unrounded it is 1.595, which raises Rn from 167 to 168.4 kips (h is
    d - 2 kdes = 21.58 in here, the Companion's h/tw times tw = 21.6 in). The test allows
    1 % there and checks the printed value from the rounded r directly."""

    def available(self, basis: str, force: str) -> dict[str, float]:
        d = parse_design(GIRDER.format(basis=basis, force=force), "j7.petra", REGISTRY)
        conn = calc.connection(d, "girder", REGISTRY)
        found = {}
        for mode in ("web_local_yielding", "web_crippling", "web_sidesway_buckling"):
            for v in calc.values(conn, d, REGISTRY, mode, "reaction"):
                found[mode] = v.available
        return found

    def test_lrfd(self):
        found = self.available("lrfd", "66")
        self.published(found["web_local_yielding"], "248", "phi Rn, Eq J10-2")
        self.published(found["web_crippling"], "212", "phi Rn, Eq J10-4")
        self.published(found["web_sidesway_buckling"], "142", "phi Rn, Eq J10-6", rel=0.01)

    def test_asd(self):
        found = self.available("asd", "45")
        self.published(found["web_local_yielding"], "165", "Rn / Omega, Eq J10-2")
        self.published(found["web_crippling"], "141", "Rn / Omega, Eq J10-4")
        self.published(found["web_sidesway_buckling"], "94.9", "Rn / Omega, Eq J10-6", rel=0.01)

    def test_sidesway_at_the_companions_rounded_ratio(self):
        # Rn = Cr tw^3 tf / h^2 (1 + 0.4 r^3) with h = 21.6 in and r = 1.59, as printed.
        tw, tf, h, r = 0.395, 0.505, 21.6, 1.59
        rn = 960000 * tw ** 3 * tf / h ** 2 * (1 + 0.4 * r ** 3)
        self.published(rn, "167", "Rn at the rounded ratio")
        cr = value(const("aisc360.j10_4.cr_below_my"), KSI)
        self.assertEqual(cr, 960000.0)


if __name__ == "__main__":
    unittest.main()
