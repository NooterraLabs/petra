"""What the kernel does where docs/format.md and docs/deck.md once left a reader to guess.

A second kernel was written from the two pages alone, and its writer listed each place where
the pages did not say what to do (bench/twin/AMBIGUITIES.md, H1 to H19). The pages now say it.
Each test here holds the kernel, and petra/grid.py where it reads the same thing, to the
sentence the pages gained. H7, H9 and H16 were corrected in the pages before, and nothing
reaches H15. The tests of the kernel are skipped when no kernel is built.
"""
import json
import unittest

from petra import grid, verify
from tests.test_deck_features import ANCHOR, HEAD, asks, cells, design, kind, made_up, no_deck, part, reads, rule, size
from tests.test_kernel_attacks3 import core_domains, empty_card, sha, text, with_card, with_rules
from tests.test_kernel_grid import ask

KERNEL = unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
PLAIN = kind("t", size("w"))


def number(dim: str, value: str = "1") -> list[dict]:
    return [{"number": {"dim": dim, "lo": value, "hi": value}}]


def found(said: dict) -> list[tuple[str, str, str]]:
    return [(f["rule"], f["file"], f["item"]) for f in said["findings"]]


@KERNEL
class ADimension(unittest.TestCase):
    """H1 and H2 (format.md, "Numbers")."""

    def said(self, dim: str) -> list[tuple[str, str, str]]:
        return found(ask(with_card([], inputs=[{"name": "x", "dim": dim, "lo": "1", "hi": "1", "by": "b"}])))

    def test_the_bases_stand_in_any_order_and_a_base_twice_is_added(self):
        for dim in ("m^3 s^-1", "s^-1 m^3", "kg^1 m^1 s^-2", "m^1 m^1", "m^0", "m^-0", "m^007", "degC^1 A^2", "m^1 m^-1"):
            with self.subTest(dim):
                self.assertEqual(self.said(dim), [])
        area = kind("t", size("a", "area"))
        for dim in ("m^1 m^1", "m^2", "area", "m^3 m^-1", "s^0 m^2"):
            with self.subTest(dim):
                said = ask(with_rules(made_up([area]), empty_card(), [{"name": "p", "type": "t", "lines": [{"field": "a", "args": number(dim)}]}]))
                self.assertEqual(said["findings"], [], "the number of a part has the dimension of its field by the exponents")

    def test_a_base_has_its_hat_and_its_whole_number_and_one_space_parts_two(self):
        for dim in ("m", "", "m^+1", "m^1  s^1", " m^1", "m^1 ", "m^1.0", "M^1", "m^", "m ^1", "m^1\ts^1", "meter^1", "m^1,s^1"):
            with self.subTest(dim):
                self.assertEqual(self.said(dim), [("types.4", "card", "x")])

    def test_the_dim_of_a_quantity_a_param_and_a_bound_is_read_no_further(self):
        files = with_card([])
        body = json.loads(files["design"])
        body["quantities"] = [{"type": "t", "entity": "e", "line": "1", "field": "f", "role": "size", "dim": "no dimension at all", "lo": "1", "hi": "1"}]
        body["params"] = [{"name": "p", "dim": "m", "lo": "1", "hi": "1"}]
        self.assertEqual(ask({**files, "design": text(body)})["findings"], [])
        claim = {"name": "k", "subject": "s", "quantity": "q", "rel": "le", "cases": [], "bound": {"dim": "m m", "lo": "1", "hi": "1"}}
        card = json.loads(files["card"])
        self.assertEqual(ask({**files, "card": text({**card, "claims": [claim]}), "design": text({**body, "card": sha(text({**card, "claims": [claim]}))})})["findings"], [])


@KERNEL
class TheBytesOfAName(unittest.TestCase):
    """H3 (format.md, "What the kernel holds and prints")."""

    def test_each_character_prints_in_the_bytes_the_page_says(self):
        bytes_of = {"a": 1, "\x7f": 1, '"': 2, "\\": 2, "\n": 2, "\r": 2, "\t": 6, "\f": 6, "\b": 6, "\x01": 6, "\x1f": 6, "é": 2, "€": 3, "\U0001F600": 4}
        for char, each in bytes_of.items():
            with self.subTest(repr(char)):
                most = 64 // each
                for count, refused in ((most, False), (most + 1, True)):
                    said = ask(with_rules(made_up([kind("t")]), empty_card(), [{"name": char * count, "type": "t", "lines": []}]))
                    self.assertEqual(bool(said["findings"]), refused, f"{count} of them")
                    self.assertEqual(grid._long(char * count), refused, "petra/grid.py counts as the kernel does")


class AValue(unittest.TestCase):
    """H4, H5, H6 and H11 (deck.md, "A value with its unit" and "A table")."""

    def least(self, value: str) -> dict:
        return made_up([kind("t", size("w", least=value))])

    def test_a_q_takes_what_a_value_takes(self):
        once = kind("t", size("n", "dimensionless", whole=True))
        same = [(["q", "29,000", "ksi"], ["q", "29000", "ksi"]), (["q", "1 1/8", "inch"], ["q", "28.575", "mm"]), (["q", "3", ""], "3"), (["q", "1,234.5", "mm"], ["q", "1234.5", "mm"])]
        lines = [asks(f"m{k}", "t") for k in range(len(same))]
        rules = [rule(f"{way}{k}", "t", f"m{k}", le=[["mul", "n", a if way == "up" else b], ["mul", "n", b if way == "up" else a]]) for k, (a, b) in enumerate(same) for way in ("up", "down")]
        states, verdict, _ = cells(self, made_up([once], lines, rules), design(part("t", "p", n="1")))
        self.assertEqual((verdict, set(states.values())), ("PASS", {"proved"}), "each is at most the other, so the two are one value")

    def test_the_first_space_parts_the_number_from_its_unit(self):
        for value in ("3  inch", "3 \tinch", "3 \ninch", " 3 inch ", "3 inch\r\n", "1 1/8  inch"):
            with self.subTest(repr(value)):
                reads(self, self.least(value))
        for value in ("3\tinch", "3\ninch", "3 inch", "1  1/8 inch", "1\t1/8 inch", "3 in ch"):
            with self.subTest(repr(value)):
                no_deck(self, self.least(value))

    def test_a_comma_stands_before_a_decimal_point_and_never_with_a_slash(self):
        for value in ("1,234.5 mm", "29,000 mm", "1,000,000 mm"):
            with self.subTest(value):
                reads(self, self.least(value))
        for value in ("1,000/3 mm", "1,000 1/8 inch", "1 1,000/3 inch", "1.000,5 mm", "1/1,000 mm", "2,90 mm", "1234,567 mm"):
            with self.subTest(value):
                no_deck(self, self.least(value))

    def test_a_cell_is_stripped_before_it_is_asked_whether_it_states_a_unit(self):
        table = {"id": "made-up/t", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "x", "dim": "length", "range": ["1 mm", "9 mm"]}],
                 "table": {"down": {"by": "x", "bands": [["0 mm", "5 mm"], ["5 mm", "10 mm"]]}, "unit": "inch", "cells": ["1 ", " 2\t"]}}
        both = [rule("up", "t", "m", le=[["row", "made-up/t", {"x": "w"}], ["q", "1", "inch"]]), rule("down", "t", "m", le=[["q", "1", "inch"], ["row", "made-up/t", {"x": "w"}]])]
        states, verdict, _ = cells(self, made_up([PLAIN], [asks("m", "t")], both, [table]), design(part("t", "p", w="2 mm")))
        self.assertEqual((verdict, set(states.values())), ("PASS", {"proved"}), '"1 " under the unit inch is 1 inch')
        no_deck(self, made_up([PLAIN], [asks("m", "t")], both, [{**table, "table": {**table["table"], "cells": ["1\tinch", "2"]}}]))
        no_deck(self, made_up([PLAIN], [asks("m", "t")], both, [{**table, "table": {**table["table"], "cells": ["1 1/8", "2"]}}]))


@KERNEL
class TheFloorsOfTheDeck(unittest.TestCase):
    """H12 and H13 (format.md, "deck.json" and "Types")."""

    def test_a_floor_that_lacks_its_min_or_its_strict_is_a_shape_finding(self):
        for value in ({"min": "0"}, {"strict": False}, {"min": 0, "strict": False}, {"min": "0", "strict": "no"}, [], "0", None):
            with self.subTest(json.dumps(value)):
                files = with_card([])
                domains = core_domains()
                domains["input"] = {**domains["input"], "m^7": value}
                said = ask({**files, "deck": text({"format": "petra-deck/0", "domains": domains, "constants": []})})
                self.assertEqual((said["verdict"], [(f["rule"], f["file"]) for f in said["findings"]]), ("ILL-FORMED", [("shape", "deck")]))

    def test_the_shape_and_type_rules_are_applied_with_parts_and_without(self):
        unsigned = [{"name": "x", "dim": "length", "lo": "1", "hi": "1", "by": ""}]
        self.assertEqual(found(ask(with_card([], inputs=unsigned))), [("types.5", "card", "x")])
        said = ask(with_rules(made_up([PLAIN]), empty_card(unsigned), [{"name": "p", "type": "t", "lines": [{"field": "w", "args": number("length")}]}]))
        self.assertIn(("types.5", "card", "x"), found(said))


@KERNEL
class ALoadOfTheCard(unittest.TestCase):
    """H10 (format.md, Parts 6)."""

    LOADED = {"type": "t", "what": "a t", "fields": [size("w")], "loads": [{"name": "V", "dim": "force", "what": "V"}]}

    def said(self, **change: str) -> list[tuple[str, str, str]]:
        load = {"name": "x", "dim": "force", "lo": "0", "hi": "1", "by": "b", "case": "c" * 65, "on": "p", "field": "V", **change}
        return found(ask(with_rules(made_up([self.LOADED]), empty_card([load]), [{"name": "p", "type": "t", "lines": [{"field": "w", "args": number("length")}]}])))

    def test_the_name_of_a_case_is_held_to_its_limit_for_a_load_that_breaks_nothing_else(self):
        self.assertEqual(self.said(), [("shape", "card", "x")])
        self.assertEqual(self.said(case="a/b"), [("shape", "card", "x")])
        self.assertEqual(self.said(case="c" * 64), [])

    def test_a_load_that_breaks_something_else_is_a_finding_of_parts_6_alone(self):
        for change in ({"on": "nobody"}, {"field": "W"}, {"dim": "length"}):
            with self.subTest(change):
                self.assertEqual(self.said(**change), [("parts.6", "card", "x")])


class ARuleThatIsNotRun(unittest.TestCase):
    """H17 (deck.md, "A deck in the grid")."""

    def test_the_rule_of_a_waived_line_and_of_a_line_that_cannot_arise_still_reads(self):
        flag = {"name": "fit", "one_of": ["loose", "tight"], "what": "fit"}
        deck = made_up([kind("t", size("w"), size("v"), flag)],
                       [asks("m", "t"), asks("n", "t", unless={"when": ["is", "fit", "tight"], "why": "a tight one has none"})],
                       [rule("m", "t", "m", le=["w", ["q", "1", "m"]]), rule("n", "t", "n", le=["v", ["q", "1", "m"]])])
        waived = HEAD + 'waive m on p by "t@example.org" reason "tested"\n'
        states, _, _ = cells(self, deck, design(part("t", "p", w="1 mm", v="1 mm", fit="tight")), waived)
        # The rule of the waived line is run, since a waiver rests only a cell that would be open: it proves, and the waiver was not
        # needed. Until then the line was one waived cell. The rule of the line that cannot arise is not run, and still reads v.
        self.assertEqual(states, {("p", "m", "m"): "proved", ("p", "n", ""): "not_applicable"}, "no field is unread: w is read by a rule that was run, and v by one that was not")
        states, verdict, _ = cells(self, deck, design(part("t", "p", w="2 m", v="1 mm", fit="tight")), waived)
        self.assertEqual((states["p", "m", "m"], verdict), ("refuted", "FAIL"), "no waiver hides a refutation")


@KERNEL
class WhenTheNamesAreTested(unittest.TestCase):
    """H18 and H19 (format.md, "Shape" and "Cells from a deck of rules")."""

    def test_the_names_of_the_card_and_the_design_are_tested_when_the_deck_holds_together(self):
        long, parts = "c" * 201, [{"name": "p", "type": "t", "lines": [{"field": "w", "args": number("length")}]}]
        said = ask(with_rules(made_up([PLAIN]), empty_card(name=long), parts, name=long))
        self.assertEqual(sorted(found(said)), [("shape", "card", "name"), ("shape", "design", "name")])
        broken = {**made_up([PLAIN]), "more": 1}
        said = ask(with_rules(broken, empty_card(name=long), parts, name=long))
        self.assertEqual([f["file"] for f in said["findings"]], ["rules"], "with a deck that does not hold together the finding is the deck's")

    def test_a_design_past_the_cells_is_a_finding_of_limits_on_the_parts_of_the_design(self):
        deck = made_up([kind("t")], [asks("m", "t")])
        said = ask(with_rules(deck, empty_card(), [{"name": f"p{k}", "type": "t", "lines": []} for k in range(10_001)]))
        self.assertEqual(found(said), [("limits", "design", "parts")])
        self.assertIn("more than 10000 cells", said["findings"][0]["why"])


@KERNEL
class TheOrdersOfATable(unittest.TestCase):
    """H14 (format.md, "How the kernel writes a table")."""

    def reason(self, down: dict, count: int) -> str:
        """The reason of the one cell, or why the deck is refused when it is."""
        table = {"id": "made-up/t", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "x", "dim": "length", "range": ["1 m", "2 m"]}],
                 "table": {"down": {"by": "x", **down}, "unit": "m", "cells": ["1"] * count}}
        deck = made_up([PLAIN], [asks("m", "t")], [rule("m", "t", "m", le=["w", ["row", "made-up/t", {"x": "w"}]])], [table])
        said = ask(with_rules(deck, empty_card(), [{"name": "p", "type": "t", "lines": [{"field": "w", "args": number("length", "3/2")}]}]))
        if said["findings"]:
            self.assertEqual([f["file"] for f in said["findings"]], ["rules"])
            return said["findings"][0]["why"]
        (cell,) = said["cells"]
        return cell.get("reason", "")

    def test_a_band_with_two_ends_has_two_orders_one_with_one_end_has_one_and_a_listed_value_two(self):
        bands = [[f"{k} m", f"{k + 1} m"] for k in range(600)]
        self.assertIn("would compare 1200 orders", self.reason({"bands": bands}, 600))
        self.assertIn("would compare 1199 orders", self.reason({"bands": bands[:-1] + [["599 m", None]]}, 600))
        self.assertIn("would compare 1200 orders", self.reason({"at": [f"{k} m" for k in range(600)]}, 600))

    def test_a_deck_whose_pick_holds_1024_orders_is_read_and_one_of_1025_is_refused(self):
        bands = [[f"{k} m", f"{k + 1} m"] for k in range(513)]
        self.assertNotIn("orders", self.reason({"bands": bands[:512]}, 512))
        self.assertIn("would compare 1025 orders, over the budget of 1024", self.reason({"bands": bands[:512] + [["512 m", None]]}, 513))


@KERNEL
class TheStepsOfTheCells(unittest.TestCase):
    """H8 (format.md, "Steps"). A thousand parts, and a line whose `unless` is an `or` of `n`
    conditions, so each part costs `n` and a constant: the design is within the 10,000,000
    steps while `n` and the constant are at most 10,000. Each test names the constant the page
    gives and holds the kernel to it from both sides."""

    FIT = {"name": "fit", "one_of": ["a", "b"], "what": "fit"}
    LOADS = [{"name": "V", "dim": "force", "what": "V"}, {"name": "T", "dim": "force", "what": "T"}]

    def said(self, n: int, fit: str = "a", le: list = ("w", ["q", "1", "m"]), cases: int = 0, waived: bool = False, rows: list = (), **more) -> list[tuple[str, str, str]]:
        deck = made_up([{**kind("t", size("w"), size("r", "dimensionless"), self.FIT), "loads": self.LOADS}],
                       [asks("m", "t", unless={"when": ["or"] + [["is", "fit", "b"]] * n, "why": "w"})], [rule("m", "t", "m", le=list(le), **more)], rows)
        inputs = [{"name": f"i{c}", "dim": "force", "lo": "0", "hi": "1", "by": "b", "case": f"c{c}", "on": "p0", "field": "V"} for c in range(cases)]
        card = {**empty_card(inputs), "waivers": [{"subject": f"p{k}", "mechanism": "m", "by": "b", "reason": "r"} for k in range(1_000)] if waived else []}
        lines = [{"field": "w", "args": number("length", "1/1000")}, {"field": "r", "args": number("dimensionless", "3/2")}, {"field": "fit", "args": [{"word": fit}]}]
        return found(ask(with_rules(deck, card, [{"name": f"p{k}", "type": "t", "lines": lines} for k in range(1_000)])))

    def assertConstant(self, constant: int, **how) -> None:
        self.assertEqual(self.said(10_000 - constant, **how), [], f"n and {constant} are 10,000")
        self.assertEqual(self.said(10_001 - constant, **how), [("limits", "design", "parts")], "one more is over the steps")

    def test_a_line_that_cannot_arise_pays_for_its_rules_and_a_waived_line_for_running_them(self):
        """Item 1: the line, 1, its `unless`, 1 + n, and its rule, 1. Item 5: the part, 1, the
        rule, 1, and the field it reads, 1. For a line that cannot arise no tape is written,
        so items 3 and 4 are nothing. The rule of a waived line is run, since a waiver rests
        only a cell that would be open: it pays its weight, 2, and the 4 nodes of its tape,
        as the rule of a line that is not waived does. Until then a waived line paid 6."""
        self.assertConstant(6, fit="b")
        self.assertConstant(6 + 2 + 4, waived=True)

    def test_a_tape_pays_the_weight_of_its_rule_and_a_step_for_each_node(self):
        """As above, and the weight of `w <= 1 m`, which is 2, and the 4 nodes of its tape:
        the field, the constant, its negative and their sum."""
        self.assertConstant(6 + 2 + 4)

    def test_a_rule_with_where_pays_its_weight_twice_whether_or_not_its_range_is_proved(self):
        """The weight is 4, a field and a constant for `le` and for `where`, and it is paid
        twice before a tape is written. The tape of the range has 4 nodes. proofs.json has
        no hint here, so the range is not proved, and the tape of `le` inside the range is
        written in place of the tape of `le`: the field, the two constants, the negative and
        the sum, and the pick that is the sum inside the range and its constant -1 outside."""
        self.assertConstant(6 + 2 * 4 + 4 + 7, where=[{"le": [["q", "1", "um"], "w"], "why": "w"}])

    def test_every_case_of_the_card_counts_for_every_load_a_rule_reads(self):
        """Item 1 has one more for each of the two loads the rule reads, and so has item 5.
        Item 2: the 9 cases of the card times the 2 loads, for every part, though the cases
        put V on one part and T on none. No case puts both, so no weight is paid and no tape
        is written."""
        self.assertConstant(6 + 2 + 2 + 8 * 2, le=[["mul", ["add", ["load", "V"], ["load", "T"]], "w"], ["q", "1", "Nm"]], cases=8)

    WIDE = {"id": "made-up/wide", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "x", "dim": "length", "range": ["1 m", "2 m"]}],
            "table": {"down": {"by": "x", "bands": [[f"{k} m", f"{k + 1} m"] for k in range(512)]}, "unit": "m", "cells": ["1"] * 512}}
    """A table of 512 bands, which is a pick of 1,024 orders, as many as a pick may compare. A
    deck with one more band is not read. The tape of a rule that reads it holds the 513 ends of
    the bands, each a constant, and the pick: 514 nodes."""
    ENDS = 513
    WEIGHTS = (("neg", ["neg", "r"], 1 + 2), ("abs", ["abs", "r"], 1 + 2), ("sqrt", ["sqrt", "r"], 1 + 2), ("exp", ["exp", "r"], 1 + 2), ("ln", ["ln", "r"], 1 + 2),
               ("div", ["div", "r", "2"], 1 + 1 + 3), ("sub", ["sub", "r", "2"], 1 + 1 + 2 + 3), ("a whole power", ["pow", "r", "3"], 1 + 2),
               ("the power 0", ["pow", "r", "0"], 1 + 2 + 1 + 3), ("a negative power", ["pow", "r", "-2"], 1 + 2 + 1 + 3), ("a half power", ["pow", "r", "1/2"], 1 + 2 + 2),
               ("another fixed power", ["pow", "r", "1/3"], 1 + 1 + 2 + 3 + 2), ("a power that varies", ["pow", "r", "r"], 1 + 1 + 2 + 3 + 2),
               ("min", ["min", "r", "2", "3"], 3 + 1 + 3), ("max", ["max", "r", "2"], 2 + 1 + 2), ("pi", "pi", 1))
    """An expression over the plain number `r`, and the weight the page gives it: 1 for each name and number, and the weight of each step."""

    def test_the_weight_of_a_rule_is_the_sum_the_page_gives(self):
        """`le` reads the table, which weighs 1, 512 places and 512 cells, in a row that binds
        one quantity: `w` again, 1, and the row, 1 + 1. It adds `w` times a sum of every
        operator to it, and compares with a constant. The part pays the constant 6 of the
        first test, one more for the second field the rule reads, the weight, and the nodes of
        the tape. Those are the two fields, the table's 514, and 22 for the operators: one for
        each of the five of one argument, `div` and the half power; two for `sub`, a negative
        and a sum, and for each power of 0 or below, a power and a quotient; three for the
        other fixed power, a constant, a product and an exponential, and two for the power
        that varies, which shares the logarithm; one each for `min`, `max` and `pi`. The 1 and
        the 2 and 3 they read are ends of the bands. Then the sum of every operator, the
        product, the sum with the table, and the two of the comparison: a negative and a sum."""
        table = 1 + (1 + 512 + 512) + (1 + 1)
        total = sum(weight for _, _, weight in self.WEIGHTS)
        every = ["add"] + [expression for _, expression, _ in self.WEIGHTS]
        weight = table + (1 + (1 + len(self.WEIGHTS) + total) + (1 + 2)) + (1 + 2) + 1
        nodes = 2 + (self.ENDS + 1) + 22 + 3 + 2
        self.assertConstant(6 + 1 + weight + nodes, le=[["add", ["row", "made-up/wide", {"x": "w"}], ["mul", "w", every]], ["q", "1", "m"]], rows=[self.WIDE])

    BANDS = WIDE["table"]["down"]["bands"]
    NAMING = {"id": "made-up/naming", "anchor": ANCHOR, "gives": {"name": "k", "one_of": ["a", "b"]}, "takes": WIDE["takes"],
              "table": {"down": {"by": "x", "bands": BANDS}, "cells": ["a", "b"] * 256}}
    KEYED = {"id": "made-up/keyed", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": [{"name": "k", "one_of": ["a", "b"]}],
             "table": {"down": {"by": "k"}, "unit": "m", "cells": ["1", "2"]}}
    CASES = {"id": "made-up/cases", "anchor": ANCHOR, "gives": {"name": "y", "dim": "length"}, "takes": WIDE["takes"],
             "cases": [{"when": ["and", ["le", ["q", lo.split()[0], "m"], "x"], ["lt", "x", ["q", hi.split()[0], "m"]]], "is": ["mul", "x", "2"]} for lo, hi in BANDS]}
    PICK = 1 + 512 + 2 * 1_024
    """A pick of 512 cases with two orders each: the 1,024 a pick may compare."""
    COMPARED = 1 + ENDS + 1 + 2
    """The nodes of each tape below but its expressions: `w`, the ends of the bands, the pick,
    and the negative and the sum of the comparison with 1 m, an end of a band."""

    def test_a_case_weighs_its_row_its_expressions_and_a_pick(self):
        """`w`, 1. The row that gives the name: a step for each of the 1,024 ends of its bands.
        The expression of `a`, 1 + 1 + 3, and of `b`, 1. The pick, and the constant of the
        other side. The nodes: as above, and the product of `a`, whose 2 is an end of a band."""
        self.assertConstant(6 + 1 + 1_024 + (5 + 1) + self.PICK + 1 + self.COMPARED + 1,
                            le=[["case", ["row", "made-up/naming", {"x": "w"}], {"a": ["mul", "w", "2"], "b": "w"}], ["q", "1", "m"]], rows=[self.NAMING])

    def test_a_table_whose_key_a_row_names_weighs_the_cells_of_that_row_twice(self):
        """`w` and the ends of the bands, as above. The table: 1, 2 places, 2 cells, the 512
        cells of the row that hold a name, and 512 places down times 1 across. The row that
        holds the table binds no quantity: 1. And the constant of the other side. The nodes:
        as above, since the table's cells, 1 m and 2 m, are ends of the bands."""
        self.assertConstant(6 + 1 + 1_024 + (1 + 2 + 2 + 512 + 512) + 1 + 1 + self.COMPARED,
                            le=[["row", "made-up/keyed", {"k": ["row", "made-up/naming", {"x": "w"}]}], ["q", "1", "m"]], rows=[self.NAMING, self.KEYED])

    def test_an_equation_with_cases_weighs_its_expressions_and_a_pick(self):
        """`w`, 1. Each case: two constants and a product of two, 1 + 1 + (1 + 3). The name of
        the input is no step inside the row. The pick, the row, 1 + 1, and the constant of the
        other side. The nodes: as above, and the product that every case has for its value."""
        self.assertConstant(6 + 1 + 512 * 6 + self.PICK + 2 + 1 + self.COMPARED + 1, le=[["row", "made-up/cases", {"x": "w"}], ["q", "1", "m"]], rows=[self.CASES])


if __name__ == "__main__":
    unittest.main()
