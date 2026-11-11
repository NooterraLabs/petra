"""The `pick` node of a tape, as the built kernel reads it (kernel/Petra/Tape.lean).

A pick takes the value of the first case whose condition holds, which is how a tape writes
a table read by bands, a table of listed values and an equation with cases. docs/format.md
states the rule. Each test writes the four files as text, runs petra-verify on them and
reads the state it settles the cell on. The tests are skipped when no kernel is built.
"""
import copy
import hashlib
import json
import unittest
from fractions import Fraction

from petra import verify

CARD = json.dumps({"format": "petra-card/0", "name": "plate", "environment": None, "cases": [], "inputs": [], "claims": [], "waivers": []})
DESIGN = json.dumps({"format": "petra-design/0", "name": "plate", "card": "sha256:" + hashlib.sha256(CARD.encode("utf-8")).hexdigest(),
                     "quantities": [], "params": []})
DECK = json.dumps({"format": "petra-deck/0", "domains": {"size": {"min": "0", "strict": True}, "input": {}}, "constants": []})

NO_CASE = "no case of the pick holds somewhere in the box"
TOO_MANY = "a pick with more than 4096 ways to order what it compares"
DIVISION = "division by an interval that contains 0"
AHEAD = "reads a node that is not before it"


def q(x) -> str:
    """A number as the format writes it."""
    return str(Fraction(x))


class Tape:
    """A tape being written. Each method adds a node and gives its index."""

    def __init__(self):
        self.inputs, self.nodes = [], []

    def node(self, *parts) -> int:
        self.nodes.append(list(parts))
        return len(self.nodes) - 1

    def input(self, name, lo, hi=None) -> int:
        """An input over `lo` to `hi`, or at the point `lo`. A `dsg:` label needs no card entry."""
        self.inputs.append({"label": f"dsg:{name}", "lo": q(lo), "hi": q(lo if hi is None else hi)})
        return self.node("s", len(self.inputs) - 1)

    def const(self, x) -> int:
        return self.node("c", q(x))

    def minus(self, a, b) -> int:
        return self.node("add", [a, self.node("neg", b)])

    def pick(self, *cases) -> int:
        return self.node("pick", [list(case) for case in cases])


def le(i, j):
    return ["le", i, j]


def lt(i, j):
    return ["lt", i, j]


def both(*conds):
    return ["and", list(conds)]


def either(*conds):
    return ["or", list(conds)]


def no(cond):
    return ["not", cond]


def split(at, below="leaf", above="leaf", k=0):
    return {"input": k, "at": q(at), "below": below, "above": above}


def ask(nodes, inputs, roots, **proof) -> dict:
    """The kernel's answer to one cell that holds the tape: proved by a partition, or
    refuted by a point when `proof` holds one."""
    cell = {"subject": "plate", "mechanism": "pick", "entry": "test", "state": "refuted" if "point" in proof else "proved",
            "tape": {"inputs": inputs, "nodes": nodes, "roots": roots}, **proof}
    proofs = json.dumps({"format": "petra-proofs/0", "cells": [cell]})
    return verify.ask(verify.binary(), {"card": CARD, "design": DESIGN, "deck": DECK, "proofs": proofs})


def settled(said: dict) -> tuple[str, str]:
    """The state the kernel settled the one cell on, and its reason."""
    assert not said["findings"], said["findings"]
    (cell,) = said["cells"]
    return cell["state"], cell.get("reason", "")


def between(tape: Tape, node: int, lo, hi, partition="leaf") -> tuple[str, str]:
    """What the kernel makes of `lo <= node <= hi` over the tape's box: the state and the
    reason. Root 0 says the node is at most `hi`, and root 1 that it is at least `lo`."""
    tape = copy.deepcopy(tape)
    roots = [tape.minus(node, tape.const(hi)), tape.minus(tape.const(lo), node)]
    return settled(ask(tape.nodes, tape.inputs, roots, partition=partition))


def refused(nodes) -> str:
    """Why the kernel finds a file with these nodes ill formed."""
    said = ask(nodes, [{"label": "dsg:x", "lo": "0", "hi": "1"}], [0], partition="leaf")
    (finding,) = said["findings"]
    assert (said["verdict"], finding["rule"], finding["file"], said["cells"]) == ("ILL-FORMED", "shape", "proofs", []), said
    return finding["why"]


def welds(lo, hi=None, last=True, cut=le) -> tuple[Tape, int]:
    """A table read by bands of thickness: to 1/4 a weld of 1/8, over 1/4 to 1/2 a weld of
    3/16, over 1/2 to 3/4 a weld of 1/4, and over 3/4 a weld of 5/16 when `last`. With `le`
    a band is closed at its upper end, and with `lt` the band above it holds the end."""
    tape = Tape()
    thickness = tape.input("thickness", lo, hi)
    cases = [[cut(thickness, tape.const(end)), tape.const(size)] for end, size in (("1/4", "1/8"), ("1/2", "3/16"), ("3/4", "1/4"))]
    return tape, tape.pick(*cases, *([[None, tape.const("5/16")]] if last else []))


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Pick(unittest.TestCase):
    def test_a_thickness_on_the_end_of_a_band_takes_that_band_exactly(self):
        tape, weld = welds("1/4")
        self.assertEqual(between(tape, weld, "1/8", "1/8"), ("proved", ""))
        self.assertEqual(between(tape, weld, "3/16", "3/16"), ("open", "leaf 0: root 1 is above zero"), "the band above is not taken")
        tape, weld = welds("1/2")
        self.assertEqual(between(tape, weld, "3/16", "3/16"), ("proved", ""))
        self.assertEqual(between(tape, weld, "1/4", "1/4")[0], "open")
        self.assertEqual(between(*welds("1/4", cut=lt), "3/16", "3/16"), ("proved", ""), "with lt the end belongs to the band above")

    def test_a_proved_cell_through_a_pick_is_a_pass(self):
        tape, weld = welds("1/4")
        said = ask(tape.nodes, tape.inputs, [tape.minus(weld, tape.const("1/8"))], partition="leaf")
        self.assertEqual((said["verdict"], said["counts"]["proved"], said["dsg_inputs"]), ("PASS", 1, 1))

    def test_a_range_that_straddles_the_end_takes_both_bands(self):
        tape, weld = welds("3/16", "5/16")
        self.assertEqual(between(tape, weld, "1/8", "3/16"), ("proved", ""))
        self.assertEqual(between(tape, weld, "1/8", "1/8"), ("open", "leaf 0: root 0 is above zero"), "the lower band alone")
        self.assertEqual(between(tape, weld, "3/16", "3/16"), ("open", "leaf 0: root 1 is above zero"), "the upper band alone")
        tape, weld = welds("3/16", "1")
        self.assertEqual(between(tape, weld, "1/8", "5/16"), ("proved", ""), "four bands")
        self.assertEqual(between(tape, weld, "1/8", "1/4")[0], "open")

    def test_a_thickness_outside_every_band_has_no_value(self):
        tape, weld = welds("1", last=False)
        self.assertEqual(between(tape, weld, "0", "1"), ("open", f"leaf 0: node {weld}: {NO_CASE}"))
        tape, weld = welds("5/8", "1", last=False)
        self.assertEqual(between(tape, weld, "0", "1"), ("open", f"leaf 0: node {weld}: {NO_CASE}"), "a part of the range is outside")
        self.assertEqual(between(*welds("5/8", "3/4", last=False), "1/4", "1/4"), ("proved", ""))

    def test_two_cases_that_meet_cover_a_box_that_straddles_them(self):
        tape = Tape()
        x, d = tape.input("x", 0, 2), tape.const(1)
        value = tape.pick([le(x, d), tape.const(10)], [lt(d, x), tape.const(20)])
        self.assertEqual(between(tape, value, 10, 20), ("proved", ""))
        self.assertEqual(between(tape, value, 10, 10)[0], "open")
        self.assertEqual(between(tape, value, 20, 20)[0], "open")

    def test_two_nodes_for_one_input_are_two_quantities_to_a_pick(self):
        tape = Tape()
        x, again, d = tape.input("x", 0, 2), tape.node("s", 0), tape.const(1)
        value = tape.pick([le(x, d), tape.const(10)], [lt(d, again), tape.const(20)])
        self.assertEqual(between(tape, value, 10, 20), ("open", f"leaf 0: node {value}: {NO_CASE}"),
                         "the kernel orders each pair of nodes on its own, so the cases meet only when they compare the same nodes")

    def test_a_three_way_split_covers_a_box_where_every_case_is_possible(self):
        def split3(x, r):
            tape = Tape()
            x, h, r, c = tape.input("x", *x), tape.const(2), tape.input("r", *r), tape.const(5)
            return tape, tape.pick([le(h, x), tape.const(10)], [both(lt(x, h), le(r, c)), tape.const(20)],
                                   [both(lt(x, h), lt(c, r)), tape.const(30)])

        tape, value = split3((1, 3), (4, 6))
        self.assertEqual(between(tape, value, 10, 30), ("proved", ""))
        self.assertEqual(between(tape, value, 10, 20)[0], "open")
        self.assertEqual(between(tape, value, 20, 30)[0], "open")
        self.assertEqual(between(*split3((1, "3/2"), (4, 5)), 20, 20), ("proved", ""))
        self.assertEqual(between(*split3((1, "3/2"), (5, 6)), 20, 30), ("proved", ""))
        self.assertEqual(between(*split3((2, 3), (4, 6)), 10, 10), ("proved", ""))

    def test_a_case_that_is_never_taken_may_be_undefined(self):
        def guarded(d):
            tape = Tape()
            x, d = tape.input("x", 1, 2), tape.const(d)
            undefined = tape.node("div", tape.const(1), tape.const(0))
            return tape, tape.pick([le(x, d), tape.const(7)], [None, undefined]), undefined

        tape, value, undefined = guarded(5)
        self.assertEqual(between(tape, value, 7, 7), ("proved", ""))
        tape, value, undefined = guarded(0)
        self.assertEqual(between(tape, value, 7, 7), ("open", f"leaf 0: node {undefined}: {DIVISION}"), "the reason names the division")
        tape, value, undefined = guarded("3/2")
        self.assertEqual(between(tape, value, 7, 7), ("open", f"leaf 0: node {undefined}: {DIVISION}"), "taken on a part of the box")

    def test_a_pick_that_compares_an_undefined_node_has_no_value(self):
        tape = Tape()
        x = tape.input("x", 1, 2)
        undefined = tape.node("div", tape.const(1), tape.const(0))
        value = tape.pick([le(undefined, x), tape.const(7)], [None, tape.const(7)])
        self.assertEqual(between(tape, value, 7, 7), ("open", f"leaf 0: node {undefined}: {DIVISION}"))

    def test_a_reason_names_the_first_node_that_failed_as_it_did_before_the_pick(self):
        tape = Tape()
        x = tape.input("x", 1, 2)
        division = tape.node("div", x, tape.const(0))
        negative_root = tape.node("sqrt", tape.const(-1))
        total = tape.node("add", [negative_root, division])
        said = ask(tape.nodes, tape.inputs, [x, total], partition="leaf")
        self.assertEqual(settled(said), ("open", f"leaf 0: node {division}: {DIVISION}"),
                         "not the square root the sum reads first, and not root 0, which is above zero")
        said = ask(tape.nodes, tape.inputs, [x, total], point=["1"], which=1)
        self.assertEqual(settled(said), ("open", f"node {division}: {DIVISION}"))

    def test_a_root_through_a_pick_is_refuted_at_a_point(self):
        tape, weld = welds("3/16", "5/16")
        root = tape.minus(weld, tape.const("1/8"))
        said = ask(tape.nodes, tape.inputs, [root], point=["5/16"], which=0)
        self.assertEqual((said["verdict"], settled(said)), ("FAIL", ("refuted", "")))
        said = ask(tape.nodes, tape.inputs, [root], point=["1/4"], which=0)
        self.assertEqual(settled(said), ("open", "root 0 is not above zero at the point"), "the point on the end takes the lower band")

    def test_a_table_of_listed_values_has_a_value_at_a_listed_one_only(self):
        def listed(lo, hi=None):
            tape = Tape()
            x = tape.input("size", lo, hi)
            rows = [(tape.const(size), tape.const(value)) for size, value in (("1/4", 10), ("3/8", 20), ("1/2", 30))]
            return tape, tape.pick(*([both(le(x, size), le(size, x)), value] for size, value in rows))

        tape, value = listed("3/8")
        self.assertEqual(between(tape, value, 20, 20), ("proved", ""))
        tape, value = listed("5/16")
        self.assertEqual(between(tape, value, 0, 100), ("open", f"leaf 0: node {value}: {NO_CASE}"), "between two listed values")
        tape, value = listed("1/4", "3/8")
        self.assertEqual(between(tape, value, 0, 100), ("open", f"leaf 0: node {value}: {NO_CASE}"), "a range holds unlisted values")

    def test_a_malformed_pick_is_ill_formed(self):
        x, one = ["s", 0], ["c", "1"]
        self.assertEqual(refused([x, one, ["pick", [[None, 1], [le(0, 1), 1]]]]), "tape: node 2: null is the condition of a case that is not the last")
        self.assertEqual(refused([x, one, ["pick", []]]), "tape: node 2: a pick of no cases")
        self.assertEqual(refused([x, one, ["pick", [[le(0, 1)]]]]), "tape: node 2: a case of a pick is not a condition and a node")
        self.assertEqual(refused([x, one, ["pick", [[both(), 1]]]]), "tape: node 2: and of no conditions")
        self.assertEqual(refused([x, one, ["pick", [[either(), 1]]]]), "tape: node 2: or of no conditions")
        self.assertEqual(refused([x, one, ["pick", [[["ge", 0, 1], 1]]]]), "tape: node 2: not a condition of this format")
        self.assertTrue(refused([x, one, ["pick", [[both(None), 1]]]]).startswith("tape: node 2: "), "null is not a condition inside one")
        self.assertTrue(refused([x, one, ["pick", [[le(0, 1), "1"]]]]).startswith("tape: node 2: "), "a node is an index")

    def test_a_pick_that_reads_ahead_leaves_its_cell_open(self):
        x, one = ["s", 0], ["c", "1"]
        box = [{"label": "dsg:x", "lo": "0", "hi": "1"}]
        for name, pick in (("a condition", ["pick", [[le(0, 2), 0], [None, 0]]]), ("a value", ["pick", [[le(0, 0), 2]]]),
                           ("a value under null", ["pick", [[None, 2]]]), ("the pick itself", ["pick", [[None, 1]]])):
            with self.subTest(name):
                said = ask([x, pick, one], box, [1], partition="leaf")
                self.assertEqual(settled(said), ("open", f"node 1 {AHEAD}"))

    def test_a_condition_nests_sixteen_deep_and_no_deeper(self):
        def nested(depth):
            """A tape whose root says a pick is at most 1. The pick's first condition is an
            order under `depth - 1` nots, so it is `depth` deep."""
            cond = le(0, 1)
            for _ in range(depth - 1):
                cond = no(cond)
            return [["s", 0], ["c", "1"], ["pick", [[cond, 0], [None, 1]]], ["c", "-1"], ["add", [2, 3]]]

        box = [{"label": "dsg:x", "lo": "0", "hi": "1"}]
        self.assertEqual(settled(ask(nested(16), box, [4], partition="leaf")), ("proved", ""))
        self.assertEqual(refused(nested(17)), "tape: node 2: a condition nests deeper than 16")

    def test_a_split_at_the_end_of_a_band_leaves_both_bands_on_the_leaf_that_holds_the_end(self):
        cut = split("1/4")
        tape, weld = welds("3/16", "5/16")
        self.assertEqual(between(tape, weld, "1/8", "3/16", cut), ("proved", ""), "both leaves evaluate")
        self.assertEqual(between(tape, weld, "1/8", "1/8", cut), ("open", "leaf 1: root 0 is above zero"),
                         "the leaf below the end takes the lower band alone, and the leaf above it starts on the end and takes both")
        self.assertEqual(between(*welds("3/16", "1/4"), "1/8", "1/8"), ("proved", ""), "the leaf below, alone")
        self.assertEqual(between(*welds("1/4", "5/16"), "1/8", "3/16"), ("proved", ""), "the leaf above, alone")
        self.assertEqual(between(*welds("1/4", "5/16"), "3/16", "3/16")[0], "open")
        tape, weld = welds("3/16", "5/16", cut=lt)
        self.assertEqual(between(tape, weld, "3/16", "3/16", cut), ("open", "leaf 0: root 1 is above zero"),
                         "with lt the end is in the upper band, and the leaf below holds it")
        self.assertEqual(between(*welds("1/4", "5/16", cut=lt), "3/16", "3/16"), ("proved", ""))

    def test_a_case_must_be_defined_on_every_leaf_that_touches_where_it_holds(self):
        def root_of(guard):
            tape = Tape()
            x, zero = tape.input("x", -1, 1), tape.const(0)
            inside = tape.node("max", [x, zero]) if guard else x
            return tape, tape.pick([le(zero, x), tape.node("sqrt", inside)], [None, zero])

        tape, value = root_of(guard=False)
        sqrt = value - 1
        self.assertEqual(between(tape, value, 0, 1, split(0)), ("open", f"leaf 0: node {sqrt}: sqrt over an interval with negative values"),
                         "the leaf from -1 to 0 holds the point 0, where the case holds, and the square root has no enclosure on that leaf")
        self.assertEqual(between(*root_of(guard=True), 0, 1, split(0)), ("proved", ""))

    def test_a_pick_has_at_most_4096_ways_to_order_what_it_compares(self):
        def bands(count):
            tape = Tape()
            x = tape.input("x", 0, 10)
            return tape, tape.pick(*([le(x, tape.const(k)), tape.const(k)] for k in range(1, count + 1)), [None, tape.const(count + 1)])

        tape, value = bands(7)
        self.assertEqual(between(tape, value, 1, 8), ("proved", ""), "3^7 = 2187 ways")
        self.assertEqual(between(tape, value, 2, 8)[0], "open")
        tape, value = bands(8)
        self.assertEqual(between(tape, value, 1, 9), ("open", f"leaf 0: node {value}: {TOO_MANY}"), "3^8 = 6561 ways")
        self.assertEqual(between(tape, value, 1, 9, split(4, split(2), split(7))), ("proved", ""), "a partition brings the count down")

    def test_or_and_not_read_one_order_for_a_pair_wherever_it_is_written(self):
        def window(lo, hi=None):
            tape = Tape()
            x, a, b = tape.input("x", lo, hi), tape.const(1), tape.const(2)
            outside = either(lt(x, a), lt(b, x))
            return tape, tape.pick([outside, tape.const(10)], [no(outside), tape.const(20)])

        self.assertEqual(between(*window(0, 3), 10, 20), ("proved", ""), "no way leaves both cases false")
        self.assertEqual(between(*window(0, 3), 10, 10)[0], "open")
        self.assertEqual(between(*window(1, 2), 20, 20), ("proved", ""))
        self.assertEqual(between(*window("1/2"), 10, 10), ("proved", ""))

    def test_a_node_compared_with_itself_is_equal(self):
        tape = Tape()
        x = tape.input("x", 0, 10)
        value = tape.pick([lt(x, x), tape.const(1)], [le(x, x), tape.const(2)])
        self.assertEqual(between(tape, value, 2, 2), ("proved", ""))


if __name__ == "__main__":
    unittest.main()
