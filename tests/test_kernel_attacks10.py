"""The tenth hostile review of petra-verify (kernel/) and petra/grid.py. One test per finding.

  A   The floors of deck.json decided verdicts for a design with parts: a number of a field
      that may be negative was held to them, and so was a completion. A reader is told to
      check `cells_from`, `hashes.rules` and `hashes.card`, and none covers deck.json. With
      the floor of a temperature left out of it, a rod fitted at -300 degC and a strut rested
      on a completion at -300 degC were PASS. With `--rules` the kernel now holds the floors
      of petra/decks/core.json itself, and a deck.json that gives others is a finding (type
      rule 8).
  B   The shipped lap compared no field with another, and passed under its waivers with a side
      distance of 1 inch on plates 1 3/4 inch wide, where one line of holes leaves at most
      7/8 inch and J3.4 refutes every such lap. The lap now needs twice its side to be at
      most the width of each plate.
  C   petra/grid.py held only the numbers of a need to 65,536 bits, where the kernel holds
      every value of a tape and every sum and product so far. The 64th power of a product of
      four ratios of 98 digits was PASS in Python and UNKNOWN in the kernel, and petra check
      exited 4. Python's tapes now have the kernel's bound.
  D   A completion was printed as a value "in SI units". Petra's SI takes a temperature in
      degC, and SI's unit of temperature is the kelvin: a steam main rested on a completion of
      295 read as 21.85 degC, where the rule asks 100 degC. Each value of a load a completion
      gives is now printed with its unit, by both readers, in the JSON and in the text.
  M3  Under a card with no load case, the reason of a load that a completion puts on a part
      and that no rule reads said `that case  puts on a`. It says `that the card puts on a`.
"""
import json
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import petra.lang
from petra import grid, verify
from petra.kernel import Interval
from petra.registry import build_registry
from tests.test_deck_features import HEAD, KERNEL, asks, cells, design, given, ill_formed, key, kind, load, made_up, parsed, part, rule, size
from tests.test_kernel_attacks3 import cell, with_card
from tests.test_kernel_attacks9 import STRUT_CARD, STRUT_TEXT, strut, waive
from tests.test_kernel_grid import ask, findings


# --- A. the floors of deck.json -------------------------------------------------------------------------------

ROD = kind("rod", size("area", "area"), size("Fy", "stress", signed=True), size("fit", "temperature", may_be="negative"),
           loads=[{"name": "pull", "dim": "force", "what": "the pull on the rod", "least": "0 kN"},
                  {"name": "t", "dim": "temperature", "may_be": "negative", "what": "the rod's temperature in the case"}])
RODS = made_up([ROD], [asks("rod.stress", "rod")],
               [rule("stress", "rod", "rod.stress",
                     le=[["add", ["div", ["load", "pull"], "area"], ["mul", ["div", ["q", "2.4", "MPa"], ["q", "1", "degC"]], ["sub", "fit", ["load", "t"]]]], "Fy"])])
"""A tie rod fitted at `fit` and held at t: 1,000 MPa of pull on 100 mm2, less 2.4 MPa for each degC that t is over `fit`."""
ROD_TEXT = design(part("rod", "r", area="100 mm2", Fy="given r.Fy", fit="-300 degC"))
ROD_CARD = HEAD + given("r.Fy", "250 MPa") + load("service", "r pull in [100 kN, 100 kN]", "r t in [20 degC, 40 degC]")
"""At -300 degC the rule holds from 20 to 40 degC: 184 to 232 MPa. At any `fit` a rod may have it fails: 296 MPa or more."""


def floors(files: dict[str, str], change) -> dict[str, str]:
    """The files with deck.json's `domains.input` changed by `change`, and nothing else."""
    deck = json.loads(files["deck"])
    change(deck["domains"]["input"])
    return {**files, "deck": json.dumps(deck, indent=1)}


def without(*names: str):
    def change(table: dict) -> None:
        for name in names:
            del table[name]
    return change


@KERNEL
class TheKernelsOwnFloors(unittest.TestCase):
    def test_a_rod_fitted_under_absolute_zero_is_refused_with_the_floor_left_out_of_deck_json(self):
        mine, kernel = ill_formed(self, RODS, ROD_TEXT, ROD_CARD)
        self.assertIn("r.fit goes down to -300 in SI units, and a temperature is at least -5463/20", mine)
        self.assertIn("parts.3", kernel)
        rules, read = parsed(RODS, ROD_TEXT, ROD_CARD)
        hint = {"subject": "r", "mechanism": "rod.stress", "entry": "stress/service", "state": "proved", "partition": "leaf"}
        files = {**grid.bundle(read, rules), "proofs": json.dumps({"format": "petra-proofs/0", "cells": [hint]})}
        said = ask(floors(files, without("temperature")))
        self.assertEqual(said["verdict"], "ILL-FORMED", "it was PASS")
        self.assertIn("types.8 deck domains.input: is not the floors of petra/decks/core.json", findings(said))
        self.assertIn("parts.3", findings(said), "the kernel goes on with core.json's floors")

    def test_a_strut_rested_on_a_completion_under_absolute_zero_is_not_passed(self):
        rules, read = parsed(strut(), STRUT_TEXT, STRUT_CARD)
        files = grid.check(read, rules)[1]
        proofs = json.loads(files["proofs"])
        hint = {"subject": "s", "mechanism": "strut.stress", "entry": "stress/service", "state": "proved", "partition": "leaf",
                "completion": {"keys": [], "loads": [["s", "t", "service", "-300"]]}}
        files = {**files, "proofs": json.dumps({**proofs, "cells": [*proofs["cells"], hint]})}
        self.assertEqual(ask(files)["verdict"], "UNKNOWN")
        said = ask(floors(files, without("temperature")))
        self.assertEqual((said["verdict"], [f["rule"] for f in said["findings"]]), ("ILL-FORMED", ["types.8"]), "it was PASS")

    def test_any_other_floor_is_a_finding_and_another_spelling_of_the_same_is_not(self):
        rules, read = parsed(strut(), STRUT_TEXT, STRUT_CARD)
        files = grid.check(read, rules)[1]
        for label, change in (("a length with no floor", without("length")),
                              ("a strict floor of a length", lambda t: t.update(length={"min": "0", "strict": True})),
                              ("a temperature at zero", lambda t: t.update(temperature={"min": "0", "strict": False})),
                              ("a floor for a force", lambda t: t.update(force={"min": "0", "strict": False})),
                              ("no floors", lambda t: t.clear())):
            with self.subTest(label):
                said = ask(floors(files, change))
                self.assertEqual([f["rule"] for f in said["findings"]], ["types.8"])
        def respelled(table: dict) -> None:
            table["m^1"] = table.pop("length")
            table["about"] = "another text"
        said = ask(floors(files, respelled))
        self.assertEqual((said["findings"], said["verdict"]), ([], "UNKNOWN"))

    def test_the_floors_of_core_json_read_with_no_finding(self):
        rules, read = parsed(RODS, ROD_TEXT.replace("-300 degC", "-40 degC"), ROD_CARD)
        report, files = grid.check(read, rules)
        said = ask(files)
        self.assertEqual((said["findings"], said["verdict"], report.verdict), ([], "FAIL", "FAIL"))


# --- B. a side distance that no plate of its width allows -----------------------------------------------------

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "deck"


def shipped_lap(width: str, side: str, pull: str = "14 kip") -> tuple[str, str]:
    """The passing lap of examples/deck on two 3/8 inch plates of `width`, its side distance `side`, under `pull`."""
    text = (EXAMPLES / "lap_pass.petra").read_text(encoding="utf-8").replace("width 6 inch", f"width {width}").replace("side 3 inch", f"side {side}")
    card = (EXAMPLES / "lap_pass.card").read_text(encoding="utf-8").replace("pull in [0 kip, 45 kip]", f"pull in [0 kip, {pull}]")
    return card, text


def judged(card: str, text: str) -> tuple[str, dict]:
    """petra/grid.py's verdict on a lap of the shipped deck, or why it refuses it, and the kernel's."""
    read = petra.lang.parse_design(card, text, "lap.petra", build_registry())
    rules = grid.owner(read)
    try:
        report, files = grid.check(read, rules)
        mine = report.status
    except grid.ComponentError as exc:
        mine, files = str(exc), grid.bundle(read, rules)
    return mine, ask(files) if verify.binary() else {}


class TheSideOfALap(unittest.TestCase):
    def test_a_side_over_half_the_width_of_a_plate_is_refused(self):
        """1 3/4 inch plates and side 1 inch, the least Table J3.4 allows for a 3/4 inch bolt: no plate of that width has a side
        distance over 7/8 inch, so J3.4 refutes every lap these plates can make, and the lap passed under its waivers."""
        for width, side in (("1.75 inch", "1 inch"), ("4 inch", "6 inch")):
            with self.subTest(width=width, side=side):
                mine, said = judged(*shipped_lap(width, side))
                self.assertIn("splice breaks need 1 of a lap", mine)
                self.assertIn("splice breaks need 2 of a lap", mine)
                self.assertIn("the line of holes lies within plate a", mine)
                if said:
                    self.assertEqual(said["verdict"], "ILL-FORMED", "it was PASS")
                    self.assertIn("splice: breaks need 1 of a lap", findings(said))

    def test_the_widest_side_the_plates_allow_fails_j3_4(self):
        mine, said = judged(*shipped_lap("1.75 inch", "0.875 inch"))
        self.assertEqual(mine, "FAIL")
        if said:
            (cell,) = [c for c in said["cells"] if c["mechanism"] == "lap.side_distance"]
            self.assertEqual((cell["state"], said["verdict"]), ("refuted", "FAIL"))

    def test_a_width_the_card_gives_is_held_over_its_whole_range(self):
        card, text = shipped_lap("6 inch", "1 inch")
        card += 'given tab.width in [1.75 inch, 6 inch] signed "s.engineer@example.org" source "the plate"\n'
        mine, said = judged(card, text.replace("width 6 inch", "width given tab.width", 1))
        self.assertIn("splice breaks need 1 of a lap", mine)
        self.assertIn("down to 889/20000", mine)
        self.assertNotIn("need 2", mine, "the strap is 6 inch wide")
        if said:
            self.assertEqual(said["verdict"], "ILL-FORMED")

    def test_a_side_at_half_the_width_still_passes(self):
        card, text = shipped_lap("6 inch", "3 inch", "45 kip")
        self.assertEqual((card, text), ((EXAMPLES / "lap_pass.card").read_text(encoding="utf-8"), (EXAMPLES / "lap_pass.petra").read_text(encoding="utf-8")))
        mine, said = judged(card, text)
        self.assertEqual(mine, grid.PASS_WAIVED)
        if said:
            self.assertEqual((said["findings"], said["verdict"]), ([], "PASS"))


# --- C. a value of more than 65,536 bits ----------------------------------------------------------------------

TRAIN = made_up([kind("train", *(size(name, "dimensionless") for name in "xyzw"), size("d"))], [asks("train.ratio", "train")],
                [rule("ratio", "train", "train.ratio", le=[["pow", ["mul", "x", "y", "z", "w"], "64"], "2"]),
                 rule("size", "train", "train.ratio", le=[["q", "1", "mm"], "d"])])
"""Four gear stages and a rule on the 64th power of the train's ratio."""


def train(digits: int) -> str:
    """Ratios 1.000...01 to 1.000...09 with `digits` after the point: with 98 the product's denominator has some 1,300 bits,
    and its 64th power some 83,000."""
    x, y, z, w = ("1." + "0" * (digits - 1) + str(k) for k in (1, 3, 7, 9))
    return design(part("train", "r", x=x, y=y, z=z, w=w, d="10 mm"))


class ValuesPastTheBitsOfTheKernel(unittest.TestCase):
    def test_a_power_of_more_than_65536_bits_leaves_its_cell_open(self):
        """The kernel gives the power no value, and the grid proved the cell with it: PASS against UNKNOWN, and petra check exited 4."""
        found, status, _ = cells(self, TRAIN, train(98))
        self.assertEqual((found[("r", "train.ratio", "ratio")], status), ("open", "UNKNOWN"))
        rules, read = parsed(TRAIN, train(98))
        self.assertEqual([c.why for c in grid.check(read, rules)[0].cells if c.entry == "ratio"], ["node 5: a value has more than 65536 bits"])
        found, status, _ = cells(self, TRAIN, train(20))
        self.assertEqual((found[("r", "train.ratio", "ratio")], status), ("proved", "PASS"))

    def test_a_sum_so_far_of_more_than_65536_bits_has_no_value(self):
        """1/3^24000 + 1/7^13800 has some 76,800 bits, and less 1/7^13800 again it has 38,000: the kernel holds each sum so far to
        the bound (`folded` in kernel/Petra/Tape.lean), so the sum has no value, though its own value would fit."""
        nodes = [["c", f"1/{3 ** 8000}"], ["pow", 0, 3], ["c", f"1/{7 ** 4600}"], ["pow", 2, 3], ["neg", 3], ["c", "-1"], ["add", [1, 3, 4, 5]]]
        self.assertEqual(grid.enclosures(nodes, [])[6], "node 6: a value has more than 65536 bits")
        apart = [*nodes[:6], ["add", [1, 5]], ["add", [3, 4]], ["add", [6, 7]]]
        self.assertEqual(grid.enclosures(apart, [])[8], Interval.point(Fraction(1, 3 ** 24000) - 1))
        if verify.binary():
            for tape, state in (({"inputs": [], "nodes": nodes, "roots": [6]}, "open"), ({"inputs": [], "nodes": apart, "roots": [8]}, "proved")):
                said = ask(with_card([cell(tape)]))
                self.assertEqual([c["state"] for c in said["cells"]], [state], said)


# --- D. the unit of a value a completion gives ----------------------------------------------------------------

MAIN = kind("main", size("d"), loads=[{"name": "t", "dim": "temperature", "may_be": "negative", "what": "the steam's temperature"}])
MAINS = made_up([MAIN], [asks("main.dry", "main"), asks("main.size", "main")],
                [rule("dry", "main", "main.dry", le=[["q", "100", "degC"], ["load", "t"]]), rule("size", "main", "main.size", le=[["q", "1", "mm"], "d"])])
"""A steam main carries dry steam only above 100 degC."""
PLAIN = kind("plain", size("d"), loads=[{"name": "t", "dim": "temperature", "may_be": "negative", "what": "the water's temperature"},
                                        {"name": "k", "dim": "force/length", "what": "the stiffness of the support"},
                                        {"name": "n", "dim": "dimensionless", "what": "the number of cycles"}])
PLAINS = made_up([PLAIN], [asks("plain.warm", "plain"), asks("plain.stiff", "plain"), asks("plain.cycles", "plain"), asks("plain.size", "plain")],
                 [rule("warm", "plain", "plain.warm", le=[["q", "0", "degC"], ["load", "t"]]),
                  rule("stiff", "plain", "plain.stiff", le=[["load", "k"], ["q", "5", "N/mm"]]),
                  rule("cycles", "plain", "plain.cycles", le=[["load", "n"], "3"]),
                  rule("size", "plain", "plain.size", le=[["q", "1", "mm"], "d"])])
"""Three loads of three kinds of unit, each read by a line of its own: a temperature, a dimension with no unit of factor 1, and a plain number."""


def printed(rules: dict, text: str, card: str) -> tuple[list[dict | None], list[str]]:
    """The completions of `petra check`'s JSON, and the lines of its text that rest on one."""
    deck, read = parsed(rules, text, card)
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        done = grid.checked(read, deck, card, text, "made-up.card")
    return [c.get("completion") for c in done.to_json()["cells"]], [line for line in done.text().splitlines() if "rested where" in line]


class TheUnitOfACompletedLoad(unittest.TestCase):
    def test_a_temperature_is_printed_in_degc(self):
        text = design(part("plain", "p", d="20 mm"))
        card = HEAD + load("service") + "".join(waive(m, "p") for m in ("plain.warm", "plain.stiff", "plain.cycles"))
        _, status, _ = cells(self, PLAINS, text, card)
        self.assertEqual(status, grid.PASS_WAIVED)
        completions, lines = printed(PLAINS, text, card)
        self.assertEqual([c["loads"] for c in completions if c], [[["p", "t", "service", "0", "degC"]], [["p", "k", "service", "0", "kg^1 s^-2"]],
                                                                  [["p", "n", "service", "0", "1"]]])
        self.assertEqual([line.split("; rested where ")[1].split(" (")[0] for line in lines],
                         ["p.t is 0 degC in case service", "p.k is 0 kg^1 s^-2 in case service", "p.n is 0 in case service"])

    @KERNEL
    def test_the_kernel_prints_a_completion_of_its_hint_with_its_unit(self):
        """The designer's proofs.json rests the dry steam on 295: degC to the kernel, and 21.85 degC to a reader who took it for kelvin."""
        rules, read = parsed(MAINS, design(part("main", "s", d="50 mm")), HEAD + load("service") + waive("main.dry", "s"))
        files = grid.bundle(read, rules)
        hints = [{"subject": "s", "mechanism": "main.dry", "entry": "dry/service", "state": "proved", "partition": "leaf",
                  "completion": {"keys": [], "loads": [["s", "t", "service", "295"]]}},
                 {"subject": "s", "mechanism": "main.size", "entry": "size", "state": "proved", "partition": "leaf"}]
        said = ask({**files, "proofs": json.dumps({"format": "petra-proofs/0", "cells": hints})})
        self.assertEqual(said["verdict"], "PASS")
        self.assertEqual([c.get("completion") for c in said["cells"]], [{"keys": [], "loads": [["s", "t", "service", "295", "degC"]]}, None])


# --- M3. a load a completion puts on a part under a card with no load case ------------------------------------

ANCHOR = kind("anchor", {**key("kind", "chemical", "mechanical"), "optional": True}, size("bond", "force", signed=True),
              loads=[{"name": "tension", "dim": "force", "least": "60 kN", "what": "the tension"}])
ANCHORS = made_up([ANCHOR], [asks("anchor.pullout", "anchor"), asks("anchor.size", "anchor")],
                  [rule("pullout", "anchor", "anchor.pullout", when=["is", "kind", "chemical"], le=[["load", "tension"], "bond"]),
                   rule("size", "anchor", "anchor.size", le=[["q", "1", "kN"], "bond"])])
"""A pull-out rule for chemical anchors alone. At its least, 60 kN, the tension is over the bond, so the waived cell rests on a
mechanical anchor, where no rule reads the tension."""


class TheReasonOfALoadNoCaseNames(unittest.TestCase):
    def test_the_card_puts_the_load_on_the_part(self):
        text = design(part("anchor", "a", kind="unstated", bond="given a.bond"))
        found, status, said = cells(self, ANCHORS, text, HEAD + given("a.bond", "50 kN") + waive("anchor.pullout", "a"))
        self.assertEqual((found[("a", "unread", "tension/")], status), ("open", "UNKNOWN"))
        rules, read = parsed(ANCHORS, text, HEAD + given("a.bond", "50 kN") + waive("anchor.pullout", "a"))
        why = "no rule of the deck reads the load tension that the card puts on a, so nothing checks it"
        self.assertEqual([c.why for c in grid.check(read, rules)[0].cells if c.entry == "tension/"], [why], "it read `that case  puts on a`")
        if verify.binary():
            self.assertEqual([c["reason"] for c in said["cells"] if c["entry"] == "tension/"], [why])
