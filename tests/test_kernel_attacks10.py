"""The tenth hostile review of petra-verify (kernel/) and petra/grid.py. One test per finding.

  A   The floors of deck.json decided verdicts for a design with parts: a number of a field
      that may be negative was held to them, and so was a completion. A reader is told to
      check `cells_from`, `hashes.rules` and `hashes.card`, and none covers deck.json. With
      the floor of a temperature left out of it, a rod fitted at -300 degC and a strut rested
      on a completion at -300 degC were PASS. With `--rules` the kernel now holds the floors
      of petra/decks/core.json itself, and a deck.json that gives others is a finding (type
      rule 8).
"""
import json
import unittest

from petra import grid
from tests.test_deck_features import HEAD, KERNEL, asks, design, given, ill_formed, kind, load, made_up, parsed, part, rule, size
from tests.test_kernel_attacks9 import STRUT_CARD, STRUT_TEXT, strut
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
