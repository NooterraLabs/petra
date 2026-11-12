"""The seventh hostile review of petra-verify (kernel/), petra/grid.py and petra/rule.py: six ways
`petra check` gave PASS for a design that a rule refutes. One test per finding.

Every finding had one shape. The search for a refuting point missed it, so the cell stayed
open, and a waiver rested the open cell. So the verdict was PASS for a design that fails the
rule, where docs/deck.md, "What a waiver rests", said "a design that fails it fails". They
differ in why the refutation was not found or could not be shown.

  1  The shipped AISC deck. A lap whose card gives ranges to seven inputs of the block shear
     rule of the tab. The search tried corners only up to six ranged inputs, and then only the
     middle. The worst corner fails block shear at a ratio of 1.26, and the middle holds. The
     card waives lap.block_shear, and the same card with six ranges, a smaller box, was FAIL.
  2  A refutation inside the box, away from every corner and the middle: a rotor kept a tenth
     of its natural frequency, 5000 rpm, away from it, with a speed range of 3000 to 9000 rpm.
  3  A rule with `where`. The card's range runs past the `where`, so the `where` is not proved
     over the box and the cell was open, though at a point inside the `where` the inequality
     fails. The kernel took no point for such a cell.
  4  `lt` at equality where a side has a root: sqrt(3^2 + 4^2) < 5 is false, and an enclosure
     of the root never decides it.
  5  `may_be: "zero"`. A rule divides a pull by a count of bolts that may be zero, and a joint
     with no bolts had no value.
  6  An optional field left `unstated`, inside `min`: current at most the lesser of the maker's
     limit and the rating, with the rating under the current. The rule fails whatever value
     the limit takes.

Since the review a waiver rests only a cell that no inequality could answer: no rule reads it,
a load is missing, a table has no value there, or a key is unstated (docs/deck.md, "What a
waiver rests"). A cell whose rule is left undecided stays open, waiver or not. So each of the
six is UNKNOWN or FAIL, and never PASS. And a deck whose rule divides by a field that may be
zero, as in 5, is refused when it is read (docs/deck.md, "A quantity at or under zero").

The search then learned to find 1 and 2. Past six ranged inputs it tries the corner the root
climbs to from the middle, and in the search for a proof it tries the middle of each box it
does not prove. Both are FAIL. Then 3: where the `where` is not proved, both readers try a
point on a tape whose root is the rule's inside the `where` and -1 outside it, and a point
inside where the rule fails refutes it. The kernel tries no partition of that tape. Then 4:
both kernels take the root of a point that is the square of a fraction to be that fraction,
not two grid points around it, so the diagonal of 3 mm and 4 mm is 5 mm, and `lt` under 5 mm
is refuted. A root that is no fraction is rounded as before.
"""
import json
import unittest
from unittest import mock

from petra import grid, verify
from petra.registry import build_registry
from petra.repair import check_text
from tests.test_deck_features import HEAD, asks, design, given, kind, load, made_up, no_deck, parsed, part, rule, size
from tests.test_kernel_grid import ask

NOT_PASS = ("UNKNOWN", "FAIL")


def waive(mechanism: str, on: str) -> str:
    return f'\nwaive {mechanism} on {on} by "t@example.org" reason "test"\n'


def checked(card: str, text: str, deck: dict | None = None):
    """What `petra check` gives (repair.check_text, as cmd_check and the MCP tool call it), with
    the shipped decks or with a made-up one in their place. With a kernel built, the kernel's
    cells are compared with the grid's, and a difference raises."""
    def run():
        return check_text(card, text, "made-up.petra", build_registry(), (), card_path="made-up.card")
    if deck is None:
        return run()
    read = grid.read_deck(json.dumps(deck))
    with mock.patch.object(grid, "decks", lambda: (read,)):
        return run()


def states(result, mechanism: str) -> list[tuple[str, str]]:
    return [(c.entry, c.state) for c in result.report.cells if c.mechanism == mechanism]


# --- 1. seven ranged inputs on the shipped deck ------------------------------------------------------------

S = 'signed "s.engineer@example.org" source "test"'
LAP = """petra 0

plate tab {
  thickness given tab.thickness
  width 6 inch
  Fy given tab.Fy
  Fu given tab.Fu
}

plate strap {
  thickness 0.375 inch
  width 6 inch
  Fy given strap.Fy
  Fu given strap.Fu
}

lap splice {
  fastener "Group 120"
  threads included
  diameter 0.75 inch
  holes standard
  count 3
  pitch given splice.pitch
  end given splice.end
  side given splice.side
  surface protected
  joins tab strap
}
"""
RANGES = {"tab.thickness": ("0.25 inch", "0.375 inch"), "tab.Fy": ("36 ksi", "50 ksi"), "tab.Fu": ("58 ksi", "65 ksi"),
          "strap.Fy": ("36 ksi", "36 ksi"), "strap.Fu": ("58 ksi", "58 ksi"),
          "splice.pitch": ("2.25 inch", "3 inch"), "splice.end": ("1 inch", "1.5 inch"), "splice.side": ("1 inch", "3 inch")}


def lap_card(ranges: dict) -> str:
    out = 'petra 0\n\ncard "lap-ranged" {\n  owner "s.engineer@example.org"\n}\n\n'
    out += "".join(f"given {name} in [{lo}, {hi}] {S}\n" for name, (lo, hi) in ranges.items())
    out += f"\nload gravity {{\n  on splice pull in [0 kip, 35 kip]\n  {S}\n}}\n\n"
    for m in ("lap.tightening", "lap.hole_use", "lap.max_edge_distance", "lap.ply_flexure", "lap.block_shear"):
        out += f'waive {m} on splice by "s.engineer@example.org" reason "test"\n'
    return out


class SevenRanges(unittest.TestCase):
    def test_a_lap_whose_worst_corner_fails_block_shear_does_not_pass_under_a_waiver_with_seven_ranged_inputs(self):
        six = checked(lap_card(dict(RANGES, **{"splice.side": ("1 inch", "1 inch")})), LAP)
        self.assertEqual(six.status, "FAIL")
        self.assertIn(("lap-block-shear-a/gravity", "refuted"), states(six, "lap.block_shear"))
        seven = checked(lap_card(RANGES), LAP)                             # a wider box: every design of `six` is in it
        self.assertEqual(seven.status, "FAIL", states(seven, "lap.block_shear"))
        refuted = next(c for c in seven.report.cells if c.entry == "lap-block-shear-a/gravity")
        self.assertEqual(refuted.state, "refuted")
        point = refuted.proof["point"]
        self.assertEqual(len([label for label in point if label.startswith("in:")]), 7, "the pull and the six givens of the tab and the splice")
        self.assertEqual((point["in:lap-ranged.splice.side"], point["in:lap-ranged.tab.thickness"]), ("127/5000", "127/20000"),
                         "the corner the root climbs to: the least side distance and the thinnest tab")


# --- 2. a refutation inside the box ------------------------------------------------------------------------

ROTOR = made_up(
    [kind("rotor", size("speed", "dimensionless/time"), size("natural", "dimensionless/time"), size("mass", "mass"))],
    [asks("rotor.resonance", "rotor"), asks("rotor.mass", "rotor")],
    [rule("clear", "rotor", "rotor.resonance", le=[["mul", "1/10", "natural"], ["abs", ["sub", "speed", "natural"]]]),
     rule("light", "rotor", "rotor.mass", le=["mass", ["q", "1", "kg"]])])
ROTOR_TEXT = design(part("rotor", "r", speed="given r.speed", natural="5000 rpm", mass="200 g"))


class InteriorRefutation(unittest.TestCase):
    def test_a_speed_range_through_the_natural_frequency_does_not_pass_under_a_waiver(self):
        card = HEAD + waive("rotor.resonance", "r")
        self.assertEqual(checked(card + given("r.speed", "5000 rpm"), ROTOR_TEXT, ROTOR).status, "FAIL")
        ranged = checked(card + given("r.speed", "3000 rpm", "9000 rpm"), ROTOR_TEXT, ROTOR)
        self.assertEqual(ranged.status, "FAIL")
        refuted = next(c for c in ranged.report.cells if c.mechanism == "rotor.resonance")
        # 5250 rpm: the middle of the upper half of the range's lower half, a box the search could not prove.
        self.assertEqual((refuted.state, refuted.proof["point"]["in:made-up.r.speed"]), ("refuted", "175/2"))


# --- 3. a refutation inside a `where` that the card's range runs past --------------------------------------

TAB = made_up(
    [kind("tab", size("x"), size("y"))],
    [asks("tab.fit", "tab"), asks("tab.size", "tab")],
    [rule("fit", "tab", "tab.fit", le=["y", "x"], where=[{"le": ["x", ["q", "10", "mm"]], "why": "x is at most 10 mm"}]),
     rule("size", "tab", "tab.size", le=["y", ["q", "100", "mm"]])])
TAB_TEXT = design(part("tab", "t", x="given t.x", y="8 mm"))


PAST = made_up(
    [kind("tab", size("x"), size("y"))],
    [asks("tab.fit", "tab"), asks("tab.size", "tab")],
    [rule("fit", "tab", "tab.fit", le=["x", ["q", "9", "mm"]], where=[{"le": ["x", ["q", "8", "mm"]], "why": "x is at most 8 mm"}]),
     rule("size", "tab", "tab.size", le=["y", ["q", "100", "mm"]])])
"""A rule that holds all through its `where`, x up to 8 mm, and fails past it, from 9 mm."""


class RefutedInsideWhere(unittest.TestCase):
    def test_a_point_inside_the_where_that_fails_the_rule_is_not_rested_by_a_waiver(self):
        self.assertEqual(checked(HEAD + given("t.x", "5 mm") + waive("tab.fit", "t"), TAB_TEXT, TAB).status, "FAIL")
        ranged = checked(HEAD + given("t.x", "5 mm", "20 mm") + waive("tab.fit", "t"), TAB_TEXT, TAB)
        self.assertEqual(ranged.status, "FAIL")
        refuted = next(c for c in ranged.report.cells if c.mechanism == "tab.fit")
        # 5 mm, inside the `where`, and under the 8 mm of y. There is no `/where` cell: the range is not proved.
        self.assertEqual((refuted.entry, refuted.state, refuted.proof["point"]["in:made-up.t.x"]), ("fit", "refuted", "1/200"))

    def test_a_rule_that_fails_only_past_its_where_is_not_refuted(self):
        ranged = checked(HEAD + given("t.x", "5 mm", "20 mm"), TAB_TEXT, PAST)
        self.assertEqual((ranged.status, states(ranged, "tab.fit")), ("UNKNOWN", [("fit", "open")]))

    @unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
    def test_the_kernel_takes_neither_a_point_past_the_where_nor_a_partition_for_the_rule_inside_it(self):
        """Hand-made hints for the rule of PAST. A point at 15 mm, past the `where`, where the
        rule fails: the kernel tries it on the tape that is -1 outside the `where`, and it
        refutes nothing. A partition at 8.5 mm that proves that tape: the kernel tries no
        partition of it, since the rule says nothing of a part past its `where`. Either way
        the cell stays open, as the grid has it. A point at 5 mm inside the `where` of TAB, where
        that rule fails, refutes it."""
        def cell(rules: dict, hint: dict) -> dict:
            deck, read = parsed(rules, TAB_TEXT, HEAD + given("t.x", "5 mm", "20 mm"))
            said = ask({**grid.bundle(read, deck), "proofs": json.dumps({"format": "petra-proofs/0", "cells": [hint]})})
            self.assertEqual(said["findings"], [])
            (found,) = [c for c in said["cells"] if c["mechanism"] == "tab.fit"]
            return found

        hint = {"subject": "t", "mechanism": "tab.fit", "entry": "fit"}
        at = {"in:made-up.t.x": "3/200", "dsg:made-up.t.y": "1/125"}
        self.assertEqual(cell(PAST, {**hint, "state": "refuted", "point": at})["state"], "open")
        split = {"input": "in:made-up.t.x", "at": "17/2000", "below": "leaf", "above": "leaf"}
        self.assertEqual(cell(PAST, {**hint, "state": "proved", "partition": split})["state"], "open")
        self.assertEqual(cell(TAB, {**hint, "state": "refuted", "point": {**at, "in:made-up.t.x": "1/200"}})["state"], "refuted")


# --- 4. `lt` at equality with a root -----------------------------------------------------------------------

DIAGONAL = made_up(
    [kind("box", size("a"), size("b"), size("c"))],
    [asks("box.fit", "box"), asks("box.size", "box")],
    [rule("fit", "box", "box.fit", lt=[["sqrt", ["add", ["mul", "a", "a"], ["mul", "b", "b"]]], "c"]),
     rule("size", "box", "box.size", le=["c", ["q", "1", "m"]])])


class StrictAtEquality(unittest.TestCase):
    def test_a_diagonal_equal_to_its_limit_is_not_under_it_and_does_not_pass_under_a_waiver(self):
        card = HEAD + waive("box.fit", "x")
        self.assertEqual(checked(card, design(part("box", "x", a="3 mm", b="4 mm", c="4.9 mm")), DIAGONAL).status, "FAIL")
        equal = checked(card, design(part("box", "x", a="3 mm", b="4 mm", c="5 mm")), DIAGONAL)
        self.assertEqual(equal.status, "FAIL")
        # The root of 3^2 + 4^2 mm^2, a point that is the square of a fraction, is 5 mm exactly.
        self.assertEqual(states(equal, "box.fit"), [("fit", "refuted")])

    def test_a_diagonal_whose_square_is_no_square_of_a_fraction_is_rounded_so_a_limit_within_a_step_of_it_is_open(self):
        """sqrt(1^2 + 1^2) mm is no fraction, so its root is rounded outward to the grid of
        2^-96 m. A limit under it by less than a step lies inside that enclosure and is open,
        waiver or not. One under it by more than a step is refuted."""
        card = HEAD + waive("box.fit", "x")

        def at(c: str):
            return checked(card, design(part("box", "x", a="1 mm", b="1 mm", c=c)), DIAGONAL)
        inside = at("1.414213562373095048801688724 mm")
        self.assertEqual((inside.status, states(inside, "box.fit")), ("UNKNOWN", [("fit", "open")]))
        self.assertEqual(states(at("1.4142135623730950488016887 mm"), "box.fit"), [("fit", "refuted")])


# --- 5. a divisor that may be zero -------------------------------------------------------------------------

JOINT = made_up(
    [kind("joint", size("bolts", "dimensionless", whole=True, may_be="zero"), size("capacity", "force"), size("mass", "mass"),
          loads=[{"name": "pull", "dim": "force", "least": "0 N", "what": "the pull"}])],
    [asks("joint.share", "joint"), asks("joint.mass", "joint")],
    [rule("share", "joint", "joint.share", le=[["div", ["load", "pull"], "bolts"], "capacity"]),
     rule("light", "joint", "joint.mass", le=["mass", ["q", "1", "kg"]])])


def joint(bolts: str) -> str:
    return design(part("joint", "j", bolts=bolts, capacity="10 kN", mass="100 g"))


class ZeroDivisor(unittest.TestCase):
    def test_a_rule_that_divides_by_a_count_that_may_be_zero_is_refused_when_the_deck_is_read(self):
        """Both readers refuse the deck, so no joint is checked by the rule. The same rule
        that divides by one more than the count is read, and a joint with no bolts fails it."""
        mine, its = no_deck(self, JOINT)
        self.assertIn("rule made-up/share: it divides by bolts, which its `may_be` lets be zero", mine)
        self.assertIn("it divides by bolts", its)
        more = json.loads(json.dumps(JOINT))
        more["rules"][0]["le"][0][2] = ["add", "bolts", "1"]
        card = HEAD + load("service", "j pull in [50 kN, 50 kN]") + waive("joint.share", "j")
        for bolts in ("0", "3"):
            self.assertEqual(checked(card, joint(bolts), more).status, "FAIL")


# --- 6. an unstated field that no value could save ---------------------------------------------------------

WIRE = made_up(
    [kind("wire", size("current", "current"), size("limit", "current", optional=True), size("rating", "current"), size("mass", "mass"))],
    [asks("wire.heat", "wire"), asks("wire.mass", "wire")],
    [rule("heat", "wire", "wire.heat", le=["current", ["min", "limit", "rating"]]),
     rule("light", "wire", "wire.mass", le=["mass", ["q", "1", "kg"]])])


def wire(limit: str) -> str:
    return design(part("wire", "w", current="10 A", limit=limit, rating="5 A", mass="100 g"))


class UnstatedEveryValueFails(unittest.TestCase):
    def test_leaving_out_a_field_whose_every_value_fails_the_rule_does_not_pass_under_a_waiver(self):
        """A known miss: the rule fails whatever the limit is, and the cell is open and not
        refuted. A waiver does not rest it, since the field left out is a quantity, so the
        design is UNKNOWN (docs/format.md, where `unstated` is described)."""
        card = HEAD + waive("wire.heat", "w")
        for limit in ("100 A", "1000000 A"):
            self.assertEqual(checked(card, wire(limit), WIRE).status, "FAIL")
        self.assertEqual(checked(card, wire("unstated"), WIRE).status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
