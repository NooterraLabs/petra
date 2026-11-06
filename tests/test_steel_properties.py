"""Property tests for the steel connections deck: docs/principles.md rule V3 ("adding material
never lowers capacity; scaling units changes nothing; mirroring a design changes nothing; a
larger load box never turns FAIL into PASS"), the structural test of §4 item 7.

Every property runs over designs the gate's generator draws (petra/models/steel/generate.py,
stream seed SEED), not hand-picked ones, and asserts the deck's behaviour: kernel verdicts,
the per-mode outcomes behind them (gate.deck_outcomes), and the utilisations and available
strengths calc.py encloses over each design's box.

  Monotonicity.test_adding_material_never_lowers_a_strength (V3, adding material): one
    change at a time, a plate or stiffener one stocked size thicker, an angle (a seat, for
    `seated`) with the same legs one size thicker, a fillet 1/16 in larger, and a tee,
    member, beam or support replaced by the next heavier W (or the WT cut from it) of the
    same nominal depth that is no smaller in any dimension the deck reads. No strength
    check's available strength falls (checks matched by mode and `what`). Detailing and
    ductility rules are left out; STRENGTH and RULES say which and why.
  LoadBox.test_a_wider_load_box_keeps_a_fail_a_fail and
  LoadBox.test_a_narrower_load_box_keeps_a_pass_a_pass (V3, larger load box): a FAIL's load
    upper end times 3/2 and times 4 stays FAIL; a PASS's box with its upper end lowered to
    the middle, or its lower end raised to the middle, stays PASS. Full kernel verdicts.
  LoadBox.test_a_wider_load_box_never_lowers_a_utilisation (V3, larger load box, at calc
    level): every check's utilisation over the wider box is at least the narrower box's.
  Units.test_lengths_and_loads_in_other_units_change_nothing (V3, scaling units): every
    length and load rewritten in mm and kN, in m and N, and in ft and lbf (as p/q where the
    decimal does not terminate), by petra/units.py's exact factors (1 inch = 25.4 mm, 1 kip =
    4.4482216152605 kN). The verdict, every mode's outcome and every check's utilisation,
    demand and available strength are identical, not merely close: the parser normalises
    every spelling to the same exact rationals. The steel grammar takes every length unit
    (m, mm, cm, km, inch, ft) and force unit (N, kN, MN, lbf, kip, kips) petra/units.py
    defines, bolt diameters included (19.05 mm is the 3/4 in bolt), so none is left out;
    the three pairs tested cover a smaller unit, the base units, and the other customary
    pair written with p/q numbers.
  Mirroring.test_a_design_written_another_way_is_checked_the_same (V3, mirroring): no
    geometric mirror is expressible in the steel grammar, because it has no handedness to
    flip. The symmetric kinds (double angle, end plate, shear tee, hanger) take one gauge
    across the web, so their mirror image is the same text; every other kind carries a
    downward reaction that fixes which edge is the tearout edge (the bolts push the plate
    down and the beam web up), so a vertical flip is a different design, not a symmetry,
    and nothing in the grammar names a left or right side. What the grammar does let a
    designer write two ways is tested instead: attribute lines in another order, keyword
    pairs within a line in another order, standard holes and other defaults stated
    explicitly, the connection and load case renamed, load entries in another order, and
    the declarations in another order. Verdicts, outcomes and utilisations must be
    identical. One ordering cannot be written: a bare count must end its line (`weld ...
    sides 2 size 0.25 inch` reads `size` as the unit of 2), so `sides` stays last.

What limits each sample: the stream draws the eleven kinds in turn, 8 of each (88 designs);
SAMPLE is the first PER_KIND = 3 of each kind (33), among them toleranced (+-1/16 in) and
free (drawn without the detailer's rules) designs, which test_the_sample_covers_every_kind
asserts are present. Monotonicity and the units, mirroring and calc-level load-box tests run
over SAMPLE. The kernel load-box tests take up to BOX_PER_KIND = 2 PASS and 2 FAIL designs
of each kind from the 88 (the stream aims three in four at PASS; at this seed 8 per kind
give every kind at least one FAIL, which test_every_kind_has_both_verdicts asserts), and change
one load line at a time (two lines only for a hanger with shear or a flange force with
panel shear). Thickening stops where the grammar and the shop deck stop: stocked plates,
angles and shapes in the shape table. A stiffened seat's seat plate is thickened like any
plate, though no check reads it (the deck puts it on no load path, as the Manual sizes it
by detailing), so that change can only show that nothing falls.
"""
import functools
import random
import re
import unittest
from collections import defaultdict
from fractions import Fraction

from petra.lang import parse_design
from petra.models.steel import calc, vocab
from petra.models.steel import gate as G
from petra.models.steel import generate as gen
from petra.models.steel.checks import GENERATORS
from petra.models.steel.domain import required
from petra.models.steel.lower import KIND_SPECS, tee_parent
from petra.pipeline import check_design
from petra.registry import build_registry
from petra.registry.steel import STOCK_PLATE
from petra.solvers import SolverSource
from petra.units import CUSTOMARY, UNITS
from petra.verdict import STATUS

REGISTRY = build_registry()
SEED = 19
STREAM_PER_KIND = 8
PER_KIND = 3
BOX_PER_KIND = 2
STREAM = list(gen.generate(STREAM_PER_KIND * len(gen.SAMPLERS), SEED, REGISTRY))
SAMPLE = [g for kind in gen.SAMPLERS for g in [s for s in STREAM if s.kind == kind][:PER_KIND]]

SHAPES = "aisc_shapes_v16"

# The strength checks monotonicity covers: every limit state vocab.STRENGTH lists, plus a seat
# stiffener's compression (its yielding check is a strength, and its width-to-thickness limit
# 0.56 sqrt(E / Fy) does not move with material), cope and extended-plate buckling, and a
# shaped bracket's free edge (an interaction whose available side is 1).
STRENGTH = frozenset({short for short, *_ in vocab.STRENGTH} | {"compression", "cope_buckling", "plate_buckling",
                                                                   "bracket_edge"})
# Left out, because more material can legitimately make them worse, or because they bound
# geometry and installation rather than carry load:
#   ductility, extended_ductility: a single plate must be thin enough to yield before its
#     bolts fracture (t <= d/2 + 1/16 in; t <= tmax) and its fillet at least 5/8 of its
#     thickness, so a thicker plate fails them by design;
#   fillet_size: Table J2.4's minimum fillet grows with the thinner part joined, a lapped
#     edge's maximum fillet is its thickness less 1/16 in, and a fillet must be four times
#     its size long, so a thicker part or a larger fillet can fail it;
#   clearance: room to tighten is measured past the part (gb - t past an angle's
#     outstanding leg, gauge/2 - tw/2 to a web), so a thicker part leaves less;
#   spacing_min, edge_min, spacing_max, edge_max, hole_use, joint_type: makeability rules
#     whose "available" is a geometric or installation limit, not a capacity (edge_max and
#     spacing_max even loosen with thickness, 12 t and 24 t, but they carry no load).
RULES = frozenset({short for short, *_ in vocab.MAKEABILITY} | {"ductility", "extended_ductility"})

ROUNDING = 1e-9
"""Relative slack on available strengths compared across two designs: calc encloses each
over its own box with outward-rounded square roots, so two exact strengths in order could
come out a rounding step apart. A formula error moves a strength by far more."""


# --- Reading a design ---------------------------------------------------------------------------

Checks = dict[tuple[str, str], list[calc.Value]]


@functools.cache
def checks_of(text: str, conn: str, case: str) -> Checks:
    """Every check the deck owes `conn` under `case`, by (mode, what), in the deck's order.
    Cached: callers only read it."""
    design = parse_design(text, "t.petra", REGISTRY)
    lowered = calc.connection(design, conn, REGISTRY)
    out: Checks = defaultdict(list)
    for mode in required(lowered, design):
        if mode in GENERATORS:
            for v in calc.values(lowered, design, REGISTRY, mode, case):
                out[(mode, v.what)].append(v)
    return dict(out)


@functools.cache
def verdict_of(text: str) -> tuple[str, dict[str, str]]:
    """The kernel's verdict and each mode's outcome ("pass", "fail" or "open")."""
    report = check_design(parse_design(text, "t.petra", REGISTRY), REGISTRY, (SolverSource(),))
    return STATUS[type(report.verdict)], G.deck_outcomes(report)[0]


def numbers(found: Checks) -> dict[tuple[str, str], list[tuple[float, float, float, bool]]]:
    """Each check's (utilisation, demand, available, excused), order-free within a key."""
    return {k: sorted((v.utilisation, v.demand, v.available, v.excused) for v in vs) for k, vs in found.items()}


def number(x: Fraction) -> str:
    """x >= 0 exactly as .petra reads numbers: a terminating decimal where there is one, p/q otherwise."""
    for places in range(40):
        if (x * 10**places).denominator == 1:
            whole, frac = divmod(int(x * 10**places), 10**places)
            return f"{whole}.{frac:0{places}d}" if places else str(whole)
    return f"{x.numerator}/{x.denominator}"


def splice(text: str, span: tuple[int, int], new: str) -> str:
    return text[:span[0]] + new + text[span[1]:]


# --- Adding material -------------------------------------------------------------------------------

STOCK = sorted(c.value.lo / CUSTOMARY["inch"][0] for name, c in REGISTRY.constants.items() if name.startswith(STOCK_PLATE))
ANGLE_SHAPES = sorted({n.split(".")[1] for n in REGISTRY.constants if n.startswith(f"{SHAPES}.L") and n.endswith(".t")})
W_SHAPES = sorted({n.split(".")[1] for n in REGISTRY.constants if n.startswith(f"{SHAPES}.W") and n.endswith(".d")})
W_PROPS = ("d", "tw", "tf", "bf", "kdes", "A")
"""Every dimension of a W shape (or of a WT's parent) the deck reads."""
WELD_STEP = Fraction(1, 16)


def dim(shape: str, prop: str) -> Fraction:
    return REGISTRY.constants[f"{SHAPES}.{shape}.{prop}"].value.lo


def thicker_plate(thickness: str) -> str | None:
    """The next plate thickness the shop deck stocks."""
    t = Fraction(thickness)
    return next((number(s) for s in STOCK if s > t), None)


def thicker_angle(shape: str) -> str | None:
    """The angle with the same legs and the next thickness the shape table has."""
    legs, t = (dim(shape, "d"), dim(shape, "b")), dim(shape, "t")
    same = sorted((dim(a, "t"), a) for a in ANGLE_SHAPES if (dim(a, "d"), dim(a, "b")) == legs and dim(a, "t") > t)
    return same[0][1] if same else None


def larger_fillet(size: str) -> str:
    return number(Fraction(size) + WELD_STEP)


def _weight(shape: str) -> Fraction:
    return Fraction(shape.split("x", 1)[1].replace("_", "."))


def heavier_w(shape: str) -> str | None:
    """The lightest heavier W of the same nominal depth that is no smaller in any dimension
    the deck reads (a heavier W is not always: W14x30's flange is thinner than W14x26's)."""
    series = shape.split("x", 1)[0]
    base = {p: dim(shape, p) for p in W_PROPS}
    for other in sorted((w for w in W_SHAPES if w.split("x", 1)[0] == series), key=_weight):
        if _weight(other) > _weight(shape) and all(dim(other, p) >= base[p] for p in W_PROPS):
            return other
    return None


def _designation(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else str(float(x)).replace(".", "_")


def heavier_tee(shape: str) -> str | None:
    """The WT cut from the next heavier parent (WT9x25 -> WT9x27_5, cut from W18x55)."""
    parent = heavier_w(tee_parent(shape))
    if parent is None:
        return None
    depth, weight = (Fraction(x.replace("_", ".")) / 2 for x in parent[1:].split("x", 1))
    tee = f"WT{_designation(depth)}x{_designation(weight)}"
    return tee if tee_parent(tee) == parent else None


THICKENINGS = (
    (re.compile(r"^  (?:plate|stiffener) \S+ thickness (?P<x>[0-9.]+) inch$", re.M), thicker_plate),
    (re.compile(r"^  (?:angle|angles) (?P<x>L\S+) grade", re.M), thicker_angle),
    (re.compile(r"^  (?:weld|support_weld) \S+ size (?P<x>[0-9.]+) inch", re.M), larger_fillet),
    (re.compile(r"^  tee (?P<x>WT\S+) grade", re.M), heavier_tee),
    (re.compile(r"^  (?:member|beam|support) (?P<x>W\S+) ", re.M), heavier_w),
)
"""Each line that adds material, and what its value becomes. A seated connection's
top_angle carries no load in the deck and is left alone."""


def thickenings(text: str) -> list[tuple[str, str]]:
    """(what changed, the design's text with that one change)."""
    out = []
    for pattern, grow in THICKENINGS:
        for m in pattern.finditer(text):
            bigger = grow(m["x"])
            if bigger is not None:
                out.append((f"{m.group(0).strip()} -> {bigger}", splice(text, m.span("x"), bigger)))
    return out


# --- Load boxes ------------------------------------------------------------------------------------

LOAD = re.compile(r"^  on \w+ (?P<field>\w+) in \[(?P<lo>[0-9.]+) kip, (?P<hi>[0-9.]+) kip\]", re.M)
WIDER = (Fraction(3, 2), Fraction(4))
"""Factors on a FAIL's load's upper end."""


def loads(text: str) -> list[re.Match]:
    return list(LOAD.finditer(text))


def with_box(text: str, entry: re.Match, lo: Fraction, hi: Fraction) -> str:
    return splice(splice(text, entry.span("hi"), number(hi)), entry.span("lo"), number(lo))


def narrower(lo: Fraction, hi: Fraction) -> tuple[tuple[str, Fraction, Fraction], ...]:
    """Two sub-boxes of [lo, hi]: the upper end lowered to the middle, the lower end raised to it."""
    middle = (lo + hi) / 2
    return (("upper end lowered", lo, middle), ("lower end raised", middle, hi))


# --- Units ------------------------------------------------------------------------------------------

MM_PER_INCH = Fraction("25.4")
KN_PER_KIP = Fraction("4.4482216152605")
LENGTH = re.compile(r"(?<![\w.])(?P<x>[0-9]+(?:\.[0-9]+)?) inch\b")
FORCE = re.compile(r"(?<![\w.])(?P<x>[0-9]+(?:\.[0-9]+)?) kip\b")
SPELLINGS = (("mm", "kN"), ("m", "N"), ("ft", "lbf"))


def factor(unit: str) -> Fraction:
    return (UNITS.get(unit) or CUSTOMARY[unit])[0]


def in_units(text: str, length: str, force: str) -> str:
    """Every length rewritten in `length` and every force in `force`, exactly."""
    per_inch, per_kip = factor("inch") / factor(length), factor("kip") / factor(force)
    text = LENGTH.sub(lambda m: f"{number(Fraction(m['x']) * per_inch)} {length}", text)
    return FORCE.sub(lambda m: f"{number(Fraction(m['x']) * per_kip)} {force}", text)


# --- The same design written another way ---------------------------------------------------------

def parts(text: str) -> tuple[str, str, list[str], list[str], str]:
    """(`petra 0`, the design block, the component block's lines, the load block's lines, the
    kind) of a generated design."""
    head, design, component, load = text.strip("\n").split("\n\n")
    return head, design, component.split("\n"), load.split("\n"), component.split(" ", 1)[0]


def join(head: str, design: str, component: list[str], load: list[str]) -> str:
    return "\n\n".join((head, design, "\n".join(component), "\n".join(load))) + "\n"


def with_attributes(text: str, attributes: list[str]) -> str | None:
    """The design with its component's attribute lines replaced; None if nothing changed."""
    head, design, comp, load, _ = parts(text)
    out = join(head, design, [comp[0], *attributes, comp[-1]], load)
    return None if out == text else out


def attributes_of(text: str) -> list[str]:
    return parts(text)[2][1:-1]


def attributes_reversed(text: str) -> str | None:
    return with_attributes(text, attributes_of(text)[::-1])


def attributes_shuffled(text: str) -> str | None:
    attrs = attributes_of(text)
    random.Random(text).shuffle(attrs)
    return with_attributes(text, attrs)


PAIRED = ("bolts", "weld", "support_weld", "cope", "angle", "angles", "top_angle")
"""Lines that read `<key> <first> <keyword> <value> ...`, the keyword pairs in any order,
except that a bare count (`sides 2`) must end its line: the parser reads a word right after
a number as the number's unit."""


def _pairs_reversed(line: str) -> str:
    words = line.split()
    if words[0] not in PAIRED or "[" in line:
        return line
    pairs, rest = [], words[2:]
    while rest:
        size = 3 if len(rest) > 2 and rest[2] == "inch" else 2
        pairs.append(rest[:size])
        rest = rest[size:]
    counts = [p for p in pairs if len(p) == 2 and p[1].isdigit()]
    others = [p for p in pairs if p not in counts]
    return "  " + " ".join(words[:2] + [w for pair in [*reversed(others), *counts] for w in pair])


def keywords_reversed(text: str) -> str | None:
    return with_attributes(text, [_pairs_reversed(x) for x in attributes_of(text)])


def holes_stated(text: str) -> str | None:
    """Every ply's hole type stated, standard where the design left it unnamed, the plies in
    reverse order. None for a kind or design without bolts."""
    kind = parts(text)[4]
    attrs = attributes_of(text)
    if not KIND_SPECS[kind].plies or not any(x.split()[0] == "bolts" for x in attrs):
        return None
    named = {}
    for x in attrs:
        words = x.split()
        if words[0] == "holes":
            named.update(zip(words[1::2], words[2::2]))
    line = "  holes " + " ".join(f"{p} {named.get(p, 'std')}" for p in reversed(KIND_SPECS[kind].plies))
    return with_attributes(text, [x for x in attrs if x.split()[0] != "holes"] + [line])


DEFAULT_LINES = {"form": "conventional", "columns": "1", "deformation": "considered", "weathering": "no",
                 "pair": "single", "moment_at_force": "below_yield"}
"""What the deck takes for an optional word line a design leaves out."""
DEFAULT_KEYWORDS = {"bolts": (("joint", "snug"), ("fillers", "none")), "weld": (("sides", "2"),),
                    "support_weld": (("sides", "2"),)}
"""What the deck takes for a keyword a line leaves out (a count last, as PAIRED says)."""


def defaults_stated(text: str) -> str | None:
    """Every default the kind allows written out: the optional lines and the keywords."""
    kind = parts(text)[4]
    attrs = attributes_of(text)
    given = {x.split()[0] for x in attrs}
    out = []
    for x in attrs:
        words = x.split()
        missing = [f"{k} {v}" for k, v in DEFAULT_KEYWORDS.get(words[0], ()) if k not in words]
        out.append(" ".join([x, *missing]))
    out += [f"  {k} {v}" for k, v in DEFAULT_LINES.items() if k in KIND_SPECS[kind].optional and k not in given]
    return with_attributes(text, out)


def renamed(text: str, conn: str, case: str) -> str:
    text = re.sub(r"^(\w+) c1 \{", rf"\1 {conn} {{", text, flags=re.M)
    text = re.sub(r"^  on c1 ", f"  on {conn} ", text, flags=re.M)
    return re.sub(r"^load gate \{", f"load {case} {{", text, flags=re.M)


def loads_reversed(text: str) -> str | None:
    head, design, comp, load, _ = parts(text)
    entries = [x for x in load if x.startswith("  on ")]
    if len(entries) < 2:
        return None
    rest = [x for x in load if not x.startswith("  on ")]
    return join(head, design, comp, [rest[0], *reversed(entries), *rest[1:]])


def declarations_reordered(text: str) -> str:
    """The load case first, then the connection, then the design block."""
    head, design, comp, load, _ = parts(text)
    return "\n\n".join((head, "\n".join(load), "\n".join(comp), design)) + "\n"


CONN, CASE = "beam_end", "service"


def rewritings(text: str) -> list[tuple[str, str, str, str]]:
    """(what, text, connection name, load case name) for each way of writing the same design
    that applies to it."""
    out = [("connection and load case renamed", renamed(text, CONN, CASE), CONN, CASE),
           ("declarations reordered", declarations_reordered(text), "c1", "gate")]
    for what, rewrite in (("attribute lines reversed", attributes_reversed), ("attribute lines shuffled", attributes_shuffled),
                          ("keyword pairs reversed", keywords_reversed), ("standard holes stated", holes_stated),
                          ("defaults stated", defaults_stated), ("load entries reversed", loads_reversed)):
        found = rewrite(text)
        if found is not None:
            out.append((what, found, "c1", "gate"))
    return out


# --- The properties ----------------------------------------------------------------------------------

class Sample(unittest.TestCase):
    def test_the_sample_covers_every_kind(self):
        self.assertEqual([g.kind for g in SAMPLE], [k for k in gen.SAMPLERS for _ in range(PER_KIND)])
        self.assertTrue(any(g.toleranced for g in SAMPLE) and any(g.free for g in SAMPLE))

    def test_every_mode_is_a_strength_or_a_rule(self):
        # a new mode must be placed on one side before monotonicity can leave it out
        self.assertEqual(STRENGTH | RULES, set(GENERATORS))
        self.assertFalse(STRENGTH & RULES)

    def test_the_unit_factors_are_lolas(self):
        self.assertEqual(factor("inch") / factor("mm"), MM_PER_INCH)
        self.assertEqual(factor("kip") / factor("kN"), KN_PER_KIP)


class Monotonicity(unittest.TestCase):
    def test_every_kind_has_material_to_add(self):
        self.assertEqual({g.kind for g in SAMPLE if thickenings(g.text)}, set(gen.SAMPLERS))

    def test_adding_material_never_lowers_a_strength(self):
        for g in SAMPLE:
            before = checks_of(g.text, "c1", "gate")
            keys = sorted(k for k in before if k[0] in STRENGTH)
            for what, text in thickenings(g.text):
                after = checks_of(text, "c1", "gate")
                with self.subTest(g.name, kind=g.kind, change=what):
                    self.assertEqual(keys, sorted(k for k in after if k[0] in STRENGTH))
                    for key in keys:
                        self.assertEqual(len(before[key]), len(after[key]), key)
                        for old, new in zip(before[key], after[key]):
                            # an excused check's formula is outside its range (J10.4 past its
                            # slenderness limit, the other branch of a cope's or a bracket's
                            # lambda): there is no strength to compare
                            if old.excused or new.excused:
                                continue
                            self.assertGreaterEqual(new.available, old.available * (1 - ROUNDING),
                                                    f"{key}: {old.available} -> {new.available} {old.unit}")


class LoadBox(unittest.TestCase):
    def picks(self, status: str) -> list[gen.Generated]:
        return [g for kind in gen.SAMPLERS
                for g in [s for s in STREAM if s.kind == kind and s.expected == status][:BOX_PER_KIND]]

    def test_every_kind_has_both_verdicts(self):
        for status in ("PASS", "FAIL"):
            self.assertEqual({g.kind for g in self.picks(status)}, set(gen.SAMPLERS), status)

    def test_a_wider_load_box_keeps_a_fail_a_fail(self):
        for g in self.picks("FAIL"):
            self.assertEqual(verdict_of(g.text)[0], "FAIL", g.name)
            for entry in loads(g.text):
                lo, hi = Fraction(entry["lo"]), Fraction(entry["hi"])
                for times in WIDER:
                    with self.subTest(g.name, kind=g.kind, load=entry["field"], times=str(times)):
                        self.assertEqual(verdict_of(with_box(g.text, entry, lo, hi * times))[0], "FAIL")

    def test_a_narrower_load_box_keeps_a_pass_a_pass(self):
        for g in self.picks("PASS"):
            self.assertEqual(verdict_of(g.text)[0], "PASS", g.name)
            for entry in loads(g.text):
                for what, lo, hi in narrower(Fraction(entry["lo"]), Fraction(entry["hi"])):
                    with self.subTest(g.name, kind=g.kind, load=entry["field"], box=what):
                        self.assertEqual(verdict_of(with_box(g.text, entry, lo, hi))[0], "PASS")

    def test_a_wider_load_box_never_lowers_a_utilisation(self):
        for g in SAMPLE:
            before = checks_of(g.text, "c1", "gate")
            for entry in loads(g.text):
                after = checks_of(with_box(g.text, entry, Fraction(entry["lo"]), Fraction(entry["hi"]) * WIDER[0]), "c1", "gate")
                with self.subTest(g.name, kind=g.kind, load=entry["field"]):
                    self.assertEqual(sorted(before), sorted(after))
                    for key in before:
                        self.assertEqual(len(before[key]), len(after[key]), key)
                        for old, new in zip(before[key], after[key]):
                            self.assertGreaterEqual(new.utilisation, old.utilisation, key)


class Units(unittest.TestCase):
    def test_lengths_and_loads_in_other_units_change_nothing(self):
        for g in SAMPLE:
            verdict, expected = verdict_of(g.text), numbers(checks_of(g.text, "c1", "gate"))
            for length, force in SPELLINGS:
                text = in_units(g.text, length, force)
                with self.subTest(g.name, kind=g.kind, units=f"{length}, {force}"):
                    self.assertNotRegex(text, r"\b(inch|kip)\b")
                    self.assertEqual(verdict_of(text), verdict)
                    self.assertEqual(numbers(checks_of(text, "c1", "gate")), expected)


class Mirroring(unittest.TestCase):
    def test_a_design_written_another_way_is_checked_the_same(self):
        for g in SAMPLE:
            verdict, expected = verdict_of(g.text), numbers(checks_of(g.text, "c1", "gate"))
            for what, text, conn, case in rewritings(g.text):
                with self.subTest(g.name, kind=g.kind, rewriting=what):
                    self.assertNotEqual(text, g.text)
                    self.assertEqual(verdict_of(text), verdict)
                    self.assertEqual(numbers(checks_of(text, conn, case)), expected)


if __name__ == "__main__":
    unittest.main()
