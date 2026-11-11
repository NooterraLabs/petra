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


if __name__ == "__main__":
    unittest.main()
