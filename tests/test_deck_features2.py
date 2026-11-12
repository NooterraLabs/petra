"""What a deck, a card and a design can say since three more families asked for it
(docs/deck.md, docs/format.md): a key and a count that the card states, a waiver that rests
only a cell that would be open, more units, a field that a record may leave unstated, a
quantity at or under zero, and a rule that states `lt`.

Each class takes one of them through what is accepted, what is refused and with which
finding, the cells and their states, and the reasons. Every deck here is made up: it is no
standard and its numbers mean nothing. A test reads a deck with petra/grid.py and with the
kernel and holds the two to the same refusal or the same cells. The tests of the kernel are
skipped when no kernel is built.
"""
import json
import unittest
from fractions import Fraction

from petra import export, grid, verify
from petra.lang import LolaSyntaxError, LoweringError
from petra.units import CUSTOMARY, UNITS, Dim, UnitError, parse_quantity, readable_text
from tests.test_deck_features import (ANCHOR, HEAD, KERNEL, SIGNED, asks, cells, design, given, ill_formed, key, kind, load, made_up, no_deck, parsed, part,
                                      reads, reason, rule, size)
from tests.test_kernel_grid import ask, cell

INCH = Fraction(127, 5000)
LB = Fraction(45359237, 100000000)


# --- 3. more units --------------------------------------------------------------------------------------

NEW_UNITS = {
    "kW": (Fraction(1000), Dim(m=2, kg=1, s=-3)), "min": (Fraction(60), Dim(s=1)), "h": (Fraction(3600), Dim(s=1)),
    "Hz": (Fraction(1), Dim(s=-1)), "rpm": (Fraction(1, 60), Dim(s=-1)),
    "mAh": (Fraction(18, 5), Dim(s=1, A=1)), "Ah": (Fraction(3600), Dim(s=1, A=1)),
    "m/s": (Fraction(1), Dim(m=1, s=-1)), "km/h": (Fraction(5, 18), Dim(m=1, s=-1)), "knot": (Fraction(1852, 3600), Dim(m=1, s=-1)),
    "mph": (Fraction(1609344, 3600000), Dim(m=1, s=-1)), "mile": (Fraction(1609344, 1000), Dim(m=1)),
    "kg/m3": (Fraction(1), Dim(m=-3, kg=1)), "g/cm3": (Fraction(1000), Dim(m=-3, kg=1)), "N/mm": (Fraction(1000), Dim(kg=1, s=-2)),
    "lb": (LB, Dim(kg=1)), "oz": (LB / 16, Dim(kg=1)),
    "lbf_in": (LB * Fraction(980665, 100000) * INCH, Dim(m=2, kg=1, s=-2)), "lbf_ft": (LB * Fraction(980665, 100000) * 12 * INCH, Dim(m=2, kg=1, s=-2)),
}
"""Each unit read since 2026-11-11, with its factor to SI as a fraction worked out here from its definition, and its dimension."""

SAME = [(("60", "rpm"), ("1", "Hz")), (("1000", "mAh"), ("1", "Ah")), (("1", "Ah"), ("3600", "A2s")), (("3.6", "km/h"), ("1", "m/s")), (("3600", "knot"), ("1852", "m/s")),
        (("1", "mph"), ("0.44704", "m/s")), (("1", "mile"), ("5280", "ft")), (("1", "h"), ("60", "min")), (("1", "min"), ("60000", "ms")), (("16", "oz"), ("1", "lb")),
        (("1", "lb"), ("453.59237", "g")), (("1", "g/cm3"), ("1000", "kg/m3")), (("12", "lbf_in"), ("1", "lbf_ft")), (("1", "lbf_ft"), ("0.001", "kip_ft")),
        (("1", "kW"), ("1000", "W"))]
"""Pairs of values that are one quantity. `A2s` is a current squared for a time, so the third pair is of two dimensions and is refused."""

MOTOR = kind("motor", size("speed", "dimensionless/time"), size("charge", "current*time"), size("pace", "length/time"), size("run", "time"), size("h", "time"),
             size("mass", "mass"), size("density", "mass/length^3"), size("rate", "force/length"), size("torque", "moment"), size("power", "power"),
             size("reach", "length"), key("grade", "K", "L"))
MOTORS = made_up([MOTOR], [asks("motor.units", "motor")],
                 [rule(f"same-{n}-{way}", "motor", "motor.units", le=[["q", *(a if way == "up" else b)], ["q", *(b if way == "up" else a)]])
                  for n, (a, b) in enumerate(SAME) if n != 2 for way in ("up", "down")])
SPIN = dict(speed="9000 rpm", charge="2200 mAh", pace="54 km/h", run="12 min", h="2 h", mass="1.5 lb", density="1.6 g/cm3", rate="3 N/mm", torque="20 lbf_in",
            power="1.2 kW", reach="0.5 mile", grade="K")


class MoreUnits(unittest.TestCase):
    def test_each_new_unit_has_its_exact_factor_and_its_dimension(self):
        table = {**UNITS, **CUSTOMARY}
        for unit, (factor, dim) in NEW_UNITS.items():
            with self.subTest(unit):
                q = parse_quantity("1", unit)
                self.assertEqual((q.value.lo, q.dim), (factor, dim))
                self.assertEqual(table[unit], (factor, dim))
                self.assertIsInstance(table[unit][0], Fraction, "a factor is a fraction and never a float")
        self.assertEqual(parse_quantity("1", "knot").value.lo, Fraction(463, 900))
        self.assertEqual(parse_quantity("1", "mph").value.lo, Fraction(1397, 3125))
        self.assertEqual(parse_quantity("9000", "rpm").value.lo, 150, "150 turns a second")
        self.assertEqual(parse_quantity("2200", "mAh").value.lo, 7920, "7,920 ampere seconds")

    def test_no_unit_that_had_a_spelling_got_a_second_one(self):
        for unit in ("N.m", "N_m", "lbf.ft", "lbf.in", "lbf_inch", "lbs", "lbm", "hr", "hour", "minute", "sec", "RPM", "hz", "kph", "kmh", "kn", "kt", "mi", "kg/m^3",
                     "g/cc", "K", "degK", "degF", "F", "C", "kelvin", "rpm^2", "Hz^2", "m/s^2", "h^2", "mm/s", "m/min", "m/h", "ft/s", "N/m", "kN/m", "kWh", "Wh", "mAs"):
            with self.subTest(unit):
                self.assertRaises(UnitError, parse_quantity, "1", unit)
        self.assertEqual(parse_quantity("1", "mile^2"), parse_quantity("2589988.110336", "m2"), "a mile is a unit of length, so it takes a power")

    def test_a_report_still_prints_a_time_in_seconds_and_a_power_in_watts(self):
        self.assertEqual(readable_text(parse_quantity("7200", "s")), "7200 s")
        self.assertEqual(readable_text(parse_quantity("5", "kW")), "5000 W")
        self.assertEqual(readable_text(parse_quantity("9000", "rpm")), "150 Hz")
        self.assertEqual(readable_text(parse_quantity("54", "km/h")), "15 m/s")
        self.assertEqual(readable_text(parse_quantity("1.6", "g/cm3")), "1.6 g/cm3")

    def test_the_language_reads_each_new_unit_in_a_design_and_in_a_card(self):
        deck, read = parsed(MOTORS, design(part("motor", "m", **{**SPIN, "run": "given m.run"})), HEAD + given("m.run", "12 min", "0.5 h"))
        written = {q["field"]: q for q in export.design_file(read, "", deck=True)["quantities"]}
        expected = {"speed": ("s^-1", 150), "charge": ("s^1 A^1", 7920), "pace": ("m^1 s^-1", 15), "h": ("time", 7200), "mass": ("mass", Fraction(3, 2) * LB),
                    "density": ("m^-3 kg^1", 1600), "rate": ("kg^1 s^-2", 3000), "torque": ("energy", 20 * NEW_UNITS["lbf_in"][0]), "power": ("power", 1200),
                    "reach": ("length", Fraction(804672, 1000))}
        self.assertEqual({name: (q["dim"], Fraction(q["lo"])) for name, q in written.items()}, expected)
        (run,) = export.card(read, export.read_inputs(read), placed=True)["inputs"]
        self.assertEqual((run["dim"], run["lo"], run["hi"]), ("time", "720", "1800"))

    def test_pairs_of_values_that_are_one_quantity_are_one_to_the_kernel_and_to_the_grid(self):
        found, verdict, said = cells(self, MOTORS, design(part("motor", "m", **SPIN)))
        units = {k: v for k, v in found.items() if k[1] == "motor.units"}
        self.assertEqual((len(units), set(units.values())), (2 * (len(SAME) - 1), {"proved"}))
        mine, its = no_deck(self, made_up([MOTOR], [asks("motor.units", "motor")], [rule("charge", "motor", "motor.units", le=[["q", *SAME[2][0]], ["q", *SAME[2][1]]])]))
        self.assertIn("`le` compares two dimensions", its)

    def test_a_unit_is_read_whole_and_never_from_its_halves(self):
        """`m/s` beside `m` and `s`, `mAh` beside `m`, `A` and `h`, `min` beside `m` and `in`, and `h` beside a field named `h`."""
        for field, value, dim, si in (("pace", "3 m/s", "m^1 s^-1", 3), ("charge", "3 mAh", "s^1 A^1", Fraction(54, 5)), ("run", "3 min", "time", 180), ("h", "3 h", "time", 10800),
                                      ("run", "3 h", "time", 10800), ("h", "3 min", "time", 180), ("run", "3 s", "time", 3), ("reach", "3 m", "length", 3)):
            with self.subTest(field=field, value=value):
                _, read = parsed(MOTORS, design(part("motor", "m", **{**SPIN, field: value})))
                (q,) = [q for q in export.design_file(read, "", deck=True)["quantities"] if q["field"] == field]
                self.assertEqual((q["dim"], Fraction(q["lo"])), (dim, si))
        for field, value in (("pace", "3 m"), ("pace", "3 s"), ("charge", "3 A"), ("charge", "3 h"), ("charge", "3 mA"), ("run", "3 m"), ("run", "3 inch"), ("speed", "3 s")):
            with self.subTest(field=field, value=value):
                _, its = ill_formed(self, MOTORS, design(part("motor", "m", **{**SPIN, field: value})))
                self.assertIn(f"parts.3 design m.{field}: is a ", its)

    def test_a_unit_with_a_space_or_another_mark_in_it_is_no_unit(self):
        for value in ("3 m /s", "3 m/ s", "3 m / s", "3 m/2", "3 /s", "3 m//s", "3 m/s/s", "3 m.s", "3 kg/m^3"):
            with self.subTest(value):
                with self.assertRaises((LolaSyntaxError, LoweringError)):
                    parsed(MOTORS, design(part("motor", "m", **{**SPIN, "pace": value})))
        for value in ("3 m in", "3 mA h", "3 m A h"):
            with self.subTest(value):
                with self.assertRaises((LolaSyntaxError, LoweringError, grid.ComponentError)):
                    grid.check(parsed(MOTORS, design(part("motor", "m", **{**SPIN, "charge": value})))[1], grid.read_deck(json.dumps(MOTORS)))

    def test_k_is_a_name_of_a_key_and_no_unit(self):
        found, _, _ = cells(self, MOTORS, design(part("motor", "m", **SPIN)))
        self.assertIn(("m", "unread", "grade"), found)
        with self.assertRaises(LoweringError) as refused:
            parsed(MOTORS, design(part("motor", "m", **{**SPIN, "run": "5 K"})))
        self.assertIn("unknown unit 'K'", str(refused.exception))
        _, its = ill_formed(self, MOTORS, design(part("motor", "m", **{**SPIN, "grade": "5 h"})))
        self.assertIn("parts.4 design m.grade: takes one name", its)

    def test_a_deck_reads_the_units_wherever_it_reads_a_value(self):
        row = {"id": "made-up/limit", "anchor": ANCHOR, "gives": {"name": "v", "dim": "length/time"},
               "takes": [{"name": "n", "dim": "dimensionless/time", "range": ["60 rpm", "200 Hz"]}],
               "table": {"down": {"by": "n", "bands": [["0 rpm", "6000 rpm"], ["100 Hz", None]], "closed": "upper"}, "unit": "km/h", "cells": ["36", "20 m/s"]}}
        rotor = kind("rotor", size("speed", "dimensionless/time", least="60 rpm"), size("pace", "length/time"))
        deck = made_up([rotor], [asks("rotor.pace", "rotor")], [rule("pace", "rotor", "rotor.pace", le=["pace", ["row", "made-up/limit", {"n": "speed"}]])], [row])
        for speed, pace, state in (("6000 rpm", "10 m/s", "proved"), ("6000 rpm", "36.1 km/h", "refuted"), ("100.001 Hz", "72 km/h", "proved"), ("6001 rpm", "20.1 m/s", "refuted")):
            with self.subTest(speed=speed, pace=pace):
                found, _, _ = cells(self, deck, design(part("rotor", "r", speed=speed, pace=pace)))
                self.assertEqual(found["r", "rotor.pace", "pace"], state)
        _, its = ill_formed(self, deck, design(part("rotor", "r", speed="59 rpm", pace="1 m/s")))
        self.assertIn("parts.3 design r.speed: is under the least its field may take", its)
        for change in (lambda b: b["rows"][0]["table"].update(unit="km/hr"), lambda b: b["rows"][0]["takes"][0].update(range=["60 rpm", "200 hz"]),
                       lambda b: b["types"][0]["fields"][0].update(least="1 m/s"), lambda b: b["rows"][0]["table"]["down"]["bands"][0].__setitem__(1, "6000 mph")):
            body = json.loads(json.dumps(deck))
            change(body)
            no_deck(self, body)


# --- 5. a quantity at or under zero ---------------------------------------------------------------------

PACK = kind("pack", size("low", "temperature", may_be="negative"), size("high", "temperature", may_be="negative", least="-40 degC"),
            size("station", "length", may_be="negative"), size("offset", "length", may_be="zero"), size("spare", "dimensionless", whole=True, may_be="zero"),
            size("mass", "mass"), size("drift", "length", may_be="negative", signed=True), size("width", "length"),
            loads=[{"name": "air", "dim": "temperature", "what": "the air"}, {"name": "shift", "dim": "length", "may_be": "negative", "what": "a shift of either sign"},
                   {"name": "reach", "dim": "length", "what": "a reach"}],
            needs=[{"le": [["add", "station", "drift"], ["mul", "2", "width"]], "why": "made up: the station and its drift stay within two widths"},
                   {"lt": [["mul", "offset", "station"], ["mul", "width", ["q", "1", "m"]]], "why": "made up: a product of two fields that may not be positive"}])
PACKS = made_up([PACK], [asks("pack.cold", "pack"), asks("pack.span", "pack"), asks("pack.share", "pack"), asks("pack.centre", "pack")],
                [rule("cold", "pack", "pack.cold", le=["low", ["load", "air"]]),
                 rule("span", "pack", "pack.span", lt=["low", "high"]),
                 rule("share", "pack", "pack.share", le=[["div", "mass", "offset"], ["div", ["q", "10", "kg"], ["q", "1", "m"]]]),
                 rule("centre", "pack", "pack.centre", le=[["abs", ["add", "station", "drift", ["load", "shift"], ["neg", ["load", "reach"]], ["mul", "spare", "width"]]], ["q", "20", "mm"]])])
COLD = dict(low="-10 degC", high="40 degC", station="-5 mm", offset="200 mm", spare="0", mass="1 kg", drift="given p.drift", width="30 mm")
FLIGHT = load("flight", "p air in [-10 degC, 40 degC]", "p shift in [-2 mm, 2 mm]", "p reach in [0 mm, 1 mm]")


def pack(card: str = FLIGHT, drift: tuple[str, str] = ("-3 mm", "3 mm"), **lines: str) -> tuple[str, str]:
    return design(part("pack", "p", **{**COLD, **lines})), HEAD + given("p.drift", *drift) + card


class AtOrUnderZero(unittest.TestCase):
    def test_a_battery_to_ten_below_and_a_station_behind_the_datum_are_read_and_checked(self):
        found, verdict, said = cells(self, PACKS, *pack())
        self.assertEqual((found["p", "pack.cold", "cold/flight"], found["p", "pack.span", "span"], found["p", "pack.share", "share"], found["p", "pack.centre", "centre/flight"], verdict),
                         ("proved", "proved", "proved", "proved", "PASS"))
        deck, read = parsed(PACKS, *pack())
        written = {q["field"]: q for q in export.design_file(read, "", deck=True)["quantities"]}
        self.assertEqual([(written[f]["dim"], written[f]["lo"]) for f in ("low", "station", "spare")], [("temperature", "-10"), ("length", "-1/200"), ("dimensionless", "0")])
        found, _, _ = cells(self, PACKS, *pack(FLIGHT.replace("[-10 degC, 40 degC]", "[-10.001 degC, 40 degC]")))
        self.assertEqual(found["p", "pack.cold", "cold/flight"], "refuted", "the air may be colder than the pack allows")

    def test_a_range_in_fahrenheit_is_stated_in_celsius_as_exact_fractions(self):
        """25 to 150 degF is -35/9 to 590/9 degC. No unit has an offset, so the card writes the fractions."""
        fahrenheit = FLIGHT.replace("[-10 degC, 40 degC]", "[-35/9 degC, 590/9 degC]")
        deck, read = parsed(PACKS, *pack(fahrenheit, low="-4 degC"))
        air = next(i for i in export.card(read, export.read_inputs(read), placed=True)["inputs"] if i.get("field") == "air")
        self.assertEqual((Fraction(air["lo"]), Fraction(air["hi"])), ((Fraction(25) - 32) * 5 / 9, (Fraction(150) - 32) * 5 / 9))
        found, _, _ = cells(self, PACKS, *pack(fahrenheit, low="-4 degC"))
        self.assertEqual(found["p", "pack.cold", "cold/flight"], "proved")
        for unit in ("degF", "K"):
            with self.assertRaises(LoweringError):
                parsed(PACKS, *pack(low=f"14 {unit}"))

    def test_zero_and_under_it_are_refused_where_the_field_does_not_permit_them(self):
        for lines, finding in ((dict(mass="0 kg"), "parts.3 design p.mass: is not more than zero"), (dict(mass="-1 kg"), "parts.3 design p.mass: is not more than zero"),
                               (dict(width="0 mm"), "parts.3 design p.width: is not more than zero"),
                               (dict(offset="-1 mm"), "parts.3 design p.offset: is under zero, and its field may be zero and not under it"),
                               (dict(spare="-1"), "parts.3 design p.spare: is under zero"), (dict(spare="0.5"), "parts.3 design p.spare: is a count: one whole number"),
                               (dict(high="-41 degC"), "parts.3 design p.high: is under the least its field may take"),
                               (dict(low="-300 degC"), "parts.3 design p.low: a temperature is at least -5463/20, and this one goes down to -300")):
            with self.subTest(lines):
                mine, its = ill_formed(self, PACKS, *pack(**lines))
                self.assertIn(finding, its)
        mine, its = ill_formed(self, PACKS, *pack(mass="0 kg"))
        self.assertIn("types.3 design p.mass.mass", its, "a number of a field that says nothing is still held to the floor of a size")
        mine, its = ill_formed(self, PACKS, *pack(low="-300 degC"))
        self.assertNotIn("types.3", its, "a field that may be negative is held to its own floor, and to absolute zero")
        for lines in (dict(offset="0 mm", mass="0.001 g"), dict(spare="0"), dict(low="-273.15 degC", high="-40 degC"), dict(station="0 mm"), dict(station="-1 km", width="1 km")):
            with self.subTest(lines):
                cells(self, PACKS, *pack(**lines))

    def test_a_bound_of_the_card_follows_the_field_or_the_load_it_is_for(self):
        for card, drift, finding in ((FLIGHT, ("-3 mm", "3 mm"), None), (FLIGHT.replace("[-2 mm, 2 mm]", "[-9 mm, -8 mm]"), ("5 mm", "6 mm"), None),
                                     (FLIGHT.replace("[0 mm, 1 mm]", "[-1 mm, 1 mm]"), ("-3 mm", "3 mm"), "types.4 card flight.p.reach: a length is at least 0, and this one goes down to -1/1000"),
                                     (FLIGHT.replace("[-10 degC, 40 degC]", "[-274 degC, 40 degC]"), ("-3 mm", "3 mm"), "types.4 card flight.p.air: a temperature is at least -5463/20")):
            with self.subTest(card=card, drift=drift):
                if finding is None:
                    cells(self, PACKS, *pack(card, drift))
                else:
                    self.assertIn(finding, ill_formed(self, PACKS, *pack(card, drift))[1])
        text, card = pack(width="given p.width")
        mine, its = ill_formed(self, PACKS, text, card + given("p.width", "-1 mm", "30 mm"))
        self.assertIn("types.4 card p.width: a length is at least 0", its)
        self.assertIn("parts.3 design p.width: is not more than zero", its)
        cold = json.loads(json.dumps(PACKS))
        cold["types"][0]["loads"][0]["may_be"] = "negative"
        mine, its = ill_formed(self, cold, *pack(FLIGHT.replace("[-10 degC, 40 degC]", "[-274 degC, 40 degC]")))
        self.assertIn("types.4 card flight.p.air: a temperature is at least -5463/20", its, "may_be lifts a floor at zero, and absolute zero is no such floor")

    def test_a_quotient_by_a_field_at_zero_has_no_value_and_its_cell_is_open(self):
        found, verdict, said = cells(self, PACKS, *pack(offset="0 mm"))
        self.assertEqual((found["p", "pack.share", "share"], verdict), ("open", "UNKNOWN"))
        if verify.binary():
            text, card = pack(offset="0 mm")
            for hint in (dict(state="proved", partition="leaf"), dict(state="refuted", point={"dsg:made-up.p.mass": "1", "dsg:made-up.p.offset": "0"})):
                its = hinted(self, PACKS, text, card, "pack.share", "p", **hint)
                self.assertEqual(its["state"], "open")
                self.assertIn("division by an interval that contains 0", its["reason"])
        text, card = pack(offset="given p.offset")
        found, _, _ = cells(self, PACKS, text, card + given("p.offset", "0 mm", "200 mm"))
        self.assertEqual(found["p", "pack.share", "share"], "open", "the offset may be zero, so the quotient has no value all over its range")
        found, _, _ = cells(self, PACKS, *pack(offset="50 mm"))
        self.assertEqual(found["p", "pack.share", "share"], "refuted", "1 kg over 50 mm is 20 kg/m")

    def test_a_need_reads_a_field_at_or_under_zero_and_divides_by_none(self):
        mine, its = ill_formed(self, PACKS, *pack(station="58 mm"))
        self.assertIn("parts.9 design p: breaks need 1 of a pack: its left side, up to 61/1000, is not at most its right side, 3/50", its)
        mine, its = ill_formed(self, PACKS, *pack(offset="700 mm", station="100 mm", width="60 mm"))
        self.assertIn("parts.9 design p: breaks need 2 of a pack: its left side, 7/100, is not under its right side, 3/50", its)
        found, _, _ = cells(self, PACKS, *pack(offset="700 mm", station="-100 mm", width="60 mm", low="-10 degC"))
        self.assertIn(("p", "pack.span", "span"), found, "a product under zero is under the right side, and the part is a part")
        for divisor in ("offset", "station", "spare", "drift"):
            with self.subTest(divisor):
                body = json.loads(json.dumps(PACKS))
                body["types"][0]["needs"].append({"le": [["div", "mass" if divisor == "spare" else "width", divisor], ["q", "1", "kg" if divisor == "spare" else "1"]], "why": "made up"})
                mine, its = no_deck(self, body)
                self.assertIn("may be zero", its)
        body = json.loads(json.dumps(PACKS))
        body["types"][0]["needs"].append({"le": [["div", "station", "width"], "3"], "why": "made up: a quotient by a field that is more than zero"})
        cells(self, body, *pack())

    def test_a_deck_says_may_be_in_one_of_two_ways_and_agrees_with_its_least(self):
        for field in (size("x", may_be="positive"), size("x", may_be=True), size("x", may_be="Zero"), size("x", may_be=None), size("x", may_be=["zero"]), size("x", may_be=""),
                      size("x", may_be="zero", least="0 mm"), size("x", may_be="zero", least="-1 mm"), size("x", may_be="zero", least="1 mm"),
                      size("x", may_be="negative", least="0 mm"), size("x", may_be="negative", least="1 mm"), {**key("x", "a", "b"), "may_be": "zero"},
                      {"name": "x", "type": "pack", "what": "x", "may_be": "negative"}):
            with self.subTest(field):
                no_deck(self, made_up([PACK, kind("holder", field)]))
        for burden in ({"name": "f", "dim": "force", "what": "f", "may_be": "zero"}, {"name": "f", "dim": "force", "what": "f", "may_be": "negative", "least": "0 N"},
                       {"name": "f", "dim": "force", "what": "f", "may_be": "any"}):
            with self.subTest(burden):
                no_deck(self, made_up([kind("holder", size("x"), loads=[burden])]))
        reads(self, made_up([kind("holder", size("x", may_be="negative", least="-1 mm"), size("n", "dimensionless", whole=True, may_be="negative"),
                                  loads=[{"name": "f", "dim": "length", "what": "f", "may_be": "negative", "least": "-1 mm"}])]))


# --- 6. a rule that states lt ---------------------------------------------------------------------------

CRAFT = kind("craft", size("mass", "mass"), size("cap", "mass", signed=True), size("span", "length"),
             loads=[{"name": "cargo", "dim": "mass", "least": "0 g", "what": "what it carries"}])
CRAFTS = made_up([CRAFT], [asks("craft.under", "craft"), asks("craft.within", "craft"), asks("craft.capped", "craft"), asks("craft.laden", "craft"),
                           asks("craft.self", "craft"), asks("craft.ranged", "craft")],
                 [rule("under", "craft", "craft.under", lt=["mass", ["q", "250", "g"]]),
                  rule("within", "craft", "craft.within", le=["mass", ["q", "250", "g"]]),
                  rule("capped", "craft", "craft.capped", lt=["mass", "cap"]),
                  rule("laden", "craft", "craft.laden", lt=[["add", "mass", ["load", "cargo"]], ["q", "55", "lb"]]),
                  rule("self", "craft", "craft.self", lt=["span", "span"]),
                  rule("ranged", "craft", "craft.ranged", lt=[["sqrt", ["mul", "span", "span"]], ["q", "0.3", "m"]],
                       where=[{"le": ["mass", ["q", "1", "kg"]], "why": "made up: a craft of at most a kilogram"}])])


def craft(mass: str = "249 g", cap: str = "250 g", span: str = "0.5 m", cap_to: str | None = None, cargo: str | None = None) -> tuple[str, str]:
    card = HEAD + given("c.cap", cap, cap_to) + (load("flight", f"c cargo in {cargo}") if cargo else "")
    return design(part("craft", "c", mass=mass, cap="given c.cap", span=span)), card


def hinted(test: unittest.TestCase, rules: dict, text: str, card: str, mechanism: str, subject: str = "c", **hint) -> dict:
    """The kernel's cell of `mechanism` when the hints of proofs.json are this one hint alone, which claims what the caller likes."""
    deck, read = parsed(rules, text, card)
    files = grid.bundle(read, deck)
    proofs = {"format": "petra-proofs/0", "cells": [{"subject": subject, "mechanism": mechanism, "entry": mechanism.split(".")[1], **hint}]}
    said = ask({**files, "proofs": json.dumps(proofs)})
    test.assertEqual(said["findings"], [])
    return cell(said, mechanism)


class AStrictRule(unittest.TestCase):
    def test_lt_is_proved_under_the_limit_and_refuted_on_it(self):
        for mass, under, within in (("249.999 g", "proved", "proved"), ("250 g", "refuted", "proved"), ("250.001 g", "refuted", "refuted"), ("0.55 lb", "proved", "proved"),
                                    ("8.818 oz", "proved", "proved"), ("8.8185 oz", "refuted", "refuted"), ("1/4 kg", "refuted", "proved")):
            with self.subTest(mass):
                found, verdict, _ = cells(self, CRAFTS, *craft(mass))
                self.assertEqual((found["c", "craft.under", "under"], found["c", "craft.within", "within"]), (under, within))
                self.assertEqual(verdict, "FAIL", "no span is under itself")

    def test_lt_over_a_range_is_proved_only_when_the_whole_range_is_under(self):
        for lo, hi, state in (("250 g", "250 g", "proved"), ("249.001 g", "300 g", "proved"), ("249 g", "300 g", "refuted"), ("240 g", "249 g", "refuted"),
                              ("249.0001 g", "249.0001 g", "proved")):
            with self.subTest(lo=lo, hi=hi):
                found, _, _ = cells(self, CRAFTS, *craft("249 g", lo, cap_to=hi))
                self.assertEqual(found["c", "craft.capped", "capped"], state, "the cap may be anywhere in its range, and the mass is 249 g")

    def test_nothing_is_under_itself(self):
        found, _, said = cells(self, CRAFTS, *craft())
        self.assertEqual(found["c", "craft.self", "self"], "refuted")

    def test_lt_reads_a_load_in_each_case_and_follows_its_range(self):
        for cargo, state in (("[0 lb, 54 lb]", "proved"), ("[0 lb, 54.45 lb]", "proved"), ("[0 lb, 54.46 lb]", "refuted"), ("[54.5 lb, 60 lb]", "refuted")):
            with self.subTest(cargo):
                found, _, _ = cells(self, CRAFTS, *craft(cargo=cargo))
                self.assertEqual(found["c", "craft.laden", "laden/flight"], state, "249 g and the cargo, against 55 lb")
        found, _, said = cells(self, CRAFTS, *craft())
        self.assertEqual((found["c", "craft.laden", "laden"], reason(said, "craft.laden")), ("open", "the card puts no cargo on c, which the rule reads"))

    def test_lt_with_a_range_and_a_root_that_is_rounded(self):
        """The square root of 0.09 m2 is enclosed and not exact, so a span of exactly 0.3 m is neither under 0.3 m nor shown not to be."""
        for span, mass, state in (("0.299 m", "249 g", "proved"), ("0.301 m", "249 g", "refuted"), ("0.3 m", "249 g", "open"), ("0.2 m", "1.5 kg", "open")):
            with self.subTest(span=span, mass=mass):
                found, _, said = cells(self, CRAFTS, *craft(mass, cap="2 kg", span=span))
                self.assertEqual(found["c", "craft.ranged", "ranged"], state)
                self.assertEqual(("c", "craft.ranged", "ranged/where") in found, mass == "249 g")

    def test_a_rule_states_one_of_le_lt_and_requires(self):
        both = rule("both", "craft", "craft.under", le=["mass", ["q", "250", "g"]], lt=["mass", ["q", "250", "g"]])
        for body in (both, rule("none", "craft", "craft.under"), rule("req", "craft", "craft.under", lt=["mass", "cap"], requires=["is", "x", "y"]),
                     rule("three", "craft", "craft.under", lt=["mass", "cap", "cap"]), rule("one", "craft", "craft.under", lt=["mass"]),
                     rule("dims", "craft", "craft.under", lt=["mass", "span"]), rule("text", "craft", "craft.under", lt="mass"),
                     rule("where", "craft", "craft.under", lt=["mass", "cap"], where=[{"lt": ["mass", "cap"], "why": "made up"}]),
                     rule("gt", "craft", "craft.under", gt=["cap", "mass"]), rule("ge", "craft", "craft.under", ge=["cap", "mass"])):
            with self.subTest(body["id"]):
                mine, its = no_deck(self, made_up([CRAFT], [asks("craft.under", "craft")], [body]))
        mine, its = no_deck(self, made_up([CRAFT], [asks("craft.under", "craft")], [both]))
        self.assertIn("a rule has one of `le`", its)
        self.assertIn("a rule has one of `le`", mine)

    @KERNEL
    def test_a_hint_cannot_prove_lt_on_its_edge_or_refute_it_under_it(self):
        text, card = craft("250 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.under", state="proved", partition="leaf")["state"], "open", "250 g is not under 250 g")
        mass = {"dsg:made-up.c.mass": "1/4"}
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.under", state="refuted", point=mass)["state"], "refuted")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.within", state="refuted", point=mass)["state"], "open", "250 g is at most 250 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.within", state="proved", partition="leaf")["state"], "proved")
        text, card = craft("249 g", "249 g", cap_to="300 g")
        label = "in:made-up.c.cap"
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="proved", partition="leaf")["state"], "open")
        split = {"input": label, "at": "1/4", "below": "leaf", "above": "leaf"}
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="proved", partition=split)["state"], "open", "the cap may be 249 g, which the mass is not under")
        mass = {"dsg:made-up.c.mass": "249/1000"}
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={**mass, label: "1/4"})["state"], "open", "249 g is under 250 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={**mass, label: "249/1000"})["state"], "refuted", "249 g is not under 249 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={**mass, label: "31/125"})["state"], "open", "the card gives no cap of 248 g")
        self.assertEqual(hinted(self, CRAFTS, text, card, "craft.capped", state="refuted", point={label: "249/1000"})["state"], "open", "the point gives the mass no value")


if __name__ == "__main__":
    unittest.main()
