"""The fourth hostile review of petra-verify (kernel/), one test per reproduced finding.

Each test asserts the behaviour the kernel should have, and each fails against the kernel at
5714d9c (rework), where the review was made. The tests of the kernel are skipped when no
kernel is built. The ones marked "hostile deck" pass their own deck of rules with --rules.

  1  Hostile deck. A load case that puts some of the loads a rule reads on a part, and not
     all, is checked by no cell of the rule, and the line is not left open (Grid.lean,
     `cells`, `unders`; docs/format.md, "Cells from a deck of rules", item 4). A case of
     100 N on a joint that carries 10 N gets PASS, and petra/grid.py says PASS too. The
     same card without the case that carries both loads gets UNKNOWN.
  2  Hostile deck. A load of a type that no rule reads is no cell (Grid.lean, `cells`, the
     fields nothing reads; docs/format.md, item 8, names quantities and keys alone). A card
     that puts 1 MN of it on a joint that carries 10 N gets PASS, and so does petra/grid.py.
  3  Hostile deck. Lean hashes a whole number by its last 64 bits, and a fraction by the
     hashes of its numerator and its denominator, so the numbers 1 + k 2^63 all fall in
     one bucket of a table. Writing a tape finds each constant in such a table (Deck.lean,
     `node`, `Writing.seen`), so the constants of one table of a row cost the square of
     their number to write, and none of it is counted: 30,000 of them, 0.92 MB, 23 to 33
     processor seconds for each part of the rule's type, before any proof and with work 0.
  4  No deck. The caches of ln and exp (Num.lean, `Cache`) are keyed by the numerator and
     the denominator of an end, with the same hash. 1,024 ends that share it fill the cache
     of exp, and each later exp of one of them is charged as one look while the look walks
     the 1,024 and compares numbers of 32,000 bits: 0.97 MB, PASS, 85 to 89 processor
     seconds with work 18.2 billion.
  5  Hostile deck, petra/grid.py. Python hashes a whole number n as n mod (2^61 - 1), and
     `axis` (petra/deck.py) puts the values of a table's side in a set: 30,000 values that
     share a hash, 0.90 MB, take grid.read_deck 312 processor seconds. The kernel answers the
     same files in 1.2.
"""
import json
import math
import time
import unittest
from fractions import Fraction
from unittest import mock

import petra
from petra import grid, verify
from petra.registry import build_registry
from tests.test_kernel_attacks2 import MB, halves, measured, total
from tests.test_kernel_attacks3 import ANCHOR, PROCESSOR_SECONDS, empty_card, with_card, with_rules
from tests.test_kernel_grid import ask, strips

RULES = {
    "format": "petra-rules/0", "name": "pc", "about": "made up",
    "rows": [],
    "types": [{"type": "joint", "what": "a joint", "fields": [{"name": "cap", "dim": "force", "what": "what it carries"}],
               "loads": [{"name": "V", "dim": "force", "least": "0 N", "what": "shear"},
                         {"name": "T", "dim": "force", "least": "0 N", "what": "tension"}]}],
    "grid": [{"type": "joint", "mechanism": "joint.combined", "what": "shear and tension together", "anchor": ANCHOR}],
    "rules": [{"id": "pc/sum", "type": "joint", "mechanism": "joint.combined", "anchor": ANCHOR,
               "says": "the shear and the tension together are at most what the joint carries",
               "le": [["add", ["load", "V"], ["load", "T"]], "cap"]}],
}
DESIGN = "petra 0\n\njoint p {\n  cap 10 N\n}\n"
HEAD = 'petra 0\n\ncard "pc" {\n  owner "t@example.org"\n}\n'
GRAVITY = '\nload gravity {\n  on p V in [0 N, 1 N]\n  on p T in [0 N, 1 N]\n  signed "t@example.org" source "test"\n}\n'
WIND = '\nload wind {\n  on p V in [0 N, 100 N]\n  signed "t@example.org" source "test"\n}\n'
SHEAR = dict(RULES, rules=[{"id": "pc/shear", "type": "joint", "mechanism": "joint.combined", "anchor": ANCHOR,
                            "says": "the shear is at most what the joint carries", "le": [["load", "V"], "cap"]}])
"""The deck of RULES with one rule for the line, which reads V and not T."""
TENSION = '\nload gravity {\n  on p V in [0 N, 1 N]\n  on p T in [0 N, 1000000 N]\n  signed "t@example.org" source "test"\n}\n'


def grid_status(card: str, rules: dict = RULES) -> str:
    deck = grid.read_deck(json.dumps(rules))
    with mock.patch.object(grid, "decks", lambda: (deck,)):
        parsed = petra.lang.parse_design(card, DESIGN, "pc.petra", build_registry())
        return grid.check(parsed, deck)[0].status


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Cases(unittest.TestCase):
    def test_a_case_that_puts_some_of_the_loads_a_rule_reads_on_a_part_is_checked(self):
        """Finding 1, hostile deck. The rule reads V and T of the joint, V + T <= cap, and the
        cap is 10 N. Case wind puts V of up to 100 N on it and no T. With case wind alone the
        kernel leaves the rule open, as the card puts no T on the joint. With case gravity
        beside it, which puts up to 1 N of each on the joint, the kernel makes one cell,
        sum/gravity, proves it and says PASS: work 44,824, 0.1 processor seconds, 4 KB."""
        alone = ask(strips(HEAD + WIND, DESIGN, RULES))
        self.assertEqual(alone["verdict"], "UNKNOWN", "with no T in any case the rule is left open")
        said = ask(strips(HEAD + GRAVITY + WIND, DESIGN, RULES))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]][:1], [("sum/gravity", "proved")])
        self.assertNotEqual(said["verdict"], "PASS", "case wind puts 100 N on a joint that carries 10 N, and no cell checks it")

    def test_a_load_that_no_rule_reads_is_left_open(self):
        """Finding 2, hostile deck. The one rule of the line reads V alone, V <= cap; the type
        has a load T too, and the card puts 1 MN of it on the joint. The kernel makes one cell,
        shear/gravity, proves it and says PASS: work 34,196, 0.1 processor seconds, 3 KB. A
        field nothing reads is an open cell (docs/format.md, item 8), and a load is not."""
        said = ask(strips(HEAD + TENSION, DESIGN, SHEAR))
        self.assertEqual([(c["entry"], c["state"]) for c in said["cells"]][:1], [("shear/gravity", "proved")])
        self.assertNotEqual(said["verdict"], "PASS", "the card puts 1 MN of T on the joint, and no cell reads T")


class TheGridChecksTheSameCases(unittest.TestCase):
    """petra/grid.py, the second reading, makes the cells the kernel makes, and so the same."""

    def test_the_grid_checks_a_case_that_puts_some_of_the_loads_a_rule_reads_on_a_part(self):
        """Finding 1 in petra/grid.py, `_answers`: the cases are the intersection of the
        cases of each load the rule reads."""
        self.assertEqual(grid_status(HEAD + WIND), "UNKNOWN")
        self.assertNotEqual(grid_status(HEAD + GRAVITY + WIND), "PASS", "case wind is checked by no cell")

    def test_the_grid_leaves_open_a_load_that_no_rule_reads(self):
        """Finding 2 in petra/grid.py, `_unread`: it goes through the fields of a type alone."""
        self.assertNotEqual(grid_status(HEAD + TENSION, SHEAR), "PASS", "no cell reads T")


STEP = 2 ** 63
"""Whole numbers that differ by a multiple of this have one hash in Lean."""


def colliding(n: int, parts: int) -> dict[str, str]:
    """A row whose table lists `n` values of x that share a hash, read by one rule, and
    `parts` parts of the rule's type."""
    row = {"id": "h", "anchor": ANCHOR, "gives": {"name": "y", "dim": "dimensionless", "what": "w"},
           "takes": [{"name": "x", "dim": "dimensionless", "what": "w", "range": ["1", "2"]}],
           "table": {"down": {"by": "x", "at": [str(1 + k * STEP) for k in range(n)]}, "cells": ["1"] * n}}
    kind = {"type": "t", "what": "w", "fields": [{"name": "f", "dim": "dimensionless", "what": "w"}]}
    rule = {"id": "r/x", "type": "t", "mechanism": "m", "anchor": ANCHOR, "says": "s",
            "le": [["row", "h", {"x": "f"}], "1"]}
    rules = {"format": "petra-rules/0", "name": "collide", "about": "a", "rows": [row], "types": [kind],
             "grid": [{"type": "t", "mechanism": "m", "what": "w", "anchor": ANCHOR}], "rules": [rule]}
    one = lambda i: {"name": f"p{i}", "type": "t",
                     "lines": [{"field": "f", "args": [{"number": {"dim": "dimensionless", "lo": "1", "hi": "1"}}]}]}
    return with_rules(rules, empty_card(), [one(i) for i in range(parts)])


BITS = 32_000
Q = 2 ** BITS - 1


def ends(n: int) -> list[int]:
    """The first `n` whole numbers k with no factor in common with Q: x_k = 1 + k 2^(BITS/2) / Q
    then has the denominator Q, and the numerator Q + k 2^(BITS/2), whose last 64 bits are Q's."""
    return [k for k in range(1, 8 * n) if math.gcd(k, Q) == 1][:n]


def exp_cell(entry: str, filled: int, chosen: int, exps: int, leaves: int) -> dict:
    """A proved cell whose tape makes x_k for the first `chosen` of the `filled` ends, and has
    `exps` roots -exp(x_k), going round them, over `leaves` leaves."""
    nodes = [["c", str(2 ** (BITS // 4))], ["pow", 0, 4], ["c", "-1"], ["add", [1, 2]], ["pow", 0, 2], ["div", 4, 3], ["c", "1"]]
    xs = []
    for k in ends(filled)[:chosen]:
        nodes += [["c", str(k)], ["mul", [len(nodes), 5]], ["add", [6, len(nodes) + 1]]]
        xs.append(len(nodes) - 1)
    roots = []
    for i in range(exps):
        nodes += [["exp", xs[i % len(xs)]], ["neg", len(nodes)]]
        roots.append(len(nodes) - 1)
    tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": str(leaves)}], "nodes": nodes, "roots": roots}
    return {"subject": "s", "mechanism": "m", "entry": entry, "state": "proved", "tape": tape,
            "partition": halves(0, Fraction(0), Fraction(leaves), leaves)}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Time(unittest.TestCase):
    def test_constants_that_share_a_hash_are_written_in_time(self):
        """Finding 3, hostile deck. 30,000 values of a table's `at` that are 1 + k 2^63, and two
        parts: 0.92 MB, UNKNOWN with work 0 and one open cell for each part (the table compares
        60,000 orders, over the 1,024 of one pick), 46 MB. Two parts took 49.8 and 46.8
        processor seconds on a quiet desktop and 156.5, 81.3 and 48.8 on a busy one; one part
        32.5, 23.1 and 27.9, and four parts 92.3, busy. The same table with values of the same
        length that do not share a hash took 1.2 processor seconds for three parts."""
        files = colliding(30_000, 2)
        self.assertLess(total(files), MB)
        said, seconds, _ = measured(files, timeout=600)
        self.assertEqual((said["verdict"], said["counts"]["open"], said["work"]), ("UNKNOWN", 2, 0))
        self.assertLess(seconds, PROCESSOR_SECONDS, "the tapes are written in about a processor second")

    def test_ends_that_share_a_hash_are_looked_up_in_the_caches_in_time(self):
        """Finding 4, no deck. Cell `fill` takes exp of 1,024 ends x_k = (Q + k 2^16000) / Q,
        Q = 2^32000 - 1, which share a hash, and proves, so the cache of exp is full and kept.
        Cell `hit` takes exp of x_1 30,000 times on each of 11 leaves. Each is charged as a
        look in the cache, and each look walks the 1,024 ends and compares numbers of 32,000
        bits that differ in a few bits in the middle. 0.97 MB: PASS, work 18.2 billion, 89.0,
        85.7 and 84.9 processor seconds on a quiet desktop, 76 MB. With 4 leaves, work 8.9
        billion: 34.2 quiet, 56.0 to 106.4 busy. With 4 leaves and without cell `fill`: work
        5.3 billion, 2.1 processor seconds."""
        files = with_card([exp_cell("fill", 1024, 1024, 1024, 1), exp_cell("hit", 1024, 1, 30_000, 11)])
        self.assertLess(total(files), MB)
        said, seconds, _ = measured(files, timeout=1200)
        self.assertEqual((said["verdict"], said["counts"]["proved"], said["work"] < 20 * 10 ** 9), ("PASS", 2, True))
        self.assertLess(seconds, PROCESSOR_SECONDS, "the work is 18 billion units, which take about 7 processor seconds")


class TheGridReadsInTime(unittest.TestCase):
    def test_values_that_share_a_hash_in_python_are_read_in_time(self):
        """Finding 5, hostile deck, petra/grid.py. Python hashes a whole number n as n mod
        (2^61 - 1), so the numbers 1 + k (2^61 - 1) share one, and `axis` (petra/deck.py)
        puts the values of a table's side in a set to see that each is there once. 30,000 of
        them, 0.90 MB: grid.read_deck took 312 processor seconds, where the kernel answers the
        same files in 1.2 and the values 1 + k 2^63 of finding 3 are read in 1.8. 12,000 took
        53 busy and 39.3 and 34.5 quiet; 16,000 are read here."""
        body = json.loads(colliding(16_000, 1)["rules"])
        body["rows"][0]["table"]["down"]["at"] = [str(1 + k * (2 ** 61 - 1)) for k in range(16_000)]
        started = time.process_time()
        grid.read_deck(json.dumps(body))
        self.assertLess(time.process_time() - started, PROCESSOR_SECONDS, "the values are read in about a processor second")


if __name__ == "__main__":
    unittest.main()
