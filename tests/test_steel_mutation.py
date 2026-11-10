"""V5 of docs/principles.md: the steel deck's mutation test.

Each number a provision prints is a registry row the deck reads by name
(petra/registry/steel.py COEFFICIENTS, petra/registry/steel_fatigue.py FATIGUE). The twin (petra/models/steel/twin.py) carries its own
copy of each, written from the method statements, so a wrong row shows as a disagreement
between the two. Here every row is mutated twice, its value doubled and halved, and the
twin comparison of tests/test_steel_twin.py runs again on each (design, connection, mode,
load case) whose statement reads the row. A mutant is killed when the deck's governing
utilisation there no longer agrees with the twin's. Where the deck certifies a bound on a
method the twin computes in floats (test_steel_twin.BOUNDED, the weld instantaneous
center), agreeing means lying between the twin's utilisation and that times one plus the
entry's share, and a mutant is killed when it leaves that band. A validity row's number (a model's
range, which the twin does not compare) is killed instead at a pair of designs on its
boundary, one just inside and one just past it (BOUNDARIES): doubled, the one past it
comes inside; halved, the one inside goes out.

A row whose mutants survive is listed in SURVIVORS with the reason the comparison cannot
see it. The test fails on a survivor not listed, and on a listed row that is now killed
(the entry is then stale and goes)."""
from __future__ import annotations

import unittest
from dataclasses import replace
from fractions import Fraction

from petra.kernel import Interval, enclose
from petra.kernel.rules.r4_enclosure import AllNonpositive
from petra.lang import parse_design
from petra.models.steel import calc, domain, twin
from petra.models.steel.checks import GEOMETRY, Ctx
from petra.models.steel.fatigue import GENERATORS, ROWS
from petra.registry import build_registry
from petra.registry.steel import COEFFICIENTS
from petra.registry.steel_fatigue import FATIGUE
from tests.test_steel_twin import BOUNDED, _designs, _differs, _variant

FACTORS = (Fraction(2), Fraction(1, 2))


def _agrees(t: float, d: float, share: float | None) -> bool:
    """Whether the deck's utilisation d agrees with the twin's t: equal within the twin
    comparison's tolerance, or for a BOUNDED site between t and t (1 + share)."""
    if share is None:
        return not _differs(t, d)
    return t <= d <= t * (1 + share)

SURVIVORS: dict[str, str] = {
    # a boundary or floor no twin design lies near
    "aisc360.j3_8.exemption": "halved (15 %): no design's shear or tension stress lies between 15 % and 30 % of "
                              "its available stress, where J3.8 would start to apply",
    "aisc360.j10_1.end_distance": "doubled (20 tf): the one tensile force near an end lies within 10 tf",
    "aisc_manual.p15.lambda_slender": "halved (0.705): no bracket's lambda lies between 0.705 and 1.41",
    "aisc_manual.p9.cb_min": "halved (0.92): where the floor binds (short double copes) Mp governs Section F11",
    "aisc_manual.p9.k1_min": "the floor never binds within the validity rows (c <= 2 d, dc <= d/2 give k1 >= 1.65), "
                             "and doubled it matters only to a slender coped web; every top-coped web here is compact",
    "aisc_manual.t10_9.rows": "doubled (10 rows): no conventional single plate here has 6 to 10 rows, where it would "
                              "take e = a/2",
    "petra.weld_ic.a_min": "no weld bracket here has e / L between 1/16 and 1/4, where the doubled or halved switch "
                           "would change the method; tests/test_steel_groups.py reads it at e / L = 0.115",
    "petra.weld_ic.k_max": "no lapped weld bracket here has kl / L between 1 and 4, where the halved or doubled switch "
                           "would change the method (theirs are 0.30 and 0.33); tests/test_steel_groups.py reads it at "
                           "kl / L = 2.25",
    # a change smaller than the band the twin bounds the deck's weld certificate to (1 %)
    "aisc_manual.p8.ic_delta_m_offset": "doubled (4 degrees): it moves a weld line's C by at most 0.33 % for a from "
                                        "1/8 to 3 (measured)",
    "aisc_manual.p8.ic_delta_u_offset": "halved (3 degrees): it moves a weld line's C by at most 0.24 % for a from "
                                        "1/8 to 3 (measured)",
    "aisc_manual.p8.ic_delta_u_cap": "the cap binds only near theta = 0, short of each line's critical element, its end: "
                                     "doubled it moves C by nothing, halved by at most 0.073 % for a from 1/8 to 3 "
                                     "(measured)",
    # a capped or non-governing branch
    "aisc360.j3_11a.tearout_not_considered": "doubled (3.0 lc t Fu): tearout no longer governs over bearing or bolt "
                                             "shear at any design with deformation not considered",
    "aisc360.j3_11a.bearing_lsl_perpendicular": "doubled (4.0 d t Fu): bearing at the one long slot across the force "
                                                "no longer governs over bolt shear",
    "aisc360.f11.inelastic_limit": "doubled (3.8 E/Fy): no design where Mp does not cap both Eqs F11-3 and F11-4 has "
                                   "its Lb d/t^2 between 1.9 and 3.8 E/Fy (the slender double cope and the slender "
                                   "rectangular bracket lie past 3.8 E/Fy)",
    "aisc_manual.p10.extended_cb": "doubled: Eq F11-3 already exceeds Mp at the extended tabs",
    "aisc_manual.p10.fnv_divisor": "halved: tmax doubles, and the 5/8 tp weld rule governs extended_ductility at the "
                                   "extended tabs",
    # Petra's strict-boundary shift
    "petra.strict.length": "a millionth of an inch: no design sits that close to a strict boundary",
    "petra.strict.ratio": "a billionth: no design sits that close to a strict boundary",
    "petra.switch.length": "10^-15 in: no switch's margin here lies that close to zero",
}
"""Row -> which mutant survives, and why the comparison cannot see it."""


def _tab(extra: str, rows: int, pitch: str, beam: str) -> tuple[str, str]:
    return _variant("boundary", f"""
shear_tab st9 {{
  basis lrfd
  beam {beam} grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows {rows}
  pitch {pitch} inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  beam_edge 1.75 inch
  top 9 inch
  weld electrode.E70 size 0.25 inch sides 2
{extra.rstrip()}
}}""", "  on st9 shear in [0 kip, 10 kip]")


BOUNDARIES = {
    # (row, design just inside, design just past): a W16x26 is 15.7 in deep
    "aisc_manual.p9.cope_length": ("steel.cope_buckling.cope_length", _tab("  bolt_line 3 inch\n  setback 0.5 inch\n  cope top depth 1.5 inch length 31.4 inch", 2, "3", "W16x26"),
                                   _tab("  bolt_line 3 inch\n  setback 0.5 inch\n  cope top depth 1.5 inch length 31.5 inch", 2, "3", "W16x26")),
    "aisc_manual.p9.cope_depth": ("steel.cope_buckling.cope_depth", _tab("  bolt_line 3 inch\n  setback 0.5 inch\n  cope top depth 7.85 inch length 4 inch", 2, "3", "W16x26"),
                                  _tab("  bolt_line 3 inch\n  setback 0.5 inch\n  cope top depth 7.9 inch length 4 inch", 2, "3", "W16x26")),
    "aisc_manual.p10.conventional_a": ("steel.ductility.conventional_a", _tab("  bolt_line 3.5 inch", 2, "3", "W16x26"),
                                       _tab("  bolt_line 3.75 inch", 2, "3", "W16x26")),
    "aisc_manual.p10.conventional_rows": ("steel.ductility.conventional_rows", _tab("  bolt_line 3 inch", 12, "2.5", "W36x231"),
                                          _tab("  bolt_line 3 inch", 13, "2.5", "W36x231")),
}
"""A validity row's number -> (row id, a design just inside the row, one just past it), each
design as the texts (card, design)."""


def _holds(pair: tuple[str, str], registry, row: str) -> bool:
    """Whether the validity row holds over the design's box."""
    design = parse_design(*pair, "<boundary>", registry)
    conn = calc.connection(design, "st9", registry)
    ctx = Ctx(conn, design, registry, next(iter(design.loads)))
    exprs, _ = ROWS[row](ctx, GEOMETRY[conn.kind](ctx))
    statement = ctx.sb.finish(AllNonpositive(exprs))
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps}
    return all(enclose(e, box).hi <= 0 for e in exprs)


def _reads(conn, design, registry, mode: str, case: str) -> frozenset[str]:
    """The registry constants a mode's statement reads, as calc.values builds it."""
    ctx = Ctx(conn, design, registry, case)
    checks = GENERATORS[mode](ctx, GEOMETRY[conn.kind](ctx))
    flat = tuple(e for c in checks for e in (*c.demand, c.capacity, *c.guards))
    if not flat:
        return frozenset()
    statement = ctx.sb.finish(AllNonpositive(flat))
    return frozenset(h.label.removeprefix("reg:const.") for h in statement.hyps
                     if getattr(h, "label", "").startswith("reg:const."))


def _deck(conn, design, registry, mode: str, case: str) -> float:
    return max((v.utilisation for v in calc.values(conn, design, registry, mode, case) if not v.excused), default=0.0)


def _mutant(registry, name: str, factor: Fraction):
    row = registry.constants[name]
    value = row.value.lo * factor
    return replace(registry, constants={**registry.constants, name: replace(row, value=Interval(value, value))})


class EveryCoefficientMatters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = build_registry()
        cls.sites = []      # (conn, design, mode, case, twin u, share, reads)
        for label, design in _designs(cls.registry):
            for name in design.components:
                conn = calc.connection(design, name, cls.registry)
                owed = [m for m in domain.required(conn, design) if m not in twin.UNCHECKED]
                for case in design.loads:
                    mine = twin.utilisations(conn, design, cls.registry, case)
                    for mode in owed:
                        t = mine.get(mode, float("nan"))
                        share = BOUNDED.get((label, name, mode))
                        if not _agrees(t, _deck(conn, design, cls.registry, mode, case), share):
                            continue        # a known disagreement (test_steel_twin.KNOWN) kills nothing
                        cls.sites.append((conn, design, mode, case, t, share, _reads(conn, design, cls.registry, mode, case)))
        cls.killed = {}
        for name, *_ in (*COEFFICIENTS, *FATIGUE):
            reached = [s for s in cls.sites if name in s[6]]
            cls.killed[name] = [any(not _agrees(t, _deck(conn, design, _mutant(cls.registry, name, f), mode, case), share)
                                    for conn, design, mode, case, t, share, _ in reached)
                                or cls._past_a_boundary(name, f) for f in FACTORS]

    @classmethod
    def _past_a_boundary(cls, name: str, factor: Fraction) -> bool:
        if name not in BOUNDARIES:
            return False
        row, inside, past = BOUNDARIES[name]
        mutant = _mutant(cls.registry, name, factor)
        return not _holds(inside, mutant, row) or _holds(past, mutant, row)

    def test_each_boundary_pair_straddles_its_row(self):
        for name, (row, inside, past) in BOUNDARIES.items():
            with self.subTest(name):
                self.assertTrue(_holds(inside, self.registry, row))
                self.assertFalse(_holds(past, self.registry, row))

    def test_every_mutant_is_killed_or_its_row_is_a_listed_survivor(self):
        for name, killed in self.killed.items():
            if name in SURVIVORS:
                continue
            with self.subTest(name):
                self.assertEqual(killed, [True] * len(FACTORS),
                                 "a mutant of this row survives: the twin comparison cannot tell it from the row")

    def test_every_listed_survivor_still_survives(self):
        for name in SURVIVORS:
            with self.subTest(name):
                self.assertIn(name, self.killed)
                self.assertFalse(all(self.killed[name]), "every mutant of this row is now killed; drop the entry")


if __name__ == "__main__":
    unittest.main()
