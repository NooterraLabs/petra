"""What a deck can say since the lifting beam asked for it (docs/deck.md): a unit of length to
a power, a condition on a key of a joined part, a rule that requires something of a key, a
key that a row picks by the size of a quantity, and what a type needs of its fields.

Each class takes one of them through what is accepted, what is refused when the deck is
read and with which finding, the cells and their states, and the reasons. Every deck here is
made up: it is no standard and its numbers mean nothing. A test reads a deck with
petra/grid.py and with the kernel and holds the two to the same refusal or the same cells.
The tests of the kernel are skipped when no kernel is built.
"""
import json
import unittest
from fractions import Fraction
from unittest import mock

import petra
from petra import export, grid, verify
from petra.lang import LolaSyntaxError, LoweringError
from petra.registry import build_registry
from petra.units import LENGTH, Dim, Quantity, UnitError, format_quantity, parse_quantity, quantity_text, readable_text
from tests.test_kernel_attacks3 import empty_card, with_rules
from tests.test_kernel_grid import ask, findings

ANCHOR = {"standard": "a deck made up for the tests", "clause": "1"}
HEAD = 'petra 0\n\ncard "made-up" {\n  owner "t@example.org"\n}\n'
SIGNED = 'signed "t@example.org" source "test"'
KERNEL = unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
INCH = Fraction(127, 5000)


def made_up(types: list, lines: list = (), rules: list = (), rows: list = ()) -> dict:
    return {"format": "petra-rules/0", "name": "made-up", "about": "Made up for the tests. It is no standard.",
            "rows": list(rows), "types": list(types), "grid": list(lines), "rules": list(rules)}


def kind(name: str, *fields: dict, **more) -> dict:
    return {"type": name, "what": f"a {name}", "fields": list(fields), **more}


def size(name: str, dim: str = "length", **more) -> dict:
    return {"name": name, "dim": dim, "what": name, **more}


def key(name: str, *names: str) -> dict:
    return {"name": name, "one_of": list(names), "what": name}


def asks(mechanism: str, of: str, **more) -> dict:
    return {"type": of, "mechanism": mechanism, "what": mechanism, "anchor": ANCHOR, **more}


def rule(name: str, of: str, mechanism: str, **body) -> dict:
    return {"id": f"made-up/{name}", "type": of, "mechanism": mechanism, "anchor": ANCHOR, "says": name, **body}


def part(of: str, name: str, **lines: str) -> str:
    return f"{of} {name} {{\n" + "".join(f"  {field} {value}\n" for field, value in lines.items()) + "}\n"


def design(*parts: str) -> str:
    return "petra 0\n\n" + "\n".join(parts)


def given(name: str, lo: str, hi: str | None = None) -> str:
    return f"given {name} in [{lo}, {hi or lo}] {SIGNED}\n"


def load(case: str, *entries: str) -> str:
    return f"\nload {case} {{\n" + "".join(f"  on {entry}\n" for entry in entries) + f"  {SIGNED}\n}}\n"


def parsed(rules: dict, text: str, card: str = HEAD):
    deck = grid.read_deck(json.dumps(rules))
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        return deck, petra.lang.parse_design(card, text, "made-up.petra", build_registry())


def cells(test: unittest.TestCase, rules: dict, text: str, card: str = HEAD) -> tuple[dict[tuple[str, str, str], str], str, dict]:
    """The state of each cell of the design by its subject, mechanism and entry, the verdict,
    and what the kernel said, after the test holds the kernel and petra/grid.py to the same
    cells in the same order and to the same verdict."""
    deck, read = parsed(rules, text, card)
    report, files = grid.check(read, deck)
    mine = [(c.subject, c.mechanism, c.entry, c.state) for c in report.cells]
    said = {"cells": [{"subject": c.subject, "mechanism": c.mechanism, "entry": c.entry, "state": c.state, "reason": c.why} for c in report.cells]}
    if verify.binary():
        said = ask(files)
        test.assertEqual(said["findings"], [])
        test.assertEqual([(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in said["cells"]], mine, "the kernel and the grid list the same cells")
        test.assertEqual(said["verdict"], report.status)
    return {key[:3]: key[3] for key in mine}, report.status, said


def reason(said: dict, mechanism: str, entry: str | None = None) -> str:
    (found,) = [c for c in said["cells"] if c["mechanism"] == mechanism and entry in (None, c["entry"])]
    return found.get("reason", "")


def ill_formed(test: unittest.TestCase, rules: dict, text: str, card: str = HEAD) -> tuple[str, str]:
    """Why petra/grid.py refuses the design and why the kernel finds it ill formed. Both must."""
    deck, read = parsed(rules, text, card)
    with test.assertRaises(grid.ComponentError) as refused:
        grid.check(read, deck)
    if not verify.binary():
        return str(refused.exception), str(refused.exception)
    said = ask(grid.bundle(read, deck))
    test.assertEqual(said["verdict"], "ILL-FORMED", str(refused.exception))
    return str(refused.exception), findings(said)


def no_deck(test: unittest.TestCase, rules: dict) -> tuple[str, str]:
    """Why petra/grid.py refuses the deck and why the kernel does. Both must, and the kernel
    for the deck and nothing else."""
    with test.assertRaises(grid.DeckError) as refused:
        grid.read_deck(json.dumps(rules))
    if not verify.binary():
        return str(refused.exception), str(refused.exception)
    said = ask(with_rules(rules, empty_card(), []))
    test.assertEqual((said["verdict"], [f["file"] for f in said["findings"]]), ("ILL-FORMED", ["rules"]), str(refused.exception))
    return str(refused.exception), said["findings"][0]["why"]


def reads(test: unittest.TestCase, rules: dict) -> None:
    """Both read the deck."""
    grid.read_deck(json.dumps(rules))
    if verify.binary():
        test.assertEqual(ask(with_rules(rules, empty_card(), []))["findings"], [])


# --- 1. a unit of length to a power ---------------------------------------------------------------------

BEAM = kind("beam", size("depth"), size("Ix", "length^4", least="1 mm^4"), size("Sx", "length^3"), size("Zx", "length^3", signed=True),
            size("count", "dimensionless", whole=True))
MODULUS = {"id": "made-up/modulus", "anchor": ANCHOR, "gives": {"name": "S", "dim": "length^3"},
           "takes": [{"name": "I", "dim": "length^4", "range": ["1 inch^4", "1000 inch^4"]}, {"name": "c", "dim": "length", "range": ["1 inch", "20 inch"]}],
           "is": ["div", "I", "c"]}
LEAST = {"id": "made-up/least", "anchor": ANCHOR, "gives": {"name": "Smin", "dim": "length^3"},
         "takes": [{"name": "I", "dim": "length^4", "range": ["1 inch^4", "1000 inch^4"]}],
         "table": {"down": {"by": "I", "bands": [["0 inch^4", "100 inch^4"], ["100 inch^4", None]], "closed": "upper"}, "unit": "inch^3", "cells": ["10", "327741.28 mm^3"]}}
SECTIONS = made_up(
    [BEAM], [asks("beam.modulus", "beam"), asks("beam.least", "beam"), asks("beam.plastic", "beam"), asks("beam.inch", "beam")],
    [rule("modulus", "beam", "beam.modulus", le=["Sx", ["row", "made-up/modulus", {"I": "Ix", "c": ["div", "depth", "2"]}]]),
     rule("least", "beam", "beam.least", le=[["row", "made-up/least", {"I": "Ix"}], "Sx"]),
     rule("plastic", "beam", "beam.plastic", le=[["mul", "count", "Sx"], "Zx"]),
     # 1 inch^4 is 25.4^4 mm^4, which is 416231.4256 mm^4, exactly: each side is at most the other.
     rule("inch-up", "beam", "beam.inch", le=[["mul", "count", ["q", "1", "inch^4"]], ["mul", "count", ["q", "416231.4256", "mm^4"]]]),
     rule("inch-down", "beam", "beam.inch", le=[["mul", "count", ["q", "416231.4256", "mm^4"]], ["mul", "count", ["q", "1", "inch^4"]]])],
    [MODULUS, LEAST])
W = dict(depth="10 inch", Ix="100 inch^4", Sx="20 inch^3", Zx="given b.Zx", count="1")
ZX = given("b.Zx", "22 inch^3", "23 inch^3")


class UnitsWithAPower(unittest.TestCase):
    def test_a_unit_of_length_to_a_power_has_the_factor_of_the_unit_to_that_power(self):
        for unit, power in (("inch", 4), ("inch", 3), ("inch", 2), ("mm", 3), ("mm", 4), ("um", 2), ("cm", 4), ("km", 2), ("ft", 3), ("m", 4)):
            with self.subTest(unit=unit, power=power):
                q = parse_quantity("3/4", f"{unit}^{power}")
                self.assertEqual((q.value.lo, q.dim), (Fraction(3, 4) * parse_quantity("1", unit).value.lo ** power, Dim(m=power)))
        self.assertEqual(parse_quantity("1", "inch^4").value.lo, INCH ** 4)

    def test_an_area_has_two_spellings_and_one_meaning(self):
        for named, powered in (("mm2", "mm^2"), ("m2", "m^2"), ("inch2", "inch^2")):
            self.assertEqual(parse_quantity("7.5", named), parse_quantity("7.5", powered))

    def test_a_power_is_two_three_or_four_and_is_written_one_way(self):
        for unit in ("inch^0", "inch^1", "inch^5", "inch^3/2", "inch^1.5", "inch^04", "inch^+4", "inch^-2", "inch^", "inch^^4", "inch^2^2", "inch^٤", "^2", "inch ^4"):
            with self.subTest(unit):
                self.assertRaises(UnitError, parse_quantity, "1", unit)

    def test_only_a_unit_of_length_takes_a_power(self):
        for unit in ("kN^2", "mm2^2", "inch2^2", "ksi^2", "s^2", "degC^2", "%^2", "1^2", "ohm/km^2", "kip_in^2", "A2s^2"):
            with self.subTest(unit):
                self.assertRaises(UnitError, parse_quantity, "1", unit)

    def test_a_quantity_prints_in_a_unit_with_a_power_and_reads_back(self):
        q = parse_quantity("100", "inch^4")
        self.assertEqual(format_quantity(q, "inch^4"), "100 inch^4")
        self.assertEqual(format_quantity(q, "mm^4"), "41623142.56 mm^4")
        self.assertEqual(readable_text(q), "4162.314256 cm^4")
        self.assertEqual(readable_text(parse_quantity("20", "inch^3")), "327.74128 cm^3")
        for text in (readable_text(q), quantity_text(q), format_quantity(q, "m^4")):
            number, unit = text.split()
            self.assertEqual(parse_quantity(number, unit), q, text)
        self.assertEqual(readable_text(parse_quantity("2", "mm^2")), "2 mm2", "an area prints as it did")

    def test_the_language_reads_a_power_in_a_design_and_in_a_card(self):
        deck, read = parsed(SECTIONS, design(part("beam", "b", **W)), HEAD + ZX)
        written = {q["field"]: q for q in export.design_file(read, "", deck=True)["quantities"]}
        self.assertEqual((written["Ix"]["dim"], Fraction(written["Ix"]["lo"])), ("m^4", 100 * INCH ** 4))
        self.assertEqual((written["Sx"]["dim"], Fraction(written["Sx"]["lo"])), ("m^3", 20 * INCH ** 3))
        (zx,) = export.card(read, export.read_inputs(read), placed=True)["inputs"]
        self.assertEqual((zx["dim"], Fraction(zx["lo"]), Fraction(zx["hi"])), ("m^3", 22 * INCH ** 3, 23 * INCH ** 3))

    def test_the_language_refuses_a_power_it_cannot_read(self):
        for value in ("100 inch^5", "100 inch^1", "100 inch^0", "100 kN^2", "100 mm2^2"):
            with self.subTest(value):
                with self.assertRaises(LoweringError):
                    parsed(SECTIONS, design(part("beam", "b", **{**W, "Ix": value})), HEAD + ZX)
        for value in ("100 inch^3/2", "100 inch^4.5", "100 inch^-4", "100 inch ^4", "100 inch^ 4", "100 inch^", "100 ^4", "100 inch^4^2", "100 inch^1234"):
            with self.subTest(value):
                with self.assertRaises(LolaSyntaxError):
                    parsed(SECTIONS, design(part("beam", "b", **{**W, "Ix": value})), HEAD + ZX)

    def test_a_power_stands_where_a_unit_does_and_nowhere_else(self):
        with self.assertRaises(LolaSyntaxError):
            parsed(SECTIONS, design(part("beam", "b^2", **W)), HEAD + ZX)
        with self.assertRaises(LolaSyntaxError):
            parsed(SECTIONS, design(part("beam", "b", **{**W, "count": "1 ^2"})), HEAD + ZX)

    def test_a_deck_reads_a_power_in_a_range_a_band_a_cell_a_least_and_a_constant(self):
        found, verdict, _ = cells(self, SECTIONS, design(part("beam", "b", **W)), HEAD + ZX)
        self.assertEqual(verdict, "PASS", found)
        self.assertEqual(found["b", "beam.modulus", "modulus"], "proved", "100 inch^4 over 5 inch is 20 inch^3")
        self.assertEqual(found["b", "beam.least", "least"], "proved", "100 inch^4 is in the band that asks 10 inch^3")
        self.assertEqual((found["b", "beam.inch", "inch-up"], found["b", "beam.inch", "inch-down"]), ("proved", "proved"), "an inch^4 is 416231.4256 mm^4")

    def test_a_value_just_past_a_band_written_with_a_power_reads_the_next_band(self):
        on = dict(W, Sx="19.999 inch^3")
        found, verdict, _ = cells(self, SECTIONS, design(part("beam", "b", **on)), HEAD + ZX)
        self.assertEqual((found["b", "beam.least", "least"], verdict), ("proved", "PASS"), "100 inch^4 is on the end of the band that asks 10 inch^3")
        found, verdict, _ = cells(self, SECTIONS, design(part("beam", "b", **{**on, "Ix": "100.001 inch^4"})), HEAD + ZX)
        self.assertEqual((found["b", "beam.least", "least"], verdict), ("refuted", "FAIL"), "over 100 inch^4 the table asks 327741.28 mm^3, which is 20 inch^3")

    def test_a_cell_with_its_own_unit_to_a_power_is_read_in_it(self):
        exact = dict(W, Ix="101 inch^4", Sx="20 inch^3", depth="10.1 inch")
        found, _, _ = cells(self, SECTIONS, design(part("beam", "b", **exact)), HEAD + ZX)
        self.assertEqual((found["b", "beam.least", "least"], found["b", "beam.modulus", "modulus"]), ("proved", "proved"), "327741.28 mm^3 is 20 inch^3, exactly")

    def test_a_design_states_a_modulus_in_any_unit_of_length_to_the_third(self):
        for sx in ("327741.28 mm^3", "327.74128 cm^3", "0.00032774128 m^3", "20 inch^3"):
            with self.subTest(sx):
                found, _, _ = cells(self, SECTIONS, design(part("beam", "b", **{**W, "Sx": sx})), HEAD + ZX)
                self.assertEqual(found["b", "beam.modulus", "modulus"], "proved")
        found, verdict, _ = cells(self, SECTIONS, design(part("beam", "b", **{**W, "Sx": "327741.29 mm^3"})), HEAD + ZX)
        self.assertEqual((found["b", "beam.modulus", "modulus"], verdict), ("refuted", "FAIL"), "a hundredth of a mm^3 over 20 inch^3")

    def test_a_unit_to_a_power_is_of_another_dimension_than_the_unit(self):
        for field, value in (("Ix", "100 inch^3"), ("Sx", "20 inch^4"), ("Sx", "20 inch^2"), ("depth", "10 inch^2"), ("Ix", "100 inch")):
            with self.subTest(field=field, value=value):
                mine, its = ill_formed(self, SECTIONS, design(part("beam", "b", **{**W, field: value})), HEAD + ZX)
                self.assertIn(f"b.{field}", mine)
                self.assertIn(f"parts.3 design b.{field}: is a ", its)

    def test_a_unit_with_a_power_is_refused_where_a_plain_number_is_asked(self):
        mine, its = ill_formed(self, SECTIONS, design(part("beam", "b", **{**W, "count": "2 mm^2"})), HEAD + ZX)
        self.assertIn("b.count is a dimensionless, not a area", mine)
        self.assertIn("parts.3 design b.count: is a area, which is not the dimension of its field", its)
        low = dict(W, Ix="0.5 mm^4")
        mine, its = ill_formed(self, SECTIONS, design(part("beam", "b", **low)), HEAD + ZX)
        self.assertIn("parts.3 design b.Ix: is under the least its field may take", its)

    def test_a_deck_refuses_a_power_it_cannot_read_wherever_a_value_stands(self):
        def swapped(old: str, new: str) -> dict:
            text = json.dumps(SECTIONS)
            self.assertIn(old, text)
            return json.loads(text.replace(old, new, 1))

        for old, new in (('"1 mm^4"', '"1 mm^5"'), ('"1 mm^4"', '"1 mm^1"'), ('"1 mm^4"', '"1 mm^0"'), ('"1 mm^4"', '"1 mm^3/2"'), ('"1 mm^4"', '"1 kN^4"'),
                         ('"1 mm^4"', '"1 mm^04"'), ('"100 inch^4", null', '"100 inch^5", null'), ('"327741.28 mm^3"', '"327741.28 mm^-3"'),
                         ('"unit": "inch^3"', '"unit": "inch^3.0"'), ('["q", "1", "inch^4"]', '["q", "1", "inch^^4"]'), ('"1 inch^4", "1000 inch^4"', '"1 inch^4", "1000 inch2^2"')):
            with self.subTest(new):
                mine, its = no_deck(self, swapped(old, new))
                self.assertIn("unit", mine)
                self.assertIn("is not a unit", its)

    def test_a_deck_holds_a_value_with_a_power_to_the_dimension_of_its_place(self):
        def swapped(old: str, new: str) -> dict:
            text = json.dumps(SECTIONS)
            self.assertIn(old, text)
            return json.loads(text.replace(old, new, 1))

        for old, new in (('"1 mm^4"', '"1 mm^3"'), ('"unit": "inch^3"', '"unit": "inch^4"'), ('"100 inch^4", null', '"100 inch^3", null'),
                         ('["q", "1", "inch^4"]', '["q", "1", "inch^3"]'), ('"1 inch^4", "1000 inch^4"', '"1 inch^4", "1000 inch^2"')):
            with self.subTest(new):
                no_deck(self, swapped(old, new))

    def test_a_number_alone_takes_no_unit_and_no_power(self):
        for number in ("2 mm^2", "2^2", "mm^2", "2 ^2"):
            with self.subTest(number):
                bad = made_up([BEAM], [asks("beam.plastic", "beam")], [rule("plastic", "beam", "beam.plastic", le=[["mul", number, "Sx"], "Zx"])])
                no_deck(self, bad)
        power = made_up([BEAM], [asks("beam.plastic", "beam")], [rule("plastic", "beam", "beam.plastic", le=[["pow", "depth", "3 mm^2"], "Zx"])])
        no_deck(self, power)
        split = made_up([BEAM], [asks("beam.plastic", "beam")], [rule("plastic", "beam", "beam.plastic", le=[["q", "2^3", "mm"], "depth"])])
        no_deck(self, split)

    def test_the_dimension_of_a_field_is_written_with_the_name_of_a_length(self):
        """A `dim` of a deck is `length^4`. `mm^4` and `inch^4` are units, and no dimension."""
        for dim in ("mm^4", "inch^4", "m^4"):
            with self.subTest(dim):
                no_deck(self, made_up([kind("beam", size("Ix", dim))]))
        reads(self, made_up([kind("beam", size("Ix", "length^4"))]))


# --- 2. a condition on a key of a joined part -----------------------------------------------------------

END = kind("end", size("t"), key("shape", "straight", "round"), key("stiff", "no", "yes"))
LINK = kind("link", size("w"), key("duty", "light", "heavy"), {"name": "ends", "type": "end", "as": ["near", "far"], "what": "its two ends"},
            loads=[{"name": "pull", "dim": "force", "least": "0 N", "what": "a pull"}])
LINKS = made_up(
    [END, LINK],
    [asks("link.round", "link"), asks("link.buckle", "link", unless={"when": ["is", "far.stiff", "yes"], "why": "a stiff far end does not buckle"}),
     asks("link.both", "link")],
    [rule("round", "link", "link.round", when=["is", "near.shape", "round"], le=["near.t", "w"]),
     rule("buckle", "link", "link.buckle", le=["far.t", "w"]),
     rule("both", "link", "link.both", when=["and", ["is", "duty", "heavy"], ["or", ["is", "near.stiff", "yes"], ["not", ["is", "far.shape", "round"]]]],
          le=["near.t", "far.t"])])
E1 = part("end", "e1", t="5 mm", shape="round", stiff="no")
E2 = part("end", "e2", t="6 mm", shape="straight", stiff="yes")


def link(ends: str = "e1 e2", duty: str = "heavy") -> str:
    return design(E1, E2, part("link", "l", w="10 mm", duty=duty, ends=ends))


def swapped(rules: dict, old: str, new: str) -> dict:
    text = json.dumps(rules)
    assert old in text, old
    return json.loads(text.replace(old, new, 1))


class AKeyOfAJoinedPart(unittest.TestCase):
    def test_a_rule_answers_when_the_part_it_joins_has_the_key_at_the_value(self):
        found, verdict, _ = cells(self, LINKS, link())
        self.assertEqual(found, {("l", "link.round", "round"): "proved", ("l", "link.buckle", ""): "not_applicable", ("l", "link.both", "both"): "proved"})
        self.assertEqual(verdict, "PASS")

    def test_each_name_of_a_join_is_one_part(self):
        """With the two ends the other way round, `near` is the straight, stiff end."""
        found, verdict, said = cells(self, LINKS, link("e2 e1"))
        self.assertEqual(found["l", "link.round", ""], "open", "the near end is straight, so the rule for a round one does not answer")
        self.assertEqual(reason(said, "link.round"), "the deck has no rule for it on a part like this one")
        self.assertEqual(found["l", "link.buckle", "buckle"], "proved", "the far end is not stiff, so the line asks")
        self.assertEqual((found["l", "link.both", "both"], verdict), ("refuted", "FAIL"), "the near end is stiff, and 6 mm is over 5 mm")

    def test_a_condition_joins_keys_of_the_part_and_of_the_parts_it_joins(self):
        light, _, _ = cells(self, LINKS, link(duty="light"))
        self.assertEqual(light["l", "link.both", ""], "open", "a light link has no rule for the line")
        soft = design(E1, part("end", "e2", t="6 mm", shape="round", stiff="yes"), part("link", "l", w="10 mm", duty="heavy", ends="e1 e2"))
        found, _, _ = cells(self, LINKS, soft)
        self.assertEqual(found["l", "link.both", ""], "open", "the near end is not stiff and the far end is round")

    def test_a_key_that_a_condition_reads_is_read(self):
        found, _, _ = cells(self, LINKS, link())
        self.assertFalse([k for k in found if k[1] == "unread"], "every key of both ends is read by a condition that holds or by an unless")
        other, _, said = cells(self, LINKS, link("e2 e1"))
        self.assertEqual([k for k in other if k[1] == "unread"], [("e2", "unread", "shape")],
                         "the rule that reads the near end's shape does not apply to this link, and nothing else reads it")
        self.assertIn("no rule of the deck reads e2.shape", reason(said, "unread", "shape"))

    def test_an_unless_reads_the_key_whether_or_not_it_holds(self):
        only = made_up([END, LINK], [asks("link.buckle", "link", unless={"when": ["is", "far.stiff", "yes"], "why": "made up"})])
        for ends in ("e1 e2", "e2 e1"):
            found, _, _ = cells(self, only, link(ends))
            far = ends.split()[1]
            self.assertNotIn((far, "unread", "stiff"), found)
            self.assertIn((ends.split()[0], "unread", "stiff"), found, "the near end's key is read by nothing")

    def test_a_join_with_no_as_is_one_part_under_the_name_of_its_field(self):
        cap = made_up([END, kind("post", size("h"), {"name": "cap", "type": "end", "what": "its cap"})], [asks("post.cap", "post")],
                      [rule("cap", "post", "post.cap", when=["is", "cap.shape", "round"], le=["cap.t", "h"])])
        found, verdict, _ = cells(self, cap, design(E1, part("post", "p", h="10 mm", cap="e1")))
        self.assertEqual((found["p", "post.cap", "cap"], verdict), ("proved", "UNKNOWN"), "the cap's stiff is read by nothing")

    def test_the_name_of_a_field_that_joins_several_parts_names_no_part(self):
        mine, its = no_deck(self, swapped(LINKS, '["is", "near.shape", "round"]', '["is", "ends.shape", "round"]'))
        self.assertIn("ends.shape", mine)
        self.assertIn("ends joins 2 parts, and a condition names one of them, near, far", its)
        mine, its = no_deck(self, swapped(LINKS, '["is", "far.stiff", "yes"]', '["is", "ends.stiff", "yes"]'))
        self.assertIn("grid link.buckle", its)

    def test_a_condition_names_a_key_that_is_there_and_one_of_its_names(self):
        for old, new in (('["is", "near.shape", "round"]', '["is", "nobody.shape", "round"]'), ('["is", "near.shape", "round"]', '["is", "near.colour", "round"]'),
                         ('["is", "near.shape", "round"]', '["is", "near.shape", "square"]'), ('["is", "near.shape", "round"]', '["is", "near.t", "round"]'),
                         ('["is", "near.shape", "round"]', '["is", "near.near.shape", "round"]'), ('["is", "near.shape", "round"]', '["is", "near.", "round"]'),
                         ('["is", "near.shape", "round"]', '["is", ".shape", "round"]'), ('["is", "near.shape", "round"]', '["is", "end.shape", "round"]'),
                         ('["is", "far.stiff", "yes"]', '["is", "far.stiff", "maybe"]'), ('["is", "far.stiff", "yes"]', '["is", "far.w", "yes"]'),
                         ('["is", "duty", "heavy"]', '["is", "near.duty", "heavy"]'), ('["is", "duty", "heavy"]', '["is", "l.duty", "heavy"]')):
            with self.subTest(new):
                no_deck(self, swapped(LINKS, old, new))

    def test_a_load_is_one_of_the_types_own(self):
        """`loaded` asks about a load on the part itself, as before: a rule reads no load of a part its part joins."""
        reads(self, swapped(LINKS, '["is", "duty", "heavy"]', '["loaded", "pull"]'))
        ended = swapped(json.loads(json.dumps(LINKS).replace('"type": "end", "what": "a end"', '"type": "end", "what": "a end", "loads": [{"name": "push", "dim": "force", "what": "a push"}]')),
                        '["is", "duty", "heavy"]', '["loaded", "near.push"]')
        no_deck(self, ended)

    def test_a_field_called_like_a_join_is_not_the_joined_part(self):
        """The link has a key of its own named `near`, as the first of the parts it joins is.
        `near` alone is the link's key, and `near.shape` the key of the part it joins."""
        twin = kind("link", size("w"), key("near", "straight", "round"), key("shape", "straight", "round"),
                    {"name": "ends", "type": "end", "as": ["near", "far"], "what": "its two ends"})
        deck = made_up([END, twin], [asks("link.own", "link"), asks("link.joined", "link"), asks("link.shape", "link")],
                       [rule("own", "link", "link.own", when=["is", "near", "round"], le=["w", "w"]),
                        rule("joined", "link", "link.joined", when=["is", "near.shape", "round"], le=["w", "w"]),
                        rule("shape", "link", "link.shape", when=["is", "shape", "round"], le=["w", "w"])])
        for own, shape, joined in (("round", "straight", "straight"), ("straight", "round", "straight"), ("straight", "straight", "round")):
            with self.subTest(own=own, shape=shape, joined=joined):
                text = design(part("end", "e1", t="5 mm", shape=joined, stiff="no"), E2, part("link", "l", w="10 mm", near=own, shape=shape, ends="e1 e2"))
                found, _, _ = cells(self, deck, text)
                self.assertEqual([found.get(("l", f"link.{m}", m)) for m in ("own", "shape", "joined")],
                                 ["proved" if x == "round" else None for x in (own, shape, joined)])
                unread = sorted(k for k in found if k[1] == "unread" and k[2] in ("near", "shape"))
                self.assertEqual(unread, sorted([("e2", "unread", "shape")] + ([] if joined == "round" else [("e1", "unread", "shape")])
                                                + ([] if own == "round" else [("l", "unread", "near")]) + ([] if shape == "round" else [("l", "unread", "shape")])))

    def test_a_design_that_joins_no_such_part_is_ill_formed_before_a_condition_is_asked(self):
        mine, its = ill_formed(self, LINKS, design(E1, part("link", "l", w="10 mm", duty="heavy", ends="e1 nobody")))
        self.assertIn("parts.5 design l.ends: names 2 different end parts of this design", its)


# --- 3. a rule that requires something of a key ---------------------------------------------------------

LUG = kind("lug", size("t"), key("bore", "machined", "cut"))
HOIST = kind("hoist", size("span"), key("category", "A", "B", "C"), key("service", "0", "1", "2", "3", "4"),
             {"name": "lugs", "type": "lug", "as": ["top", "bottom"], "what": "its two lugs"},
             loads=[{"name": "lift", "dim": "force", "least": "0 N", "what": "the lift"}])
A_ONLY_0 = rule("category-a", "hoist", "hoist.category", when=["is", "category", "A"], requires=["is", "service", "0"])
BORES = rule("bores", "hoist", "hoist.bore", requires=["and", ["is", "top.bore", "machined"], ["is", "bottom.bore", "machined"]])
HOISTS = made_up(
    [LUG, HOIST],
    [asks("hoist.category", "hoist"), asks("hoist.bore", "hoist", unless={"when": ["is", "service", "0"], "why": "the finish is asked of service classes 1 to 4"}),
     asks("hoist.span", "hoist")],
    [A_ONLY_0, BORES, rule("span", "hoist", "hoist.span", le=[["add", "top.t", "bottom.t"], "span"])])


def hoist(category: str = "A", service: str = "0", top: str = "machined", bottom: str = "machined") -> str:
    return design(part("lug", "up", t="1 inch", bore=top), part("lug", "down", t="1 inch", bore=bottom),
                  part("hoist", "h", span="10 inch", category=category, service=f'"{service}"', lugs="up down"))


class ARuleThatRequires(unittest.TestCase):
    def test_its_cell_is_proved_when_the_condition_holds(self):
        found, verdict, said = cells(self, HOISTS, hoist())
        self.assertEqual(found, {("h", "hoist.category", "category-a"): "proved", ("h", "hoist.bore", ""): "not_applicable", ("h", "hoist.span", "span"): "proved"})
        self.assertEqual((verdict, reason(said, "hoist.category")), ("PASS", ""))

    def test_its_cell_is_refuted_when_the_condition_does_not_hold_and_the_verdict_fails(self):
        found, verdict, said = cells(self, HOISTS, hoist("A", "2"))
        self.assertEqual((found["h", "hoist.category", "category-a"], verdict), ("refuted", "FAIL"))
        self.assertEqual(reason(said, "hoist.category"), "the part is not what the rule requires: service is 2")

    def test_the_reason_names_each_key_the_condition_names_with_the_name_the_part_has(self):
        found, verdict, said = cells(self, HOISTS, hoist("B", "3", "machined", "cut"))
        self.assertEqual((found["h", "hoist.bore", "bores"], verdict), ("refuted", "FAIL"))
        self.assertEqual(reason(said, "hoist.bore"), "the part is not what the rule requires: top.bore is machined, bottom.bore is cut")
        deck, read = parsed(HOISTS, hoist("B", "3", "machined", "cut"))
        report, _ = grid.check(read, deck)
        (line,) = [text for text in report.lines() if "hoist.bore" in text]
        self.assertIn("refuted", line)
        self.assertIn("bores: bores: the part is not what the rule requires: top.bore is machined, bottom.bore is cut", line)

    def test_it_has_a_when_like_any_rule(self):
        found, verdict, said = cells(self, HOISTS, hoist("B", "2"))
        self.assertEqual(found["h", "hoist.category", ""], "open", "a hoist of category B has no rule for the line")
        self.assertEqual(reason(said, "hoist.category"), "the deck has no rule for it on a part like this one")
        self.assertEqual((found["h", "hoist.bore", "bores"], verdict), ("proved", "UNKNOWN"))

    def test_it_reads_the_keys_it_names(self):
        found, _, _ = cells(self, HOISTS, hoist("A", "0"))
        self.assertEqual(sorted(k for k in found if k[1] == "unread"), [], "the rules read the category, the service class and both bores, though the line of the bores cannot arise")
        found, _, _ = cells(self, HOISTS, hoist("B", "2"))
        self.assertEqual(sorted(k for k in found if k[1] == "unread"), [("h", "unread", "category")],
                         "the rule for category A does not apply to a hoist of category B, and nothing else reads the category")
        bare = made_up([LUG, HOIST], [asks("hoist.bore", "hoist")], [rule("top", "hoist", "hoist.bore", requires=["is", "top.bore", "machined"])])
        found, _, _ = cells(self, bare, hoist())
        self.assertNotIn(("up", "unread", "bore"), found)
        self.assertIn(("down", "unread", "bore"), found, "the rule names the top lug's bore alone")

    def test_a_waiver_and_an_unless_take_its_line_as_any_other(self):
        waived = HEAD + 'waive hoist.category on h by "t@example.org" reason "made up"\n'
        found, verdict, _ = cells(self, HOISTS, hoist("A", "3"), waived)
        self.assertEqual((found["h", "hoist.category", ""], verdict), ("waived", "PASS"))

    @KERNEL
    def test_it_needs_no_hint_and_no_work_and_no_hint_changes_it(self):
        for service, state in (("0", "proved"), ("2", "refuted")):
            deck, read = parsed(HOISTS, hoist("A", service))
            files = grid.check(read, deck)[1]
            alone = ask(files, without=("proofs",))
            mine = [c for c in alone["cells"] if c["mechanism"] == "hoist.category"]
            self.assertEqual([(c["entry"], c["state"], c["claimed"]) for c in mine], [("category-a", state, None)])
            for claimed, more in (("proved", {"partition": "leaf"}), ("refuted", {"point": {}}), ("open", {"why": "x"}), ("not_applicable", {"why": "x"}), ("waived", {})):
                hints = json.loads(files["proofs"])
                hints["cells"] = [{"subject": "h", "mechanism": "hoist.category", "entry": "category-a", "state": claimed, **more}]
                said = ask({**files, "proofs": export.text(hints)})
                mine = [c for c in said["cells"] if c["mechanism"] == "hoist.category"]
                self.assertEqual([(c["state"], c["claimed"]) for c in mine], [(state, claimed)])
                self.assertEqual(said["ignored_hints"], 0, "the hint names a cell the kernel has")
        only = made_up([LUG, HOIST], [asks("hoist.category", "hoist")], [A_ONLY_0])
        deck, read = parsed(only, hoist())
        said = ask(grid.check(read, deck)[1], without=("proofs",))
        self.assertEqual((said["verdict"], said["work"], said["counts"]["proved"]), ("UNKNOWN", 0, 1), "its proof took no work, and the fields nothing reads are open")

    def test_a_design_passes_on_what_it_requires_alone(self):
        small = made_up([kind("hoist", key("category", "A", "B", "C"), key("service", "0", "1", "2", "3", "4"))], [asks("hoist.category", "hoist")],
                        [rule("category-a", "hoist", "hoist.category", requires=["or", ["not", ["is", "category", "A"]], ["is", "service", "0"]])])
        for category, service, verdict in (("A", "0", "PASS"), ("A", "1", "FAIL"), ("B", "4", "PASS"), ("C", "0", "PASS")):
            with self.subTest(category=category, service=service):
                found, said, _ = cells(self, small, design(part("hoist", "h", category=category, service=f'"{service}"')))
                self.assertEqual(said, verdict)
                self.assertEqual(found, {("h", "hoist.category", "category-a"): "proved" if verdict == "PASS" else "refuted"})

    def test_a_rule_has_an_inequality_or_a_requirement_and_not_both(self):
        le = ["span", "span"]
        for body in ({"requires": ["is", "service", "0"], "le": le}, {"requires": ["is", "service", "0"], "let": {"x": "span"}},
                     {"requires": ["is", "service", "0"], "where": [{"le": le, "why": "x"}]}, {}, {"requires": None}, {"requires": []}, {"requires": "service"},
                     {"requires": ["is", "service"]}, {"requires": ["is", "service", "5"]}, {"requires": ["is", "span", "0"]}, {"requires": ["is", "nobody.bore", "cut"]},
                     {"requires": ["is", "lugs.bore", "cut"]}, {"requires": ["loaded", "lift"]}, {"requires": ["and", ["is", "service", "0"], ["loaded", "lift"]]},
                     {"requires": ["not", ["loaded", "lift"]]}, {"requires": ["le", "span", "span"]}, {"requires": ["and"]}, {"requires": {"is": ["service", "0"]}},
                     {"requires": ["is", "service", "0"], "tape": []}):
            with self.subTest(body):
                no_deck(self, made_up([LUG, HOIST], [asks("hoist.category", "hoist")], [rule("r", "hoist", "hoist.category", **body)]))
        mine, its = no_deck(self, made_up([LUG, HOIST], [asks("hoist.category", "hoist")], [rule("r", "hoist", "hoist.category", requires=["loaded", "lift"])]))
        self.assertIn("`requires` is a condition over keys", mine)
        self.assertIn("`requires` is a condition over keys", its)

    def test_its_cell_shares_a_key_with_no_other_rules(self):
        """A requirement is entered as any rule is, under its id from after the last `/`."""
        twice = made_up([LUG, HOIST], [asks("hoist.category", "hoist")], [A_ONLY_0, rule("category-a", "hoist", "hoist.category", le=["span", "span"]) | {"id": "other/category-a"}])
        mine, its = no_deck(self, twice)
        self.assertIn("ids that end in category-a after the last /", its)
        # A rule with a range gives the cells `span` and `span/where`. A requirement whose id ends in `span/where` is entered as `where`.
        ranged = rule("span", "hoist", "hoist.span", le=["top.t", "span"], where=[{"le": ["bottom.t", "span"], "why": "made up"}])
        near = made_up([LUG, HOIST], [asks("hoist.span", "hoist")], [ranged, rule("span/where", "hoist", "hoist.span", requires=["is", "service", "0"]),
                                                                    rule("", "hoist", "hoist.span", requires=["is", "category", "A"]) | {"says": "an id that ends in /"}])
        found, verdict, _ = cells(self, near, hoist())
        self.assertEqual({k: v for k, v in found.items() if k[1] == "hoist.span"},
                         {("h", "hoist.span", "span/where"): "proved", ("h", "hoist.span", "span"): "proved", ("h", "hoist.span", "where"): "proved", ("h", "hoist.span", ""): "proved"})
        found, verdict, said = cells(self, near, hoist("B", "1"))
        self.assertEqual({k: v for k, v in found.items() if k[1] == "hoist.span"},
                         {("h", "hoist.span", "span/where"): "proved", ("h", "hoist.span", "span"): "proved", ("h", "hoist.span", "where"): "refuted", ("h", "hoist.span", ""): "refuted"})
        self.assertEqual([c.get("reason") or None for c in said["cells"] if c["mechanism"] == "hoist.span"],
                         [None, None, "the part is not what the rule requires: service is 1", "the part is not what the rule requires: category is B"])

    def test_the_acceptance_check_for_rules_tries_a_requirement_as_it_holds_or_fails(self):
        from petra import rule as rules

        task = rules.read_task({"format": "petra-rule-task/0", "name": "made-up", "about": "made up", "rows": [],
                                "types": [{**LUG, "fields": [{**LUG["fields"][0], "range": ["1 mm", "100 mm"]}, LUG["fields"][1]]},
                                          {**HOIST, "fields": [{**HOIST["fields"][0], "range": ["1 mm", "100 mm"]}, *HOIST["fields"][1:]],
                                           "loads": [{**HOIST["loads"][0], "range": ["0 N", "10 N"]}]}],
                                "asks": [asks("hoist.category", "hoist"), asks("hoist.bore", "hoist")]})
        mine = rules.Reading(task, rules.read_transcription({"rules": [A_ONLY_0, BORES]}))
        other = rules.Reading(task, rules.read_transcription({"rules": [
            rule("x", "hoist", "hoist.category", requires=["or", ["not", ["is", "category", "A"]], ["is", "service", "0"]]),
            rule("y", "hoist", "hoist.bore", requires=["not", ["or", ["is", "top.bore", "cut"], ["is", "bottom.bore", "cut"]]])]}))
        lines, _ = rules.accept(mine, None, other)
        outcome = {line.mechanism: {c.name: c.outcome for c in line.checks} for line in lines}
        self.assertEqual(outcome["hoist.bore"]["second"], "pass", "one says both are machined, and the other that neither is cut")
        self.assertEqual(outcome["hoist.category"]["second"], "fail", "one answers for category A alone, and the other for every hoist")


# --- 4. a key that a row picks by the size of a quantity ------------------------------------------------

LENGTH_RANGE = ["1 mm", "300 mm"]
CATEGORY = {"id": "made-up/category", "anchor": ANCHOR, "gives": {"name": "category", "one_of": ["B", "C", "D", "E"], "what": "the category of an attachment"},
            "takes": [{"name": "a", "dim": "length", "what": "its length", "range": LENGTH_RANGE}, {"name": "t", "dim": "length", "what": "its thickness", "range": LENGTH_RANGE}],
            "table": {"down": {"by": "a", "bands": [["10 mm", "50 mm"], ["50 mm", "100 mm"], ["100 mm", "200 mm"]], "closed": "upper"},
                      "across": {"by": "t", "bands": [["0 mm", "25 mm"], ["25 mm", None]], "closed": "upper"},
                      "cells": [["B", "B"], ["C", "D"], ["E", None]]}}
ALLOWED = {"id": "made-up/allowed", "anchor": ANCHOR, "gives": {"name": "Fsr", "dim": "stress", "what": "the allowed range of stress"},
           "takes": [{"name": "category", "one_of": ["A", "B", "C", "D", "E"], "what": "the category"}, {"name": "service", "one_of": ["1", "2"], "what": "the service class"}],
           "table": {"down": {"by": "category"}, "across": {"by": "service"}, "unit": "MPa",
                     "cells": [["160", "100"], ["125", "80"], ["90", "60"], ["70", "45"], ["50", None]]}}
SIZE = {"id": "made-up/size", "anchor": ANCHOR, "gives": {"name": "size", "one_of": ["small", "large"]},
        "takes": [{"name": "d", "dim": "length", "range": ["10 mm", "20 mm"]}], "table": {"down": {"by": "d", "at": ["10 mm", "20 mm"]}, "cells": ["small", "large"]}}
HALVE = {"id": "made-up/halve", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless"}, "takes": [{"name": "x", "dim": "length", "range": LENGTH_RANGE}],
         "is": ["div", "x", ["q", "200", "mm"]]}
NAMED = ["row", "made-up/category", {"a": "a", "t": "t"}]
WELD = kind("weld", size("a"), size("t"), size("range", "stress"), key("service", "1", "2"), key("category", "A", "B", "C", "D", "E"))
FATIGUE = rule("fatigue", "weld", "weld.fatigue", le=["range", ["row", "made-up/allowed", {"category": NAMED, "service": "service"}]])
OWN = rule("own", "weld", "weld.own", le=["range", ["row", "made-up/allowed", {"category": "category", "service": "service"}]])
FACTOR = rule("factor", "weld", "weld.factor",
              le=[["mul", "range", ["case", NAMED, {"B": "1", "C": ["div", "a", ["q", "50", "mm"]], "D": "3", "E": ["row", "made-up/halve", {"x": "a"}]}]], ["q", "400", "MPa"]])
WELDS = made_up([WELD], [asks("weld.fatigue", "weld"), asks("weld.own", "weld"), asks("weld.factor", "weld")], [FATIGUE, OWN, FACTOR], [CATEGORY, ALLOWED, SIZE, HALVE])


def weld(a: str = "30 mm", t: str = "10 mm", stress: str = "100 MPa", service: str = "1", category: str = "B") -> str:
    return design(part("weld", "w", a=a, t=t, range=stress, service=f'"{service}"', category=category))


class AKeyPickedBySize(unittest.TestCase):
    def test_a_table_is_read_at_the_name_that_the_sizes_give(self):
        """30 mm by 10 mm is category B, which allows 125 MPa in service class 1 and 80 in class 2."""
        for stress, service, state in (("125 MPa", "1", "proved"), ("125.01 MPa", "1", "refuted"), ("80 MPa", "2", "proved"), ("80.01 MPa", "2", "refuted")):
            with self.subTest(stress=stress, service=service):
                found, _, _ = cells(self, WELDS, weld(stress=stress, service=service))
                self.assertEqual(found["w", "weld.fatigue", "fatigue"], state)

    def test_each_band_is_closed_as_the_table_says(self):
        """Up to and including 50 mm is B, and over it C or D by the thickness, up to and including 25 mm."""
        for a, t, allowed in (("50 mm", "10 mm", 125), ("50.001 mm", "10 mm", 90), ("100 mm", "25 mm", 90), ("100 mm", "25.001 mm", 70), ("50 mm", "400 mm", 125),
                              ("100.001 mm", "25 mm", 50), ("200 mm", "0.001 mm", 50), ("10.001 mm", "1 mm", 125)):
            with self.subTest(a=a, t=t):
                on, _, _ = cells(self, WELDS, weld(a, t, f"{allowed} MPa"))
                over, _, _ = cells(self, WELDS, weld(a, t, f"{allowed}.001 MPa"))
                self.assertEqual((on["w", "weld.fatigue", "fatigue"], over["w", "weld.fatigue", "fatigue"]), ("proved", "refuted"))

    def test_a_value_in_no_band_leaves_the_cell_open_and_takes_no_default(self):
        for a, t in (("10 mm", "10 mm"), ("5 mm", "10 mm"), ("200.001 mm", "10 mm"), ("1000 mm", "30 mm")):
            with self.subTest(a=a, t=t):
                for stress in ("1 MPa", "1000 MPa"):
                    found, verdict, _ = cells(self, WELDS, weld(a, t, stress))
                    self.assertEqual((found["w", "weld.fatigue", "fatigue"], found["w", "weld.factor", "factor"]), ("open", "open"))
                deck, read = parsed(WELDS, weld(a, t))
                (cell,) = [c for c in grid.check(read, deck)[0].cells if c.mechanism == "weld.fatigue"]
                self.assertEqual(cell.why, "made-up/allowed gives no value at what w has: no case of the pick holds somewhere in the box")

    def test_an_empty_cell_gives_no_name(self):
        """Over 100 mm long and over 25 mm thick the table of categories has no name."""
        found, verdict, _ = cells(self, WELDS, weld("150 mm", "30 mm", "1 MPa"))
        self.assertEqual((found["w", "weld.fatigue", "fatigue"], found["w", "weld.factor", "factor"], verdict), ("open", "open", "UNKNOWN"))
        found, _, _ = cells(self, WELDS, weld("150 mm", "20 mm", "50 MPa", "2"))
        self.assertEqual(found["w", "weld.fatigue", "fatigue"], "open", "category E has no value in service class 2")

    @KERNEL
    def test_no_hint_proves_or_refutes_a_rule_outside_the_bands(self):
        deck, read = parsed(WELDS, weld("5 mm", "10 mm", "1000 MPa"))
        files = grid.check(read, deck)[1]
        for more in ({"state": "proved", "partition": "leaf"}, {"state": "refuted", "point": {"dsg:made-up.w.a": "1/200", "dsg:made-up.w.t": "1/100", "dsg:made-up.w.range": "1000000000"}}):
            hints = json.loads(files["proofs"])
            hints["cells"] = [{"subject": "w", "mechanism": "weld.fatigue", "entry": "fatigue", **more}]
            said = ask({**files, "proofs": export.text(hints)})
            (cell,) = [c for c in said["cells"] if c["mechanism"] == "weld.fatigue"]
            self.assertEqual(cell["state"], "open")
            self.assertIn("no case of the pick holds", cell["reason"])

    def test_a_range_that_reaches_into_two_bands_must_hold_in_both(self):
        card = HEAD + given("w.a", "40 mm", "60 mm")
        found, _, _ = cells(self, WELDS, weld("given w.a", stress="90 MPa"), card)
        self.assertEqual(found["w", "weld.fatigue", "fatigue"], "proved", "B allows 125 MPa and C 90")
        found, verdict, _ = cells(self, WELDS, weld("given w.a", stress="91 MPa"), card)
        self.assertEqual((found["w", "weld.fatigue", "fatigue"], verdict), ("refuted", "FAIL"), "at 60 mm it is C, which allows 90 MPa")
        out = HEAD + given("w.a", "5 mm", "60 mm")
        found, _, _ = cells(self, WELDS, weld("given w.a", stress="1 MPa"), out)
        self.assertEqual(found["w", "weld.fatigue", "fatigue"], "open", "under 10 mm the row gives no name")

    def test_a_name_from_a_row_and_a_key_of_the_part_are_kept_apart(self):
        """The part says its own key is C, and its sizes make it B. The rule that reads the
        part's key reads C, and the rule that reads the row's name reads B."""
        found, verdict, _ = cells(self, WELDS, weld(stress="100 MPa", category="C"))
        self.assertEqual((found["w", "weld.fatigue", "fatigue"], found["w", "weld.own", "own"], verdict), ("proved", "refuted", "FAIL"))
        found, _, _ = cells(self, WELDS, weld("60 mm", stress="100 MPa", category="B"))
        self.assertEqual((found["w", "weld.fatigue", "fatigue"], found["w", "weld.own", "own"]), ("refuted", "proved"))

    def test_a_case_gives_the_expression_of_the_name(self):
        """B gives 1, C the length over 50 mm, D 3 and E the length over 200 mm, and the stress times it is at most 400 MPa."""
        for a, t, most in (("30 mm", "10 mm", "400"), ("75 mm", "10 mm", "800/3"), ("75 mm", "30 mm", "400/3"), ("150 mm", "10 mm", "1600/3")):
            with self.subTest(a=a, t=t):
                top = Fraction(most)
                on, _, _ = cells(self, WELDS, weld(a, t, f"{top.numerator}/{top.denominator} MPa" if top.denominator > 1 else f"{top} MPa"))
                over, _, _ = cells(self, WELDS, weld(a, t, f"{top.numerator + 1}/{top.denominator} MPa"))
                self.assertEqual((on["w", "weld.factor", "factor"], over["w", "weld.factor", "factor"]), ("proved", "refuted"))

    def test_what_a_row_that_gives_a_name_reads_is_read(self):
        only = made_up([WELD], [asks("weld.fatigue", "weld")], [FATIGUE], [CATEGORY, ALLOWED])
        found, _, _ = cells(self, only, weld())
        self.assertEqual(sorted(k for k in found if k[1] == "unread"), [("w", "unread", "category")], "the row reads the length and the thickness, and nothing reads the part's own key")

    def test_a_table_read_at_listed_values_gives_a_name_at_them_and_nowhere_else(self):
        bolt = kind("bolt", size("d"), size("grip"))
        limit = {"id": "made-up/grip", "anchor": ANCHOR, "gives": {"name": "g", "dim": "length"}, "takes": [{"name": "size", "one_of": ["small", "large"]}],
                 "table": {"down": {"by": "size"}, "cells": ["30 mm", "60 mm"]}}
        deck = made_up([bolt], [asks("bolt.grip", "bolt")],
                       [rule("grip", "bolt", "bolt.grip", le=["grip", ["row", "made-up/grip", {"size": ["row", "made-up/size", {"d": "d"}]}]])], [SIZE, limit])
        for d, grip, state in (("10 mm", "30 mm", "proved"), ("10 mm", "31 mm", "refuted"), ("20 mm", "60 mm", "proved"), ("15 mm", "1 mm", "open"), ("20.001 mm", "1 mm", "open")):
            with self.subTest(d=d, grip=grip):
                found, _, _ = cells(self, deck, design(part("bolt", "b", d=d, grip=grip)))
                self.assertEqual(found["b", "bolt.grip", "grip"], state)

    def test_a_name_is_a_text_whatever_it_looks_like(self):
        """Names that read as a number, a unit, a value, an operator and the word null. A cell
        that is the text `null` is that name, and a cell that is null is empty."""
        odd = ["null", "2", "inch", "1 mm", "pi", "row", ""]
        naming = {**CATEGORY, "gives": {"name": "category", "one_of": odd},
                  "table": {"down": {"by": "a", "bands": [[f"{10 * k} mm", f"{10 * k + 10} mm"] for k in range(1, 9)]}, "across": {"by": "t", "bands": [["0 mm", None]]},
                            "cells": [[name] for name in odd] + [[None]]}}
        table = {**ALLOWED, "takes": [{"name": "category", "one_of": odd}, ALLOWED["takes"][1]],
                 "table": {"down": {"by": "category"}, "across": {"by": "service"}, "unit": "MPa", "cells": [[str(10 * (k + 1)), None] for k in range(len(odd))]}}
        deck = made_up([WELD], [asks("weld.fatigue", "weld")], [FATIGUE], [naming, table])
        for k, name in enumerate(odd):
            with self.subTest(name):
                on, _, _ = cells(self, deck, weld(f"{10 * k + 15} mm", stress=f"{10 * (k + 1)} MPa"))
                over, _, _ = cells(self, deck, weld(f"{10 * k + 15} mm", stress=f"{10 * (k + 1) + 1} MPa"))
                self.assertEqual((on["w", "weld.fatigue", "fatigue"], over["w", "weld.fatigue", "fatigue"]), ("proved", "refuted"))
        found, _, _ = cells(self, deck, weld("85 mm", stress="1 MPa"))
        self.assertEqual(found["w", "weld.fatigue", "fatigue"], "open", "the last cell is null, and gives no name")

    def test_a_row_gives_a_quantity_or_a_name_and_a_name_comes_from_a_table_of_names(self):
        def changed(**more) -> dict:
            return made_up([WELD], rows=[{**CATEGORY, **more}])

        def table(**more) -> dict:
            body = {**CATEGORY["table"], **more}
            return changed(table={k: v for k, v in body.items() if v is not ...})

        reads(self, changed())
        for bad in (changed(gives={"name": "category", "one_of": ["B", "C", "D", "E"], "dim": "length"}), changed(gives={"name": "category"}),
                    changed(gives={"name": "category", "one_of": []}), changed(gives={"name": "category", "one_of": ["B", "C", "D", "E", "B"]}),
                    changed(gives={"name": "category", "one_of": ["B", "C", "D", 5]}), changed(gives={"name": "category", "one_of": "BCDE"}),
                    changed(gives={"name": "category", "one_of": ["B", "C", "D"]}), changed(gives={"name": "category", "one_of": None}),
                    table(cells=[["B", "B"], ["C", "D"], ["E", "F"]]), table(cells=[["B", "B"], ["C", "D"], ["E", 5]]), table(cells=[["B", "B"], ["C", "D"], ["E", ["E"]]]),
                    table(cells=[["B", "B"], ["C", "D"]]), table(cells=[["B", "B"], ["C", "D"], ["E"]]), table(cells=["B", "C", "E"]), table(cells=[["B", "B"], ["C", "D"], ["E", "b"]]),
                    table(unit="mm"), table(rises=["a"]), table(falls=[]), table(across=...), table(down={"by": "a", "bands": [["10 kN", "50 kN"], ["50 kN", "100 kN"], ["100 kN", "200 kN"]]}),
                    table(down={"by": "a", "bands": [["10 mm", "50 mm"], ["40 mm", "100 mm"], ["100 mm", "200 mm"]]}), table(note="x"),
                    {**changed(), "rows": [{k: v for k, v in CATEGORY.items() if k != "table"} | {"is": "a"}]},
                    {**changed(), "rows": [{k: v for k, v in CATEGORY.items() if k != "table"} | {"cases": [{"is": "a"}]}]},
                    changed(jumps=[{"cases": [1, 2], "why": "x"}]),
                    changed(takes=[CATEGORY["takes"][0], {"name": "t", "one_of": ["thin", "thick"]}], table={**CATEGORY["table"], "across": {"by": "t"}})):
            with self.subTest(json.dumps(bad["rows"])[:150]):
                no_deck(self, bad)

    def test_a_name_is_read_by_a_key_or_by_a_case_and_by_nothing_else(self):
        def ruled(le: list) -> dict:
            return made_up([WELD], [asks("weld.fatigue", "weld")], [rule("fatigue", "weld", "weld.fatigue", le=le)], [CATEGORY, ALLOWED, SIZE, HALVE])

        def keyed(binding) -> dict:
            return ruled(["range", ["row", "made-up/allowed", {"category": binding, "service": "service"}]])

        def cased(key, branches) -> dict:
            return ruled([["mul", "range", ["case", key, branches]], ["q", "400", "MPa"]])

        whole = {"B": "1", "C": "2", "D": "3", "E": "4"}
        reads(self, keyed(NAMED))
        reads(self, cased(NAMED, whole))
        for bad in (ruled([NAMED, "range"]), ruled([["mul", "range", NAMED], ["q", "400", "MPa"]]), ruled(["range", ["mul", ["q", "1", "MPa"], NAMED]]),
                    keyed(["row", "made-up/halve", {"x": "a"}]), keyed(["row", "made-up/nobody", {"a": "a", "t": "t"}]), keyed(["row", "made-up/category"]),
                    keyed(["row", "made-up/category", {"a": "a"}]), keyed(["row", "made-up/category", {"a": "a", "t": "t", "u": "t"}]),
                    keyed(["row", "made-up/category", {"a": "a", "t": "range"}]), keyed(["row", "made-up/category", {"a": "a", "t": "service"}]),
                    keyed(["row", "made-up/category", ["a", "t"]]), keyed(["row", ["made-up/category"], {"a": "a", "t": "t"}]),
                    keyed(["by", NAMED, {"B": "B", "C": "C", "D": "D", "E": "E"}]), keyed(["key", NAMED]), keyed(["row", "made-up/size", {"d": "a"}]),
                    keyed(["row", "made-up/allowed", {"category": "category", "service": "service"}]),
                    cased(NAMED, {"B": "1", "C": "2", "D": "3"}), cased(NAMED, {**whole, "F": "5"}), cased(NAMED, {**whole, "E": "a"}), cased(NAMED, {}),
                    cased("category", whole), cased(["key", "B"], whole), cased(["row", "made-up/halve", {"x": "a"}], whole), cased(NAMED, ["1", "2", "3", "4"]),
                    cased(["row", "made-up/category", {"a": "a", "t": "range"}], whole), cased(NAMED, {**whole, "E": NAMED})):
            with self.subTest(json.dumps(bad["rules"][0]["le"])[:160]):
                no_deck(self, bad)
        mine, its = no_deck(self, keyed(["row", "made-up/size", {"d": "a"}]))
        self.assertIn("gives names the key lacks", mine)
        self.assertIn("gives names the key lacks", its)

    def test_a_row_takes_no_name_and_no_case(self):
        inside = {**HALVE, "is": ["case", NAMED, {"B": "1", "C": "2", "D": "3", "E": "4"}]}
        no_deck(self, made_up([WELD], rows=[CATEGORY, inside]))

    def test_the_acceptance_check_for_a_row_reads_a_table_of_names(self):
        from petra import deck as rows

        mine = rows.read(CATEGORY)
        self.assertEqual((mine.names, mine.dim, rows.value(mine, {"a": Fraction(3, 100), "t": Fraction(1, 100)})), (("B", "C", "D", "E"), None, "B"))
        other = rows.read({**CATEGORY, "gives": {"name": "cat", "one_of": ["two", "three", "four", "five"]},
                           "takes": [{**CATEGORY["takes"][0], "name": "length"}, {**CATEGORY["takes"][1], "name": "thick"}],
                           "table": {"down": {**CATEGORY["table"]["down"], "by": "length"}, "across": {**CATEGORY["table"]["across"], "by": "thick"},
                                     "cells": [["two", "two"], ["three", "four"], ["five", None]]}})
        said = {c.name: c for c in rows.accept(mine, [rows.example({"anchor": "made up", "given": {"a": "75 mm", "t": "30 mm"}, "gives": "D"}, mine)], other)}
        self.assertEqual({name: c.outcome for name, c in said.items()}, {"units": "pass", "examples": "pass", "shape": "none", "second": "pass"}, said)
        wrong = rows.read({**CATEGORY, "table": {**CATEGORY["table"], "cells": [["B", "B"], ["D", "D"], ["E", None]]}})
        said = {c.name: c for c in rows.accept(mine, [rows.example({"anchor": "made up", "given": {"a": "75 mm", "t": "30 mm"}, "gives": "C"}, mine)], wrong)}
        self.assertEqual((said["examples"].outcome, said["second"].outcome), ("fail", "fail"), said)
        self.assertIn("this one gives C and the other D", said["second"].detail)
        self.assertRaises(rows.RowError, rows.example, {"anchor": "made up", "given": {"a": "75 mm", "t": "30 mm"}, "gives": "F"}, mine)


# --- 5. what a type needs of its fields -----------------------------------------------------------------

PIN = kind("pin", size("d"))
FITS = {"lt": ["pin.d", "hole"], "why": "a pin passes through its hole"}
NARROW = {"lt": ["hole", "width"], "why": "a hole is narrower than its plate"}
BEYOND = {"le": [["add", ["div", "hole", "2"], "gap"], "edge"], "why": "the edge lies beyond the hole and its gap"}


def eye(*needs: dict) -> dict:
    return kind("eye", size("hole"), size("width"), size("edge"), size("gap", signed=True), {"name": "pin", "type": "pin", "what": "its pin"},
                **({"needs": list(needs)} if needs else {}))


def eyes(*needs: dict) -> dict:
    return made_up([PIN, eye(*needs)], [asks("eye.any", "eye")], [rule("any", "eye", "eye.any", le=["pin.d", "width"])])


EYES = eyes(FITS, NARROW, BEYOND)
GAP = given("e.gap", "5 mm", "10 mm")


def eyed(d: str = "20 mm", hole: str = "22 mm", width: str = "60 mm", edge: str = "30 mm") -> str:
    return design(part("pin", "p", d=d), part("eye", "e", hole=hole, width=width, edge=edge, gap="given e.gap", pin="p"))


class WhatATypeNeeds(unittest.TestCase):
    def test_a_part_that_keeps_every_need_is_checked_as_before(self):
        found, verdict, said = cells(self, EYES, eyed(), HEAD + GAP)
        self.assertEqual(found["e", "eye.any", "any"], "proved")
        self.assertEqual(sorted(k for k in found if k[1] == "unread"), [("e", "unread", "edge"), ("e", "unread", "gap"), ("e", "unread", "hole")],
                         "a need reads nothing: the fields that only a need names have no rule that checks them")
        self.assertEqual(verdict, "UNKNOWN")

    def test_a_part_that_breaks_a_need_is_no_design(self):
        mine, its = ill_formed(self, EYES, eyed(d="23 mm"), HEAD + GAP)
        said = "breaks need 1 of a eye: its left side is 23/1000 and its right side is 11/500, in SI units, and the left is to be under the right: a pin passes through its hole"
        self.assertIn("e " + said, mine)
        self.assertEqual(its, "parts.9 design e: " + said)

    def test_the_finding_names_the_part_the_need_and_the_two_values(self):
        mine, its = ill_formed(self, EYES, eyed(hole="60 mm", edge="50 mm"), HEAD + GAP)
        self.assertEqual(its, "parts.9 design e: breaks need 2 of a eye: its left side is 3/50 and its right side is 3/50, in SI units, and the left is to be under the right: "
                              "a hole is narrower than its plate")
        mine, its = ill_formed(self, EYES, eyed(edge="20.999 mm"), HEAD + GAP)
        self.assertEqual(its, "parts.9 design e: breaks need 3 of a eye: its left side reaches 21/1000 and its right side is 20999/1000000, in SI units, and the left is to be at most the right: "
                              "the edge lies beyond the hole and its gap")

    def test_a_need_is_decided_exactly_on_its_edge(self):
        """Half of 22 mm and a gap of up to 10 mm is 21 mm at most: an edge of 21 mm keeps the need, and one of 20.999 mm breaks it."""
        found, _, _ = cells(self, EYES, eyed(edge="21 mm"), HEAD + GAP)
        self.assertIn(("e", "eye.any", "any"), found)
        ill_formed(self, EYES, eyed(edge="20.999999 mm"), HEAD + GAP)
        ill_formed(self, EYES, eyed(d="22 mm"), HEAD + GAP)
        cells(self, EYES, eyed(d="21.999999 mm"), HEAD + GAP)

    def test_a_need_holds_for_every_value_a_bound_of_the_card_allows(self):
        cells(self, EYES, eyed(), HEAD + given("e.gap", "5 mm", "19 mm"))
        mine, its = ill_formed(self, EYES, eyed(), HEAD + given("e.gap", "5 mm", "19.001 mm"))
        self.assertIn("its left side reaches 30001/1000000 and its right side is 3/100", its)

    def test_sums_products_and_quotients_of_ranges_are_decided_at_their_ends(self):
        both = kind("tile", size("a", signed=True), size("b", signed=True))
        card = HEAD + given("t.a", "10 mm", "20 mm") + given("t.b", "20 mm", "30 mm")
        text = design(part("tile", "t", a="given t.a", b="given t.b"))
        for need, kept in (({"le": [["mul", "a", "b"], ["q", "600", "mm2"]]}, True), ({"lt": [["mul", "a", "b"], ["q", "600", "mm2"]]}, False),
                           ({"le": [["mul", "a", "b"], ["q", "599.999", "mm2"]]}, False), ({"le": [["div", "a", "b"], "1"]}, True), ({"lt": [["div", "a", "b"], "1"]}, False),
                           ({"le": ["1/3", ["div", "a", "b"]]}, True), ({"lt": ["1/3", ["div", "a", "b"]]}, False), ({"le": [["sub", "a", "b"], ["q", "0", "mm"]]}, True),
                           ({"le": [["sub", "b", "a"], ["q", "19.999", "mm"]]}, False), ({"le": [["neg", "b"], ["neg", "a"]]}, True),
                           ({"le": [["mul", "-2", "a"], ["mul", "-1", "b"]]}, False), ({"le": [["mul", "-2", "a"], ["mul", "-2/3", "b"]]}, True),
                           ({"le": [["div", "a", "-2"], ["div", "b", "-6"]]}, True), ({"lt": [["div", "a", "-2"], ["div", "b", "-6"]]}, False),
                           ({"le": [["div", ["mul", "a", "b"], ["q", "-6", "mm"]], ["q", "-33", "mm"]]}, True), ({"le": [["div", ["mul", "a", "b"], ["q", "-6", "mm"]], ["q", "-34", "mm"]]}, False),
                           ({"lt": [["add", "a", ["q", "1/2", "inch"]], ["add", "b", ["q", "12.7001", "mm"]]]}, True)):
            with self.subTest(need):
                deck = made_up([{**both, "needs": [{**need, "why": "made up"}]}])
                if kept:
                    cells(self, deck, text, card)
                else:
                    ill_formed(self, deck, text, card)

    def test_a_need_reaches_the_fields_of_the_parts_the_type_joins(self):
        wide = kind("pin", size("d"), size("head"))
        deck = made_up([wide, eye({"le": [["mul", "2", "pin.d"], ["sub", "width", "pin.head"]], "why": "made up"})])
        text = design(part("pin", "p", d="20 mm", head="20 mm"), part("eye", "e", hole="22 mm", width="60 mm", edge="30 mm", gap="given e.gap", pin="p"))
        cells(self, deck, text, HEAD + GAP)
        ill_formed(self, deck, text.replace("head 20 mm", "head 20.001 mm"), HEAD + GAP)

    def test_a_need_that_divides_by_a_field_never_divides_by_zero(self):
        """A quantity of a part is more than zero, and a design that breaks that is refused for it before any need is asked."""
        deck = eyes({"le": [["div", "hole", "width"], "1/2"], "why": "made up"})
        cells(self, deck, eyed(), HEAD + GAP)
        ill_formed(self, deck, eyed(hole="31 mm"), HEAD + GAP)
        for width in ("0 mm", "-5 mm"):
            mine, its = ill_formed(self, deck, eyed(width=width), HEAD + GAP)
            self.assertIn("parts.3 design e.width: is not more than zero", its)
            self.assertNotIn("parts.9", its)
            self.assertNotIn("need", mine)
        gap = eyes({"le": [["div", "hole", "gap"], "10"], "why": "made up"})
        cells(self, gap, eyed(), HEAD + given("e.gap", "2.2 mm", "5 mm"))
        mine, its = ill_formed(self, gap, eyed(), HEAD + given("e.gap", "0 mm", "5 mm"))
        self.assertIn("parts.3 design e.gap: is not more than zero", its)
        self.assertNotIn("parts.9", its)

    @KERNEL
    def test_a_range_of_a_design_written_by_hand_that_reaches_zero_is_refused_before_the_need(self):
        deck = eyes({"le": [["div", "hole", "width"], "1/2"], "why": "made up"})
        loaded, read = parsed(deck, eyed(), HEAD + GAP)
        files = grid.check(read, loaded)[1]
        body = json.loads(files["design"])
        (line,) = [ln for p in body["parts"] if p["name"] == "e" for ln in p["lines"] if ln["field"] == "width"]
        line["args"][0]["number"].update(lo="-1/100", hi="1/100")
        said = ask({**files, "design": export.text(body)})
        self.assertEqual([(f["rule"], f["item"]) for f in said["findings"]], [("parts.3", "e.width")])

    def test_a_need_is_asked_of_a_design_that_breaks_nothing_else(self):
        mine, its = ill_formed(self, EYES, eyed(d="23 mm", hole="22 kN"), HEAD + GAP)
        self.assertEqual(its, "parts.3 design e.hole: is a force, which is not the dimension of its field")

    def test_the_fields_a_need_names_are_not_read(self):
        bare = made_up([PIN, eye(FITS, NARROW, BEYOND)])
        found, verdict, _ = cells(self, bare, eyed(), HEAD + GAP)
        self.assertEqual(sorted(found), sorted([("p", "unread", "d")] + [("e", "unread", f) for f in ("hole", "width", "edge", "gap")]))
        self.assertEqual(verdict, "UNKNOWN")

    @KERNEL
    def test_deciding_the_needs_comes_off_the_work_of_the_verdict(self):
        bare = made_up([PIN, eye(FITS, NARROW, BEYOND)])
        loaded, read = parsed(bare, eyed(), HEAD + GAP)
        said = ask(grid.check(read, loaded)[1])
        self.assertTrue(0 < said["work"] < 200_000, said["work"])
        none = made_up([PIN, eye()])
        loaded, read = parsed(none, eyed(), HEAD + GAP)
        self.assertEqual(ask(grid.check(read, loaded)[1])["work"], 0)

    @KERNEL
    def test_a_need_whose_numbers_grow_past_what_the_kernel_holds_is_not_decided_and_the_design_is_refused(self):
        big = str(10 ** 3990)
        deck = made_up([kind("tile", size("a", "dimensionless"), needs=[{"le": [["mul", *[big] * 6, "a"], big], "why": "made up"}])])
        loaded, read = parsed(deck, design(part("tile", "t", a="1")))
        said = ask(grid.bundle(read, loaded))
        self.assertEqual(findings(said), "parts.9 design t: need 1 of a tile is not decided: a value has more than 65536 bits")

    def test_a_need_is_two_sides_of_one_dimension_and_a_why(self):
        reads(self, EYES)
        le = ["hole", "width"]
        for need in ({"le": le}, {"le": le, "why": ""}, {"le": le, "why": 5}, {"why": "x"}, {"le": le, "lt": le, "why": "x"}, {"ge": le, "why": "x"}, {"le": le, "why": "x", "note": "y"},
                     {"le": ["hole"], "why": "x"}, {"le": ["hole", "width", "edge"], "why": "x"}, {"le": "hole", "why": "x"}, {"le": ["hole", ["q", "5", "kN"]], "why": "x"},
                     {"le": ["hole", "5"], "why": "x"}, {"le": [["add", "hole", "1"], "width"], "why": "x"}, {"le": [["mul", "hole", "width"], "edge"], "why": "x"},
                     {"le": ["hole", "nobody"], "why": "x"}, {"le": ["hole", "pin"], "why": "x"}, {"le": ["hole", "pin.nobody"], "why": "x"}, {"le": ["hole", "p.d"], "why": "x"},
                     {"le": ["hole", "eye.width"], "why": "x"}, {"le": ["hole", "pin.d.d"], "why": "x"}, "hole <= width", ["le", "hole", "width"], None):
            with self.subTest(need):
                no_deck(self, eyes(need))
        for needs in ([], None, FITS, "x"):
            with self.subTest(needs=needs):
                no_deck(self, made_up([PIN, {**eye(), "needs": needs}]))

    def test_a_need_holds_only_what_exact_fractions_decide(self):
        for side in (["sqrt", "hole"], ["pow", "hole", "2"], ["pow", "hole", "1/2"], ["pow", "hole", "1"], ["abs", "hole"], ["min", "hole", "edge"], ["max", "hole", "edge"],
                     ["exp", ["div", "hole", "edge"]], ["ln", ["div", "hole", "edge"]], ["mul", "pi", "hole"], ["load", "pull"], ["row", "made-up/halve", {"x": "hole"}],
                     ["case", NAMED, {}], ["div", ["mul", "hole", "edge"], ["add", "gap", "gap"]], ["div", "hole", ["add", "edge", "gap"]], ["div", "hole", ["neg", "edge"]],
                     ["mul", "hole", ["div", "edge", "0"]], ["mul", "hole", ["div", "edge", ["q", "0", "mm"]]], ["mul", "hole", ["div", "edge", "0/5"]],
                     ["div", "hole", ["div", "edge", "gap"]], ["add"], ["mul"], ["neg"], ["sub", "hole"], ["div", "hole"], ["q", "5"], ["q", 5, "mm"], ["q", "5", "mm", "x"], []):
            with self.subTest(side):
                no_deck(self, eyes({"le": [side, "width"], "why": "made up"}))

    def test_a_need_names_a_field_and_each_field_once(self):
        for le in (["hole", "hole"], [["add", "hole", "hole"], "width"], [["mul", "hole", "2"], ["add", "hole", "width"]], ["pin.d", ["add", "hole", "pin.d"]],
                   [["div", "hole", "hole"], "1"], ["1", "2"], [["q", "1", "mm"], ["q", "2", "mm"]], [["mul", "2", "3"], "7"]):
            with self.subTest(le):
                no_deck(self, eyes({"le": le, "why": "made up"}))
        reads(self, eyes({"le": [["mul", "hole", "2"], ["add", "edge", "width"]], "why": "made up"}))

    def test_a_field_called_like_a_joined_part_is_not_its_field(self):
        """The eye joins a pin under the name `pin`. `pin` alone is the field that joins it,
        which is no quantity, and `pin.d` is the diameter of the pin."""
        no_deck(self, eyes({"lt": ["pin", "hole"], "why": "made up"}))
        twin = made_up([PIN, kind("eye", size("d"), size("p"), {"name": "holds", "type": "pin", "as": ["p"], "what": "its pin"},
                                  needs=[{"lt": ["p.d", "d"], "why": "the pin is under the eye's own d"}, {"lt": ["p", "d"], "why": "the eye's own p is under its d"}])])
        cells(self, twin, design(part("pin", "x", d="5 mm"), part("eye", "e", d="10 mm", p="9 mm", holds="x")))
        mine, its = ill_formed(self, twin, design(part("pin", "x", d="10 mm"), part("eye", "e", d="10 mm", p="9 mm", holds="x")))
        self.assertIn("breaks need 1 of a eye", its)
        mine, its = ill_formed(self, twin, design(part("pin", "x", d="5 mm"), part("eye", "e", d="10 mm", p="10 mm", holds="x")))
        self.assertIn("breaks need 2 of a eye", its)

    def test_petra_kinds_says_what_a_type_needs(self):
        from petra import teach

        text = teach._deck_text(grid.read_deck(json.dumps(EYES)), ("eye",))
        self.assertIn("  a part that breaks one of these is no design:\n    a pin passes through its hole\n    a hole is narrower than its plate\n", text)


if __name__ == "__main__":
    unittest.main()
