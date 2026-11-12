"""The ninth hostile review of petra-verify (kernel/) and petra/grid.py: what a completion of a
waived cell leaves unchecked. One test per finding.

  A4  An anchor leaves its optional `kind` unstated, and the only rule that reads its bond stress
      and its tension applies when the anchor is chemical. The rule answers because its `when`
      names an unstated key, so it counted as reading them, and they had no `unread` cell. Its
      cell was rested under the completion `mechanical`, under which the rule does not answer:
      PASS_WAIVED, with 1,000 kN of tension and nothing that checked it. What a design reads is
      now worked out under the completions of the rested cells, as for the design that states
      them.
  A3  A pin's shear rule holds for pins up to 30 mm, and the pin is 20 to 40 mm. Stated, its
      cell is open, since the `where` is not proved. Left out of the case, the shear completed
      at zero, and the witness proved only the tape whose root is the rule's inside the `where`:
      PASS_WAIVED. A witness now proves the `where` and the rule over the whole box, or shows the
      `where` holds nowhere, as a complete cell must.
  A1  A strut whose stress rule holds only under -292.5 degC, under every temperature a card
      may state, left its temperature out of the case. The kernel took a completion at -300
      degC, and with a `least` of -300 degC on the load `petra check` found it itself: the
      waiver rested the cell. A spring's play with a `least` of -5 mm, a length that no card
      may state under zero, was completed there. A completion is now held to the floor of its
      dimension as a load of the card is, and a deck whose `least` is under that floor is
      refused.
  C1  The shipped lap with plates 10^-98 inch thick under a pull of 10^99 kip: the ratio of a
      refuted cell was past the largest float, and `petra check` stopped with exit code 4. The
      cell now prints no ratio, and the lap FAILs.
  A5  Under a load case named `where` every rule that reads a load had an entry that ends in
      `/where`, which marks the cell of a range, so its proof was not counted and a design
      whose rules all held was UNKNOWN. Both readers now refuse the name.
"""
import json
import unittest
from pathlib import Path

import petra
from petra import grid
from tests.test_deck_features import (HEAD, KERNEL, asks, cells, design, given, ill_formed, key, kind, load, made_up, no_deck, parsed, part, reads, reason,
                                      rule, size)
from tests.test_kernel_grid import ask, changed, findings


def waive(mechanism: str, on: str) -> str:
    return f'\nwaive {mechanism} on {on} by "t@example.org" reason "test"\n'


# --- A4. what a design reads under a completion -------------------------------------------------------------

ANCHOR_T = kind("anchor", size("d"), size("embed"), size("tau", "stress"), {**key("kind", "chemical", "mechanical"), "optional": True},
                loads=[{"name": "tension", "dim": "force", "what": "the tension on the anchor", "least": "0 kN"}])
ANCHORS = made_up([ANCHOR_T], [asks("anchor.pullout", "anchor"), asks("anchor.embedment", "anchor")],
                  [rule("pullout-bonded", "anchor", "anchor.pullout", when=["is", "kind", "chemical"],
                        le=[["load", "tension"], ["mul", "pi", "d", "embed", "tau"]]),
                   rule("embedment", "anchor", "anchor.embedment", le=[["mul", "4", "d"], "embed"])])
"""The pull-out rule is for bonded anchors alone: pi x 16 mm x 100 mm x 10 MPa = 50.3 kN."""


def anchor(named: str) -> str:
    return design(part("anchor", "a", d="16 mm", embed="100 mm", tau="10 MPa", kind=named))


ANCHOR_CARD = HEAD + load("service", "a tension in [1000 kN, 1000 kN]") + waive("anchor.pullout", "a")
UNREAD = [("a", "unread", "tau"), ("a", "unread", "kind"), ("a", "unread", "tension/service")]


class ReadsUnderACompletion(unittest.TestCase):
    def test_a_rule_that_does_not_answer_under_the_completion_reads_nothing(self):
        found, status, said = cells(self, ANCHORS, anchor("unstated"), ANCHOR_CARD)
        self.assertEqual((found[("a", "anchor.pullout", "pullout-bonded/service")], status), ("waived", "UNKNOWN"))
        self.assertEqual([found[c] for c in UNREAD], ["open"] * 3)
        self.assertEqual(reason(said, "unread", "tau"), "no rule of the deck reads a.tau, so nothing checks it")

    def test_the_design_that_states_the_completion_gets_the_same_cells_but_the_waived_one(self):
        left, _, _ = cells(self, ANCHORS, anchor("unstated"), ANCHOR_CARD)
        stated, status, _ = cells(self, ANCHORS, anchor("mechanical"), ANCHOR_CARD)
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual({c: s for c, s in left.items() if c[1] != "anchor.pullout"}, {c: s for c, s in stated.items() if c[1] != "anchor.pullout"})
        found, status, _ = cells(self, ANCHORS, anchor("chemical"), ANCHOR_CARD)
        self.assertEqual((found[("a", "anchor.pullout", "pullout-bonded/service")], status), ("refuted", "FAIL"))

    def test_with_no_waiver_the_rule_reads_what_its_when_names(self):
        found, status, _ = cells(self, ANCHORS, anchor("unstated"), HEAD + load("service", "a tension in [1000 kN, 1000 kN]"))
        self.assertEqual((found[("a", "anchor.pullout", "pullout-bonded/service")], status), ("open", "UNKNOWN"))
        self.assertFalse([c for c in found if c[1] == "unread"], "no completion is rested, so the rule that answers reads tau and the tension")

    def test_two_rules_that_cover_the_key_are_still_rested_under_the_name_one_holds_by(self):
        coating = {**key("coating", "zinc", "none"), "optional": True}
        pin = kind("pin", size("d"), coating, loads=[{"name": "shear", "dim": "force", "what": "shear", "least": "0 kN"}])
        deck = made_up([pin], [asks("pin.shear", "pin"), asks("pin.size", "pin")],
                       [rule("coated", "pin", "pin.shear", when=["is", "coating", "zinc"], le=[["load", "shear"], ["mul", ["q", "100", "MPa"], "d", "d"]]),
                        rule("bare", "pin", "pin.shear", when=["is", "coating", "none"], le=[["load", "shear"], ["mul", ["q", "50", "MPa"], "d", "d"]]),
                        rule("size", "pin", "pin.size", le=[["q", "6", "mm"], "d"])])
        card = HEAD + load("service", "p shear in [7 kN, 7 kN]") + waive("pin.shear", "p")
        found, status, _ = cells(self, deck, design(part("pin", "p", d="10 mm", coating="unstated")), card)
        self.assertEqual((found, status), ({("p", "pin.shear", "coated/service"): "waived", ("p", "pin.shear", "bare/service"): "waived",
                                            ("p", "pin.size", "size"): "proved"}, grid.PASS_WAIVED))


# --- A3. a witness for a rule with a `where` -------------------------------------------------------------

SHEAR_PIN = kind("pin", size("d"), size("fu", "stress", signed=True), loads=[{"name": "shear", "dim": "force", "what": "shear on the pin", "least": "0 kN"}])
UP_TO_30 = made_up([SHEAR_PIN], [asks("pin.shear", "pin"), asks("pin.size", "pin")],
                   [rule("shear", "pin", "pin.shear", where=[{"le": ["d", ["q", "30", "mm"]], "why": "the formula is for pins up to 30 mm"}],
                         le=[["load", "shear"], ["mul", "0.6", "fu", ["div", ["mul", "pi", "d", "d"], "4"]]]),
                    rule("size", "pin", "pin.size", le=[["q", "6", "mm"], "d"])])
"""A shear rule for pins up to 30 mm."""
TWO_PINS = design(part("pin", "p", d="given p.d", fu="given p.fu"), part("pin", "q", d="20 mm", fu="given q.fu"))


def pin_card(d: tuple[str, str], *more: str) -> str:
    """The card's one case puts a shear on q, and on p only what `more` gives."""
    return (HEAD + given("p.d", *d) + given("p.fu", "400 MPa") + given("q.fu", "400 MPa")
            + load("service", "q shear in [10 kN, 10 kN]", *more) + waive("pin.shear", "p"))


class AWhereUnderACompletion(unittest.TestCase):
    def test_a_load_left_out_does_not_rest_a_rule_whose_where_is_not_proved(self):
        """From 20 to 40 mm the `where` holds on part of the box. Stated, the shear cell is open, and the waiver does not rest it. Left out,
        it was rested under the completion of zero shear, whose witness proved the rule only inside the `where`."""
        for more in ((), ("p shear in [0 kN, 0 kN]",)):
            with self.subTest(stated=bool(more)):
                found, status, _ = cells(self, UP_TO_30, TWO_PINS, pin_card(("20 mm", "40 mm"), *more))
                self.assertEqual((found[("p", "pin.shear", "shear/service")], status), ("open", "UNKNOWN"))

    def test_a_load_left_out_rests_a_rule_whose_where_and_rule_are_proved_under_the_completion(self):
        found, status, said = cells(self, UP_TO_30, TWO_PINS, pin_card(("10 mm", "20 mm")))
        self.assertEqual((found[("p", "pin.shear", "shear/service")], status), ("waived", grid.PASS_WAIVED))
        found, status, _ = cells(self, UP_TO_30, TWO_PINS, pin_card(("10 mm", "20 mm"), "p shear in [0 kN, 0 kN]"))
        self.assertEqual((found[("p", "pin.shear", "shear/service/where")], found[("p", "pin.shear", "shear/service")], status), ("proved", "proved", "PASS"))

    def test_a_load_left_out_rests_a_rule_whose_where_holds_nowhere_under_the_completion(self):
        for more, state in (((), "waived"), (("p shear in [0 kN, 0 kN]",), "waived")):
            found, status, _ = cells(self, UP_TO_30, TWO_PINS, pin_card(("40 mm", "50 mm"), *more))
            self.assertEqual((found[("p", "pin.shear", "shear/service")], status), (state, grid.PASS_WAIVED))

    @KERNEL
    def test_the_kernel_takes_no_partition_that_proves_the_rule_only_inside_its_where(self):
        """The hint of the review: zero shear, and one leaf, which proves the tape whose root is the rule's inside the `where` and -1
        outside it. It proves neither the `where` nor the rule over the box."""
        rules, read = parsed(UP_TO_30, TWO_PINS, pin_card(("20 mm", "40 mm")))
        report, files = grid.check(read, rules)
        (cell,) = [h for h in json.loads(files["proofs"])["cells"] if h["subject"] == "p" and h["mechanism"] == "pin.shear"]
        for partition in ("leaf", None):
            hint = {**cell, "completion": {"keys": [], "loads": [["p", "shear", "service", "0"]]}, **({"partition": partition} if partition else {})}
            said = ask({**files, "proofs": json.dumps({"format": "petra-proofs/0", "cells": [hint]})})
            (found,) = [c for c in said["cells"] if c["subject"] == "p" and c["mechanism"] == "pin.shear"]
            self.assertEqual((said["findings"], found["state"], said["verdict"]), ([], "open", "UNKNOWN"), partition)


# --- A1. a completion under the floor of its dimension -----------------------------------------------------

def strut(least: str | None = None) -> dict:
    """A strut held between two walls, set at 20 degC: its stress is push / area + 2.4 MPa per degC of t - 20 degC."""
    temperature = {"name": "t", "dim": "temperature", "may_be": "negative", "what": "the strut's temperature in the case", **({"least": least} if least else {})}
    strut_t = kind("strut", size("area", "area"), size("Fy", "stress", signed=True),
                   loads=[{"name": "push", "dim": "force", "what": "the push on the strut", "least": "0 kN"}, temperature])
    stress = ["add", ["div", ["load", "push"], "area"], ["mul", ["div", ["q", "2.4", "MPa"], ["q", "1", "degC"]], ["sub", ["load", "t"], ["q", "20", "degC"]]]]
    return made_up([strut_t], [asks("strut.stress", "strut"), asks("strut.size", "strut")],
                   [rule("stress", "strut", "strut.stress", le=[stress, "Fy"]), rule("size", "strut", "strut.size", le=[["q", "50", "mm2"], "area"])])


STRUT_TEXT = design(part("strut", "s", area="100 mm2", Fy="given s.Fy"))
STRUT_CARD = HEAD + given("s.Fy", "250 MPa") + load("service", "s push in [100 kN, 100 kN]") + waive("strut.stress", "s")
"""1,000 MPa of push against 250 MPa: the rule holds only under -292.5 degC, where no card may state a temperature."""


class CompletionsAboveTheFloor(unittest.TestCase):
    def test_a_temperature_left_out_is_not_completed_under_absolute_zero(self):
        found, status, _ = cells(self, strut(), STRUT_TEXT, STRUT_CARD)
        self.assertEqual((found[("s", "strut.stress", "stress/service")], status), ("open", "UNKNOWN"))

    @KERNEL
    def test_the_kernel_takes_no_completion_under_the_floor(self):
        rules, read = parsed(strut(), STRUT_TEXT, STRUT_CARD)
        report, files = grid.check(read, rules)
        proofs = json.loads(files["proofs"])
        for t, state in (("-300", "open"), ("-5463/20", "open")):
            hint = {"subject": "s", "mechanism": "strut.stress", "entry": "stress/service", "state": "proved", "partition": "leaf",
                    "completion": {"keys": [], "loads": [["s", "t", "service", t]]}}
            said = ask({**files, "proofs": json.dumps({**proofs, "cells": [*proofs["cells"], hint]})})
            (cell,) = [c for c in said["cells"] if c["mechanism"] == "strut.stress"]
            self.assertEqual((said["findings"], cell["state"], said["verdict"]), ([], state, "UNKNOWN"), t)

    def test_a_least_under_the_floor_that_holds_is_refused_by_both_readers(self):
        mine, kernel = no_deck(self, strut("-300 degC"))
        for said in (mine, kernel):
            self.assertIn("field t: its least, -300 in SI units, is under -5463/20, the floor of a temperature", said)
        spring = kind("spring", size("rate", "force/length"), loads=[{"name": "play", "dim": "length", "what": "the free play", "least": "-5 mm"}])
        mine, kernel = no_deck(self, made_up([spring], [asks("spring.preload", "spring")], [rule("preload", "spring", "spring.preload", le=[["load", "play"], ["q", "-1", "mm"]])]))
        for said in (mine, kernel):
            self.assertIn("field play: its least, -1/200 in SI units, is under 0, the floor of a length", said)
        mine, kernel = no_deck(self, made_up([kind("plate", size("t", least="-1 mm"))]))
        self.assertIn("field t: its least", kernel)

    def test_a_least_over_the_floor_or_under_a_floor_that_negative_lifts_is_read(self):
        reads(self, strut("-40 degC"))
        reads(self, made_up([kind("holder", size("x", may_be="negative", least="-1 mm"),
                                  loads=[{"name": "f", "dim": "length", "what": "f", "may_be": "negative", "least": "-1 mm"}])]))


# --- C1. a ratio past the largest float ------------------------------------------------------------------

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "deck"
TINY, HUGE = "0." + "0" * 97 + "1", "1" + "0" * 99


class ARatioPastTheLargestFloat(unittest.TestCase):
    def test_the_shipped_lap_under_a_pull_of_ten_to_the_99_kip_fails(self):
        """Plates 10^-98 inch thick and wide, of 10^-98 ksi, carry about 10^-196 kip, and the pull reaches 10^99: the demand over the
        capacity is past the largest float, and float() of it raised OverflowError, which stopped petra check with exit code 4."""
        text = (EXAMPLES / "lap_pass.petra").read_text(encoding="utf-8").replace("0.375 inch", f"{TINY} inch").replace("6 inch", f"{TINY} inch")
        card = (EXAMPLES / "lap_pass.card").read_text(encoding="utf-8").replace("36 ksi", f"{TINY} ksi").replace("45 kip", f"{HUGE} kip")
        found = petra.check(card, text, path="lap.petra", repair=False)
        self.assertEqual(found["status"], "FAIL")
        yields = [c for c in found["cells"] if c["mechanism"] == "lap.ply_yield"]
        self.assertEqual([(c["state"], c.get("ratio")) for c in yields], [("refuted", None)] * 2)


# --- A5. a load case named `where` -----------------------------------------------------------------------

LOADED_PIN = made_up([SHEAR_PIN], [asks("pin.shear", "pin")],
                     [rule("shear", "pin", "pin.shear", le=[["load", "shear"], ["mul", "0.6", "fu", ["div", ["mul", "pi", "d", "d"], "4"]]])])
ONE_PIN = design(part("pin", "p", d="20 mm", fu="given p.fu"))


def one_pin(case: str) -> str:
    return HEAD + given("p.fu", "400 MPa") + load(case, "p shear in [10 kN, 10 kN]")


class ACaseNamedWhere(unittest.TestCase):
    def test_a_case_named_where_is_refused_by_both_readers(self):
        """Under a case named `where` the rule's cell was entered `shear/where`, the entry of a range, and its proof did not count: a pin
        whose one rule held was UNKNOWN."""
        found, status, _ = cells(self, LOADED_PIN, ONE_PIN, one_pin("service"))
        self.assertEqual((found, status), ({("p", "pin.shear", "shear/service"): "proved"}, "PASS"))
        mine, kernel = ill_formed(self, LOADED_PIN, ONE_PIN, one_pin("where"))
        for said in (mine, kernel):
            self.assertIn("a load case is not named where: an entry that ends in /where is the range of a rule", said)

    @KERNEL
    def test_a_name_in_cases_that_no_load_has_is_not_where_either(self):
        rules, read = parsed(LOADED_PIN, ONE_PIN, one_pin("service"))
        files = grid.check(read, rules)[1]
        said = ask(changed(files, "card", lambda card: card["cases"].append("where")))
        self.assertIn("shape card cases: a load case is not named where", findings(said))


if __name__ == "__main__":
    unittest.main()
