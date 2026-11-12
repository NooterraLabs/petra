"""The ninth hostile review of petra-verify (kernel/) and petra/grid.py: what a completion of a
waived cell leaves unchecked. One test per finding.

  A4  An anchor leaves its optional `kind` unstated, and the only rule that reads its bond stress
      and its tension applies when the anchor is chemical. The rule answers because its `when`
      names an unstated key, so it counted as reading them, and they had no `unread` cell. Its
      cell was rested under the completion `mechanical`, under which the rule does not answer:
      PASS_WAIVED, with 1,000 kN of tension and nothing that checked it. What a design reads is
      now worked out under the completions of the rested cells, as for the design that states
      them.
"""
import unittest

from petra import grid
from tests.test_deck_features import ANCHOR, HEAD, asks, cells, design, key, kind, load, made_up, part, reason, rule, size


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


if __name__ == "__main__":
    unittest.main()
