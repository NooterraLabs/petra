"""The cosine: the step `cos` of a tape and the operator `cos` of a deck (docs/format.md, docs/deck.md).

A tape takes the cosine of an angle in radians. The enclosure of a point is the two points
of the grid of 2^-96 around its cosine. Over a range it is from the grid points of the two
ends, or reaches to 1 or to -1 where the cosine may turn in the range, and from -1 to 1 for
a range that may hold two turns. An angle beyond 65,536 has no cosine.

The reference each enclosure is held to is worked out here another way: pi from
pi/4 = atan(1/2) + atan(1/3), the angle less a whole number of turns, and the plain series
of the cosine, in exact fractions with the rest of each series bounded. The kernel takes pi
from Machin's formula, halves the angle and doubles it again.

The classes named Kernel run petra-verify, and are skipped when none is built.
"""
import json
import random
import re
import unittest
from fractions import Fraction as F

from petra import deck, grid, verify
from petra.kernel import Add, Const, Cos, Div, Interval, KernelArithmeticError, Mul, Neg, Pi, Sym, enclose, i_cos, i_pi
from tests.test_kernel_attacks2 import MB, measured, total
from tests.test_kernel_grid import ask, changed, findings, strips
from tests.test_kernel_limits import old_path

STEP = F(1, 2 ** 96)
"""One step of the grid."""
TOLERANCE = F(1, 10 ** 60)
"""How far apart the two ends of a reference are, at most."""


def _atan_inverse(n: int, error: F) -> tuple[F, F]:
    """atan(1/n) between two fractions `error` apart at most: its series alternates and its terms fall."""
    total, k, power = F(0), 0, F(1, n)
    while True:
        term = power / (2 * k + 1)
        total += term if k % 2 == 0 else -term
        if term < error:
            return total - term, total + term
        power /= n * n
        k += 1


PI_LOW, PI_HIGH = (4 * (_atan_inverse(2, F(1, 10 ** 90))[side] + _atan_inverse(3, F(1, 10 ** 90))[side]) for side in (0, 1))
"""Pi between two fractions, by a formula the kernel does not use."""


def reference(x: F) -> tuple[F, F]:
    """cos x between two fractions at most TOLERANCE apart. The angle less the nearest whole
    number of turns is at most 3.2 in size. It is cut to 80 digits, which moves its cosine by
    no more than it moves the angle. Past the term n with 2n > 4 the terms of the series
    fall, and the series alternates, so the rest after a term is at most the next term."""
    turns = round(x / (PI_LOW + PI_HIGH))
    low, high = (x - 2 * turns * end for end in ((PI_HIGH, PI_LOW) if turns >= 0 else (PI_LOW, PI_HIGH)))
    cut = F(round((low + high) / 2 * 10 ** 80), 10 ** 80)
    slack = max(high - cut, cut - low)
    assert abs(cut) < 4 and slack < F(1, 10 ** 70)
    term, total, n = F(1), F(1), 0
    while n < 3 or term > F(1, 10 ** 70):
        n += 1
        term = term * cut * cut / ((2 * n - 1) * (2 * n))
        total += term if n % 2 == 0 else -term
    return total - term - slack, total + term + slack


def point(x) -> Interval:
    return Interval.point(F(x))


def cos_of(lo, hi=None) -> Interval:
    return i_cos(Interval(F(lo), F(lo if hi is None else hi)))


PI = i_pi()
POINTS = [F(1), F(-1), F(1, 2), F(3), F(4), F(22, 7), F(355, 113), F(10), F(-10), F(100), F(1000) + F(1, 3), F(65536), F(-65536), F(65535) + F(999, 1000),
          F(3, 7), F(7, 3), PI.lo / 3, PI.hi / 4, PI.lo * 5 / 2 + F(1, 1000), F(10 ** 300 + 7, 9 * 10 ** 299 + 1), F(2 ** 400 + 1, 3 ** 250), F(-(5 ** 200), 7 ** 170)]
"""Angles whose cosine is not within 10^-60 of a point of the grid."""


class Points(unittest.TestCase):
    def test_the_enclosure_of_a_point_holds_its_cosine_and_is_one_step_wide(self):
        for x in POINTS:
            with self.subTest(x=float(x)):
                e, (low, high) = cos_of(x), reference(x)
                self.assertLessEqual(high - low, TOLERANCE)
                self.assertTrue(e.lo <= low and high <= e.hi, "the cosine is in the enclosure")
                self.assertEqual(e.hi - e.lo, STEP, "its ends are next to each other on the grid")
                self.assertEqual((e.lo / STEP).denominator, 1, "and are points of the grid")

    def test_the_cosine_of_zero_is_one_and_no_interval(self):
        self.assertEqual(cos_of(0), point(1))

    def test_an_angle_and_its_negative_have_one_cosine(self):
        for x in POINTS:
            self.assertEqual(cos_of(x), cos_of(-x))

    def test_a_tiny_angle_has_a_cosine_one_step_under_one_at_most(self):
        """cos x is under 1 and over 1 - x^2 / 2, so for a tiny x it lies in the last step under 1."""
        for x in (F(1, 10 ** 30), F(-1, 10 ** 30), F(1, 2 ** 200), F(1, 2 ** 1200), F(3, 2 ** 5000), F(1, 2 ** 49)):
            self.assertEqual(cos_of(x), Interval(1 - STEP, F(1)), x)
        wider = cos_of(F(1, 2 ** 47))
        self.assertEqual(wider.hi - wider.lo, STEP)
        self.assertLess(wider.hi, 1, "an angle of 2^-47 has a cosine 2^-95 under 1, which is two steps")

    def test_an_angle_next_to_a_half_turn_has_a_cosine_one_step_over_minus_one(self):
        for x in (PI.lo, PI.hi, -PI.lo, 3 * PI.lo, 3 * PI.hi, PI.lo - F(1, 2 ** 300), 20001 * PI.hi):
            self.assertEqual(cos_of(x), Interval(F(-1), -1 + STEP), float(x))
        for x in (2 * PI.lo, 2 * PI.hi, -4 * PI.hi, 20000 * PI.lo):
            self.assertEqual(cos_of(x), Interval(1 - STEP, F(1)), float(x))

    def test_no_enclosure_reaches_past_one_or_minus_one(self):
        rng = random.Random(11)
        for _ in range(300):
            x = F(rng.randrange(-65536 * 10 ** 6, 65536 * 10 ** 6), 10 ** 6)
            e = cos_of(x)
            self.assertTrue(-1 <= e.lo < e.hi <= 1 or x == 0, x)

    def test_a_cosine_too_near_zero_to_round_has_no_value(self):
        """An angle within 2^-2300 of a quarter turn has a cosine that close to zero, a point of
        the grid. The finest enclosure is of 2,144 bits and does not say on which side of zero
        it lies, so the angle has no cosine. One within 2^-140 of it takes the second enclosure."""
        from petra.kernel.interval import _pi_at
        quarter = _pi_at(None, 2500).lo / 2
        near = F(round(quarter * 2 ** 2300), 2 ** 2300)
        with self.assertRaisesRegex(KernelArithmeticError, "separated"):
            cos_of(near)
        nearer = F(round(quarter * 2 ** 140), 2 ** 140)
        e = cos_of(nearer)
        self.assertEqual(e.hi - e.lo, STEP)
        self.assertTrue(e.lo == 0 or e.hi == 0)


RANGES = [(0, 1), (-1, 1), (-1, 0), (1, 3), (3, 4), (3, 7), (0, 7), (-4, -3), (-7, -6), (6, 7), (F(1, 3), F(1, 3)), (-3, 3), (-4, 4), (F(-7, 2), F(1, 10)),
          (100, 101), (100, 104), (-65536, -65535), (65535, 65536), (0, PI.lo), (0, PI.hi), (PI.lo, PI.hi), (PI.lo / 2, PI.hi / 2), (2 * PI.lo, 2 * PI.hi),
          (-PI.hi, -PI.lo), (F(-1, 2 ** 100), F(1, 2 ** 100)), (F(31415926, 10 ** 7), F(31415927, 10 ** 7)), (PI.hi, 2 * PI.lo), (PI.lo, 2 * PI.hi),
          (F(1, 10 ** 30), F(1)), (F(10 ** 300 + 7, 9 * 10 ** 299 + 1), F(12, 10))]


PI_MID = (PI_LOW + PI_HIGH) / 2


def turning(lo: F, hi: F) -> list[int]:
    """The whole numbers k with k pi in [lo, hi], for a range under 100 long with no end next to one."""
    first = round(lo / PI_MID)
    return [k for k in range(first - 2, first + 40) if lo <= k * PI_MID <= hi]


def beside_a_turn(x: F) -> bool:
    """Whether x is within 10^-20 of a multiple of pi."""
    return abs(x - round(x / PI_MID) * PI_MID) < F(1, 10 ** 20)


class Ranges(unittest.TestCase):
    def test_the_enclosure_of_a_range_holds_the_cosine_of_points_of_the_range(self):
        rng = random.Random(7)
        for lo, hi in RANGES:
            lo, hi = F(lo), F(hi)
            e = cos_of(lo, hi)
            for t in [F(0), F(1), F(1, 2), *(F(rng.randrange(1, 10 ** 6), 10 ** 6) for _ in range(12))]:
                x = lo + (hi - lo) * t
                low, high = reference(x)
                self.assertTrue(e.lo <= high and low <= e.hi, (float(lo), float(hi), float(x)))
                if all(abs(low - at) > 2 * STEP for at in (-1, 0, 1)):
                    self.assertTrue(e.lo <= low and high <= e.hi, (float(lo), float(hi), float(x)))

    def test_the_enclosure_of_a_range_is_no_wider_than_the_cosine_and_a_step_at_each_end(self):
        """The least and the greatest of the cosine over a range are at its ends or at a
        multiple of pi inside it. The enclosure reaches no more than a step past either."""
        rng = random.Random(3)
        ranges = [(F(lo), F(hi)) for lo, hi in RANGES]
        for _ in range(200):
            lo = F(rng.randrange(-40 * 10 ** 4, 40 * 10 ** 4), 10 ** 4)
            ranges.append((lo, lo + F(rng.randrange(0, 8 * 10 ** 4), 10 ** 4)))
        for lo, hi in ranges:
            if hi - lo > 100 or ((beside_a_turn(lo) or beside_a_turn(hi)) and (lo, hi) != (F(0), F(0))):
                continue      # a turn that pi does not place: the test of such an end is below
            e = cos_of(lo, hi)
            values = [*reference(lo), *reference(hi), *(F((-1) ** (k % 2)) for k in turning(lo, hi))]
            self.assertLessEqual(e.lo, min(values))
            self.assertGreaterEqual(e.hi, max(values))
            self.assertLessEqual(min(values) - e.lo, STEP + TOLERANCE, (float(lo), float(hi)))
            self.assertLessEqual(e.hi - max(values), STEP + TOLERANCE, (float(lo), float(hi)))

    def test_where_the_cosine_goes_one_way_the_ends_are_the_grid_points_of_the_two_ends(self):
        for lo, hi, falls in ((0, 1, True), (1, 3, True), (F(1, 10), PI.lo, True), (-3, -1, False), (4, 6, False), (PI.hi, 2 * PI.lo, False), (7, 9, True), (-1, 0, False)):
            e = cos_of(lo, hi)
            first, second = cos_of(lo), cos_of(hi)
            self.assertEqual((e.lo, e.hi), (second.lo, first.hi) if falls else (first.lo, second.hi), (lo, hi))

    def test_a_range_over_a_turn_reaches_to_the_turn_and_no_further(self):
        """Over zero the cosine reaches 1 and no more, and the lower end is the lesser of the
        two ends' own. Over pi it reaches -1."""
        self.assertEqual(cos_of(-1, 2), Interval(cos_of(2).lo, F(1)))
        self.assertEqual(cos_of(-2, 1), Interval(cos_of(2).lo, F(1)))
        self.assertEqual(cos_of(3, 4), Interval(F(-1), cos_of(4).hi))
        self.assertEqual(cos_of(2, 4), Interval(F(-1), cos_of(2).hi))
        self.assertEqual(cos_of(6, 7), Interval(cos_of(7).lo, F(1)))
        self.assertEqual(cos_of(0, 1), Interval(cos_of(1).lo, F(1)))
        self.assertEqual(cos_of(0, 0), point(1))

    def test_a_range_over_two_turns_is_from_minus_one_to_one(self):
        for lo, hi in ((0, 7), (3, 7), (-1, 4), (-100, 100), (-65536, 65536), (0, 2 * PI.hi), (PI.lo, 2 * PI.hi)):
            self.assertEqual(cos_of(lo, hi), Interval(F(-1), F(1)), (lo, hi))

    def test_an_end_that_pi_does_not_place_counts_as_on_both_sides_of_the_turn(self):
        """The kernel's pi is two fractions 2^-96 apart. An end between them may be on either
        side of pi, and the enclosure then reaches to -1, which is within a step of what the
        cosine of that end is."""
        between = (PI.lo + PI.hi) / 2
        self.assertEqual(cos_of(3, between), Interval(F(-1), cos_of(3).hi))
        self.assertEqual(cos_of(between, 4), Interval(F(-1), cos_of(4).hi))
        self.assertEqual(cos_of(between, between), Interval(F(-1), -1 + STEP))
        self.assertEqual(cos_of(3, PI.lo), Interval(F(-1), cos_of(3).hi), "an end at the lower fraction is at or under pi")

    def test_an_angle_beyond_65536_has_no_cosine(self):
        self.assertEqual(cos_of(65536).hi - cos_of(65536).lo, STEP)
        for lo, hi in ((65536 + F(1, 2 ** 200), 65536 + F(1, 2 ** 200)), (-65536 - F(1, 10 ** 9), -65536), (65535, 65537), (-70000, 0), (10 ** 9, 10 ** 9), (-(2 ** 70000), 2 ** 70000)):
            with self.assertRaisesRegex(KernelArithmeticError, "cos of a value beyond 65536"):
                cos_of(lo, hi)

    def test_an_expression_takes_a_cosine_and_a_sine_is_the_cosine_of_a_quarter_turn_less_the_angle(self):
        box = {"x": Interval(F(1, 2), F(1))}
        self.assertEqual(enclose(Cos(Sym("x")), box), cos_of(F(1, 2), 1))
        sine = enclose(Cos(Add((Div(Pi(), Const(F(2))), Neg(Sym("x"))))), box)
        low, high = sorted(F(v) for v in ("0.479425538604203000273287935215571388081803367940600675188616613125535", "0.841470984807896506652502321630298999622563060798371065672751709991910"))
        self.assertTrue(sine.lo <= low and high <= sine.hi, "sin 1/2 and sin 1 to 69 places")
        self.assertLess((sine.hi - sine.lo) - (high - low), 4 * STEP)
        degrees = enclose(Cos(Mul((Const(F(60)), Div(Pi(), Const(F(180)))))), {})
        self.assertTrue(degrees.lo < F(1, 2) < degrees.hi and degrees.hi - degrees.lo <= 2 * STEP, "cos 60 degrees is 1/2")


def num(x: F) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def angle(lo: F, hi: F) -> list[list]:
    """Nodes whose last has the enclosure [lo, hi]: lo + (hi - lo) t for the input t in [0, 1]."""
    return [["c", num(lo)], ["c", num(hi - lo)], ["s", 0], ["mul", [1, 2]], ["add", [0, 3]]]


def at_most(nodes: list[list], bound: F) -> dict:
    """The tape that says the last node is at most `bound`."""
    nodes = [*nodes, ["c", num(-bound)]]
    nodes.append(["add", [len(nodes) - 2, len(nodes) - 1]])
    return {"inputs": [{"label": "dsg:t", "lo": "0", "hi": "1"}], "nodes": nodes, "roots": [len(nodes) - 1]}


def at_least(nodes: list[list], bound: F) -> dict:
    nodes = [*nodes, ["neg", len(nodes) - 1], ["c", num(bound)]]
    nodes.append(["add", [len(nodes) - 2, len(nodes) - 1]])
    return {"inputs": [{"label": "dsg:t", "lo": "0", "hi": "1"}], "nodes": nodes, "roots": [len(nodes) - 1]}


def proved(tapes: list[dict]) -> list[dict]:
    """What the kernel says of each tape, offered as proved on one leaf."""
    cells = [{"subject": "s", "mechanism": "m", "entry": str(k), "state": "proved", "tape": tape, "partition": "leaf"} for k, tape in enumerate(tapes)]
    said = ask(old_path(cells, []))
    assert not said["findings"], said["findings"]
    return said["cells"]


ABOVE = "leaf 0: root 0 is above zero"


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class KernelEnds(unittest.TestCase):
    """The kernel's enclosure of a cosine has the ends that petra/kernel/interval.py gives it,
    to the last bit. A tape cannot print an enclosure, so four tapes ask about each range:
    that the cosine is at most the upper end, and at least the lower, which the kernel proves
    when its ends are no wider, and the same with a limit one step inside, which it proves
    only when its ends are narrower. Both ends are points of the grid, so the first two proved
    and the last two not is the same two ends."""

    def assertSameEnds(self, ranges: list[tuple[F, F]]) -> None:
        tapes = []
        for lo, hi in ranges:
            e = cos_of(lo, hi)
            nodes = [*angle(lo, hi), ["cos", 4]]
            tapes += [at_most(nodes, e.hi), at_least(nodes, e.lo), at_most(nodes, e.hi - STEP), at_least(nodes, e.lo + STEP)]
        cells = proved(tapes)
        for k, (lo, hi) in enumerate(ranges):
            four = cells[4 * k:4 * k + 4]
            self.assertEqual([c["state"] for c in four], ["proved", "proved", "open", "open"], (float(lo), float(hi), [c.get("reason") for c in four]))
            self.assertEqual([c["reason"] for c in four[2:]], [ABOVE, ABOVE], "open because the limit is inside the enclosure, and for no other reason")

    def test_at_the_points(self):
        self.assertSameEnds([(x, x) for x in [F(0), *POINTS, F(1, 10 ** 30), F(1, 2 ** 1200), PI.lo, PI.hi, 2 * PI.lo, PI.lo / 2, PI.hi / 2]])

    def test_over_the_ranges(self):
        self.assertSameEnds([(F(lo), F(hi)) for lo, hi in RANGES])

    def test_over_ranges_drawn_at_random(self):
        rng = random.Random(19)
        ranges = []
        for k in range(160):
            scale = rng.choice([1, 1, 10, 1000, 60000])
            lo = F(rng.randrange(-scale * 10 ** 6, scale * 10 ** 6), 10 ** 6)
            wide = rng.choice([F(0), F(1, 10 ** 9), F(rng.randrange(1, 10 ** 6), 10 ** 6), F(rng.randrange(1, 7 * 10 ** 6), 10 ** 6)])
            if k % 8 == 0:      # an end on a multiple of the kernel's pi, or next to one
                lo = rng.choice([PI.lo, PI.hi]) * rng.randrange(-20, 21) / rng.choice([1, 2]) + rng.choice([F(0), F(1, 2 ** 97), F(-1, 2 ** 200)])
            if abs(lo) <= 65536 and lo + wide <= 65536:
                ranges.append((lo, lo + wide))
        self.assertSameEnds(ranges)

    def test_with_long_fractions(self):
        rng = random.Random(23)
        long = [F(rng.getrandbits(bits) | 1, rng.getrandbits(bits) | 1 << (bits - 1)) for bits in (200, 1000, 4000, 6000)]
        self.assertSameEnds([(x, x) for x in long] + [(long[0], long[0] + F(1, 3)), (-long[1] * 5, long[2] * 5)])

    def test_with_fractions_longer_than_a_file_writes(self):
        """A number of a file has at most 4,000 characters. A tape makes a longer one by
        arithmetic: here a fraction of 16,000 bits a side, as the product of four."""
        rng = random.Random(29)
        parts = [F(rng.getrandbits(4000) | 1, rng.getrandbits(4000) | 1 << 3999) for _ in range(4)]
        x = parts[0] * parts[1] * parts[2] * parts[3]
        self.assertGreater(x.denominator.bit_length(), 15_000)
        e = cos_of(x)
        nodes = [*(["c", num(p)] for p in parts), ["mul", [0, 1, 2, 3]], ["cos", 4]]
        tapes = [{"inputs": [], "nodes": [*nodes, *more], "roots": [len(nodes) + len(more) - 1]} for more in (
            [["c", num(-e.hi)], ["add", [5, 6]]], [["neg", 5], ["c", num(e.lo)], ["add", [6, 7]]],
            [["c", num(-(e.hi - STEP))], ["add", [5, 6]]], [["neg", 5], ["c", num(e.lo + STEP)], ["add", [6, 7]]])]
        self.assertEqual([c["state"] for c in proved(tapes)], ["proved", "proved", "open", "open"])

    def test_each_argument_of_one_tape_has_its_own_cosine(self):
        """The kernel keeps the cosines it has rounded, each under the size of its angle. One
        tape here takes the cosine of angles that share a numerator, a denominator or a size,
        twice each, and holds each to its own ends."""
        angles = [F(3, 7), F(3, 8), F(-3, 7), F(7, 3), F(4, 7), F(3, 7), F(-7, 3), F(37, 1), F(3, 71), F(1, 37), F(-3, 8), F(7, 3)]
        nodes, roots = [], []
        for x in angles + angles:
            e = cos_of(x)
            nodes += [["c", num(x)], ["cos", len(nodes)]]
            at = len(nodes) - 1
            for bound, sign in ((e.hi, 1), (e.lo, -1)):
                nodes += ([["c", num(-bound)], ["add", [at, len(nodes)]]] if sign == 1 else [["neg", at], ["c", num(bound)], ["add", [len(nodes), len(nodes) + 1]]])
                roots.append(len(nodes) - 1)
        tape = {"inputs": [], "nodes": nodes, "roots": roots}
        self.assertEqual(proved([tape])[0]["state"], "proved")
        inside = {**tape, "nodes": [*nodes, ["c", num(STEP)], ["add", [roots[5], len(nodes)]]], "roots": [len(nodes) + 1]}
        self.assertEqual(proved([inside])[0]["reason"], ABOVE, "a limit one step inside the third angle's cosine is not kept")


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class KernelEdges(unittest.TestCase):
    def reason(self, nodes: list[list]) -> tuple[str, str]:
        (found,) = proved([at_most(nodes, F(2))])
        return found["state"], found.get("reason", "")

    def test_an_angle_at_65536_has_a_cosine_and_one_past_it_has_none(self):
        self.assertEqual(self.reason([["c", "65536"], ["cos", 0]]), ("proved", ""))
        self.assertEqual(self.reason([["c", "-65536"], ["cos", 0]]), ("proved", ""))
        for x in (65536 + F(1, 2 ** 200), -65536 - F(1, 10 ** 9), F(10 ** 9), F(2 ** 3000)):
            self.assertEqual(self.reason([["c", num(x)], ["cos", 0]]), ("open", "leaf 0: node 1: cos of a value beyond 65536"), x)
        self.assertEqual(self.reason([*angle(F(65535), F(65537)), ["cos", 4]]), ("open", "leaf 0: node 5: cos of a value beyond 65536"))
        self.assertEqual(self.reason([*angle(F(65535), F(65536)), ["cos", 4]]), ("proved", ""))

    def test_a_cosine_too_near_zero_to_round_has_no_value(self):
        from petra.kernel.interval import _pi_at
        near = F(round(_pi_at(None, 2500).lo / 2 * 2 ** 2300), 2 ** 2300)
        state, reason = self.reason([["c", num(near)], ["cos", 0]])
        self.assertEqual((state, reason), ("open", "leaf 0: node 1: no enclosure separated the value from the rounding grid"))

    def test_the_cosine_of_a_node_with_no_value_has_none(self):
        self.assertEqual(self.reason([["c", "0"], ["c", "1"], ["div", 1, 0], ["cos", 2]])[1], "leaf 0: node 2: division by an interval that contains 0")

    def test_a_refutation_reads_a_cosine_at_its_point(self):
        """cos t <= 1/2 fails at t = 1, where the cosine is over 0.54, and no point shows it failing at t = 3/2."""
        nodes = [["s", 0], ["cos", 0], ["c", "-1/2"], ["add", [1, 2]]]
        tape = {"inputs": [{"label": "dsg:t", "lo": "0", "hi": "2"}], "nodes": nodes, "roots": [3]}
        cells = [{"subject": "s", "mechanism": "m", "entry": str(k), "state": "refuted", "tape": tape, "point": [at], "which": 0} for k, at in enumerate(("1", "3/2", "0"))]
        said = ask(old_path(cells, []))
        self.assertEqual([c["state"] for c in said["cells"]], ["refuted", "open", "refuted"])

    def test_a_proof_over_leaves_reads_each_end_once_and_is_charged_for_it(self):
        """cos t <= 1 over 64 leaves: 65 different ends, each rounded once and then looked up.
        The second proof of the same tape finds every end in the cache and costs less."""
        nodes = [["s", 0], ["cos", 0], ["c", "-1"], ["add", [1, 2]]]
        tape = {"inputs": [{"label": "dsg:t", "lo": "1", "hi": "65"}], "nodes": nodes, "roots": [3]}

        def halves(lo: int, hi: int):
            mid = (lo + hi) // 2
            return "leaf" if hi - lo == 1 else {"input": 0, "at": str(mid), "below": halves(lo, mid), "above": halves(mid, hi)}

        def cells(count: int) -> list[dict]:
            return [{"subject": "s", "mechanism": "m", "entry": str(k), "state": "proved", "tape": tape, "partition": halves(1, 65)} for k in range(count)]

        once, twice = ask(old_path(cells(1), [])), ask(old_path(cells(2), []))
        self.assertEqual([c["state"] for c in twice["cells"]], ["proved", "proved"])
        self.assertGreater(once["work"], 65 * 400_000, "65 ends, each over 400,000 units")
        self.assertLess(twice["work"] - once["work"], once["work"] / 5, "the second proof looks its ends up")


TEST = {"standard": "a deck made up for the tests", "clause": "1"}
TURNS = {
    "format": "petra-rules/0", "name": "test-turns", "about": "Made up for the tests. It is no standard.",
    "rows": [
        {"id": "test/sine", "anchor": TEST, "gives": {"name": "y", "dim": "dimensionless", "what": "the sine of an angle in radians"},
         "takes": [{"name": "x", "dim": "dimensionless", "what": "the angle", "range": ["0", "1.5"]}],
         "is": ["cos", ["sub", ["div", "pi", "2"], "x"]]}],
    "types": [{"type": "arm", "what": "an arm at an angle", "fields": [
        {"name": "angle", "dim": "dimensionless", "may_be": "negative", "what": "its angle in radians"},
        {"name": "tilt", "dim": "dimensionless", "what": "its tilt in degrees"},
        {"name": "reach", "dim": "length", "what": "its length"}]}],
    "grid": [{"type": "arm", "mechanism": f"arm.{name}", "what": name, "anchor": TEST} for name in ("cos", "sine", "tilt")],
    "rules": [
        {"id": "test/cos", "type": "arm", "mechanism": "arm.cos", "anchor": TEST, "says": "the cosine of the angle is at most 0.6", "le": [["cos", "angle"], "0.6"]},
        {"id": "test/sine", "type": "arm", "mechanism": "arm.sine", "anchor": TEST, "says": "the sine of the angle is at most 0.6",
         "le": [["row", "test/sine", {"x": "angle"}], "0.6"]},
        {"id": "test/tilt", "type": "arm", "mechanism": "arm.tilt", "anchor": TEST, "says": "the cosine of the tilt is at most a half",
         "le": [["cos", ["mul", "tilt", ["div", "pi", "180"]]], "1/2"]}],
}
ARM = """petra 0

arm a {
  angle ANGLE
  tilt TILT
  reach 1 m
}
"""
CARD = """petra 0

card "turns" {
  owner "t@example.org"
}
GIVEN"""


def arm(angle: str = "1", tilt: str = "61", rules: dict = TURNS) -> dict[str, str]:
    """The files of an arm against TURNS. An angle written `[lo, hi]` is a bound of the card."""
    given = f'\ngiven a.angle in {angle} signed "t@example.org" source "test"\n' if angle.startswith("[") else ""
    design = ARM.replace("ANGLE", "given a.angle" if given else angle).replace("TILT", tilt)
    return strips(CARD.replace("GIVEN", given), design, rules)


def grid_says(files: dict[str, str]) -> dict[str, str]:
    return {c["mechanism"]: c["state"] for c in json.loads(files["proofs"])["cells"]}


def kernel_says(files: dict[str, str]) -> dict[str, str]:
    said = ask(files)
    assert not said["findings"], said["findings"]
    return {c["mechanism"]: c["state"] for c in said["cells"]}


CASES = (("1", "61", "proved", "refuted", "proved"), ("0.5", "59", "refuted", "proved", "refuted"), ("-1", "90", "proved", "proved", "proved"),
         ("[0.93, 1]", "120", "proved", "refuted", "proved"), ("[0.9, 1]", "180", "refuted", "refuted", "proved"), ("[-0.5, 0.5]", "350", "refuted", "proved", "refuted"),
         ("[0.1, 0.6]", "360", "refuted", "proved", "refuted"), ("3", "540", "proved", "proved", "proved"))
"""An angle, a tilt, and what becomes of `cos angle <= 0.6`, `sin angle <= 0.6` and `cos tilt <= 1/2`."""


class Rules(unittest.TestCase):
    def test_a_rule_with_a_cosine_is_proved_or_refuted(self):
        for angle, tilt, *want in CASES:
            with self.subTest(angle=angle, tilt=tilt):
                said = grid_says(arm(angle, tilt))
                self.assertEqual([said["arm.cos"], said["arm.sine"], said["arm.tilt"]], want)

    def test_a_cosine_exactly_on_its_limit_leaves_the_cell_open(self):
        """cos 60 degrees is 1/2, and the tape's pi is an interval, so the enclosure reaches a
        step to each side of 1/2: the rule is neither proved nor refuted."""
        self.assertEqual(grid_says(arm(tilt="60"))["arm.tilt"], "open")
        self.assertEqual(grid_says(arm(tilt="300"))["arm.tilt"], "open")

    def test_an_angle_beyond_65536_leaves_the_cell_open(self):
        said = grid_says(arm(angle="70000", tilt="61"))
        self.assertEqual((said["arm.cos"], said["arm.tilt"]), ("open", "proved"))
        self.assertEqual(grid_says(arm(angle="65536"))["arm.cos"], "proved", "cos 65536 is under -0.3")
        self.assertEqual(grid_says(arm(angle="[65536, 65537]"))["arm.cos"], "open", "the rule holds at 65536, and past it the angle has no cosine")
        self.assertEqual(grid_says(arm(angle="[65000, 66000]"))["arm.cos"], "refuted", "a range that reaches past 65536 is still refuted by a point within it")

    def test_the_cosine_of_a_length_is_refused_when_the_deck_is_read(self):
        for change, why in ((["cos", "reach"], "cos of a length"), (["cos", ["mul", "reach", "angle"]], "cos of a length"),
                            (["cos", ["q", "1", "kN"]], "cos of a force")):
            body = json.loads(json.dumps(TURNS))
            body["rules"][0]["le"][0] = change
            with self.subTest(change=change), self.assertRaisesRegex(grid.DeckError, why):
                grid.read_deck(json.dumps(body))
        row = json.loads(json.dumps(TURNS["rows"][0]))
        row["takes"][0].update(dim="length", range=["1 mm", "2 mm"])
        self.assertIn("sub of dimensionless and length", deck.read(row).problems[0])
        row["is"] = ["cos", "x"]
        self.assertEqual(deck.read(row).problems, ("cos of a length, which must be a plain number",))

    def test_a_cosine_takes_one_argument(self):
        for written in (["cos"], ["cos", "angle", "angle"]):
            body = json.loads(json.dumps(TURNS))
            body["rules"][0]["le"][0] = written
            with self.assertRaisesRegex(grid.DeckError, "is not in the language"):
                grid.read_deck(json.dumps(body))

    def test_the_language_has_one_operator_for_angles(self):
        for name in ("sin", "tan", "acos", "asin", "atan", "cosd", "sec"):
            body = json.loads(json.dumps(TURNS))
            body["rules"][0]["le"][0] = [name, "angle"]
            with self.assertRaisesRegex(grid.DeckError, "is not in the language"):
                grid.read_deck(json.dumps(body))


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class KernelRules(unittest.TestCase):
    def test_the_kernel_settles_each_cell_as_the_grid_does(self):
        for angle, tilt, *want in CASES + (("1", "60", "proved", "refuted", "open"), ("70000", "61", "open", "open", "proved"), ("65536", "300", "proved", "refuted", "open")):
            with self.subTest(angle=angle, tilt=tilt):
                files = arm(angle, tilt)
                said = kernel_says(files)
                self.assertEqual(said, grid_says(files))
                self.assertEqual([said["arm.cos"], said["arm.sine"], said["arm.tilt"]], want)

    def test_the_kernel_says_why_a_cosine_has_no_value(self):
        """The grid leaves the cell open and gives no hint, so the kernel tries nothing. With a
        hint that the rule is proved on one leaf, it tries and says where the tape has no value."""
        files = arm(angle="70000")
        (found,) = [c for c in ask(files)["cells"] if c["mechanism"] == "arm.cos"]
        self.assertEqual((found["state"], found["reason"]), ("open", "proofs.json has no partition and no point for it"))
        hinted = changed(files, "proofs", lambda body: [c.update(state="proved", partition="leaf") for c in body["cells"] if c["mechanism"] == "arm.cos"])
        (found,) = [c for c in ask(hinted)["cells"] if c["mechanism"] == "arm.cos"]
        self.assertEqual(found["state"], "open")
        self.assertRegex(found["reason"], r"^leaf 0: node \d+: cos of a value beyond 65536$")

    def test_the_kernel_refuses_a_deck_that_takes_the_cosine_of_a_length(self):
        files = arm()
        for change in (["cos", "reach"], ["cos", ["mul", "reach", "angle"]], ["cos"], ["cos", "angle", "angle"], ["sin", "angle"]):
            rules = json.loads(files["rules"])
            rules["rules"][0]["le"][0] = change
            why = findings(ask({**files, "rules": json.dumps(rules)}))
            self.assertRegex(why, "the argument of cos must be a plain number" if len(change) == 2 and change[0] == "cos" else "is not in the language", change)

    def test_a_tape_of_a_file_takes_the_node_and_a_node_of_another_shape_is_refused(self):
        good = {"inputs": [], "nodes": [["c", "1"], ["cos", 0], ["c", "-1"], ["add", [1, 2]]], "roots": [3]}
        self.assertEqual(proved([good])[0]["state"], "proved")
        for node in (["cos"], ["cos", 0, 0], ["cos", "0"], ["cos", [0]], ["sin", 0]):
            bad = {**good, "nodes": [["c", "1"], node, ["c", "-1"], ["add", [1, 2]]]}
            cells = [{"subject": "s", "mechanism": "m", "entry": "e", "state": "proved", "tape": bad, "partition": "leaf"}]
            self.assertIn("node", findings(ask(old_path(cells, []))), node)


LUGS = {
    "format": "petra-rules/0", "name": "test-lugs", "about": "Made up for the tests. It is no standard, and its stress is no steel's.",
    "rows": [
        {"id": "test/planes", "anchor": TEST, "gives": {"name": "Av", "dim": "area", "what": "the area of two planes beyond a pinhole"},
         "takes": [{"name": "t", "dim": "length", "what": "the thickness", "range": ["1 mm", "100 mm"]},
                   {"name": "a", "dim": "length", "what": "the distance from the hole to the edge", "range": ["1 mm", "500 mm"]},
                   {"name": "d", "dim": "length", "what": "the pin's diameter", "range": ["1 mm", "500 mm"]},
                   {"name": "D", "dim": "length", "what": "the hole's diameter", "range": ["1 mm", "500 mm"]}],
         "is": ["mul", "2", "t", ["add", "a", ["mul", ["div", "d", "2"], ["sub", "1", ["cos", ["mul", "55", ["div", "pi", "180"], ["div", "d", "D"]]]]]]]}],
    "types": [{"type": "lug", "what": "a plate with a pinhole", "fields": [
        {"name": "t", "dim": "length", "what": "its thickness"}, {"name": "a", "dim": "length", "what": "the distance from its hole to its edge"},
        {"name": "d", "dim": "length", "what": "the diameter of its pin"}, {"name": "D", "dim": "length", "what": "the diameter of its hole"}],
        "loads": [{"name": "pull", "dim": "force", "least": "0 N", "what": "the pull of the pin"}],
        "needs": [{"le": ["d", "D"], "why": "the pin goes through the hole"}]}],
    "grid": [{"type": "lug", "mechanism": "lug.planes", "what": "shear on two planes beyond the hole", "anchor": TEST}],
    "rules": [{"id": "test/planes", "type": "lug", "mechanism": "lug.planes", "anchor": TEST, "says": "the pull is at most a made-up stress on the two planes",
               "le": [["load", "pull"], ["mul", ["q", "100", "MPa"], ["row", "test/planes", {"t": "t", "a": "a", "d": "d", "D": "D"}]]]}],
}
LUG = """petra 0

lug hook {
  t THICK
  a 20 mm
  d 20 mm
  D 21 mm
}
"""
LIFT = """petra 0

card "lugs" {
  owner "t@example.org"
}

load lift {
  on hook pull in [0 kN, 40 kN]
  signed "t@example.org" source "test"
}
"""


def lug(thick: str = "10 mm", card: str = LIFT) -> dict[str, str]:
    return strips(card, LUG.replace("THICK", thick), LUGS)


class TwoPlanes(unittest.TestCase):
    """A rule of the shape a lifting lug needs: the area of two planes is
    2 t (a + (d / 2) (1 - cos phi)) with phi = 55 (pi / 180) d / D, an angle in degrees
    that the rule turns to radians with the tape's pi. The deck is made up, and so is its
    stress of 100 MPa. A lug 10 mm thick with a = 20 mm, d = 20 mm and D = 21 mm has
    phi = 0.9142 and an area of 477.92 mm2, so it carries 47.79 kN."""

    def test_the_row_gives_the_area(self):
        row = deck.read(LUGS["rows"][0])
        self.assertEqual(row.problems, ())
        mm = F(1, 1000)
        box = {name: point(value * mm) for name, value in (("t", 10), ("a", 20), ("d", 20), ("D", 21))}
        area = enclose(row.cases[0].expr, box)
        low, high = reference(55 * (PI_LOW + PI_HIGH) / 2 / 180 * F(20, 21))
        self.assertTrue(area.lo < 2 * 10 * (20 + 10 * (1 - high)) * mm * mm and 2 * 10 * (20 + 10 * (1 - low)) * mm * mm < area.hi)
        self.assertAlmostEqual(float(area.lo) * 1e6, 477.918, places=3)
        self.assertLess(area.hi - area.lo, F(1, 10 ** 30))

    def test_the_deck_loads_and_one_lug_is_proved_and_a_thinner_one_refuted(self):
        self.assertEqual(grid_says(lug("10 mm")), {"lug.planes": "proved"})
        self.assertEqual(grid_says(lug("8 mm")), {"lug.planes": "refuted"}, "8 mm carries 38.2 kN, and the card pulls 40")
        self.assertEqual(grid_says(lug("10 mm", LIFT.replace("40 kN", "48 kN"))), {"lug.planes": "refuted"})
        self.assertEqual(grid_says(lug("10 mm", LIFT.replace("40 kN", "47.7 kN"))), {"lug.planes": "proved"})

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_proves_the_one_and_refutes_the_other(self):
        for thick, pull, want in (("10 mm", "40 kN", "proved"), ("8 mm", "40 kN", "refuted"), ("10 mm", "47.7 kN", "proved"), ("10 mm", "47.8 kN", "refuted")):
            files = lug(thick, LIFT.replace("40 kN", pull))
            said = ask(files)
            self.assertEqual(said["findings"], [])
            self.assertEqual([(c["mechanism"], c["state"]) for c in said["cells"]], [("lug.planes", want)], (thick, pull))
            self.assertEqual(said["verdict"], "PASS" if want == "proved" else "FAIL")
            self.assertEqual(grid_says(files), {"lug.planes": want})

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_tries_the_rule_only_with_a_hint_and_pays_for_two_cosines(self):
        """With no hint the cell is open. With the grid's it is proved on one leaf. The angle is
        a product by the tape's pi, an interval, so it has two ends, and each is rounded once:
        a little over a million units of the twenty billion a verdict has."""
        files = lug()
        self.assertEqual(kernel_says({k: v for k, v in files.items() if k != "proofs"}), {"lug.planes": "open"})
        self.assertTrue(1_000_000 < ask(files)["work"] < 3_000_000, ask(files)["work"])


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class KernelTime(unittest.TestCase):
    """What a cosine costs beside what it is charged (docs/format.md, "Work"). The heaviest
    inputs under 1 MB that spend the work on cosines are in tests/test_kernel_attacks3.py, `Worst`."""

    def test_a_cosine_that_no_enclosure_rounds_pays_for_all_four_and_is_within_its_time(self):
        """300 angles within 2^-2300 of a quarter turn, all different: each asks for the four
        enclosures, of 128, 224, 608 and 2,144 bits, pays for each before it asks, and has no
        value. They are charged 16.7 million units each, 5 billion together."""
        from petra.kernel.interval import _pi_at
        base = F(round(_pi_at(None, 2500).lo / 2 * 2 ** 2300), 2 ** 2300)
        nodes, roots = [], []
        for k in range(300):
            nodes += [["c", num(base + F(2 * k + 1, 2 ** 2310))], ["cos", len(nodes)], ["abs", len(nodes) + 1], ["neg", len(nodes) + 2]]
            roots.append(len(nodes) - 1)
        files = old_path([{"subject": "s", "mechanism": "m", "entry": "e", "state": "proved", "partition": "leaf",
                           "tape": {"inputs": [], "nodes": nodes, "roots": roots}}], [])
        self.assertLess(total(files), MB)
        said, seconds, peak = measured(files)
        (found,) = said["cells"]
        self.assertEqual((found["state"], found["reason"]), ("open", "leaf 0: node 1: no enclosure separated the value from the rounding grid"))
        self.assertTrue(300 * 15_000_000 < said["work"] < 300 * 18_000_000, said["work"])
        self.assertLess(seconds, 30, "it took 1.5 processor seconds")
        self.assertLess(peak, 512_000_000)

    def test_a_node_that_reads_a_cosine_with_no_value_costs_nothing_more(self):
        """An angle past 65,536 pays 3,000 units and no enclosure."""
        nodes = [["c", "70000"], ["cos", 0], ["abs", 1], ["neg", 2]]
        said = ask(old_path([{"subject": "s", "mechanism": "m", "entry": "e", "state": "proved", "partition": "leaf",
                              "tape": {"inputs": [], "nodes": nodes, "roots": [3]}}], []))
        self.assertLess(said["work"], 30_000)


if __name__ == "__main__":
    unittest.main()
