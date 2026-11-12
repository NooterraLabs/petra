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


if __name__ == "__main__":
    unittest.main()
