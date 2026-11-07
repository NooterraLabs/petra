"""The steel deck's fatigue numbers: AISC 360-22 Appendix 3 and its Table A-3.1. Trusted;
each row is a premise with a tag, an owner and a source that cites its clause.

What is here, by clause:
- Section 3.1: the cycle count past which fatigue is evaluated, and the 0.66 Fy cap on the
  stress from peak cyclic loads.
- Section 3.3: the coefficients and exponents of Eqs A-3-1, A-3-2 and A-3-6.
- Section 3.4: the thread constant of Eq A-3-7, and the 20% share of the applied load that
  a pretensioned bolt's stress range may be taken as.
- Table A-3.1: Cf and FTH of the categories the deck's details fall in (B, C, E', G).

Every value was read in the published text (A360-22W-ewr.pdf), so each row is sanctioned
and owned by AISC. Rows are (constant name, value text, unit, tag, owner, source), as in
steel.FACTORS: unit "1" for a pure number, "Pa" for a stress written in ksi, "m" for a
length written in inches.
"""
from __future__ import annotations

from .model import Constant
from .steel import AISC, CHECKED, SANCTIONED, _F, rows_to_constants

TABLE = f"{AISC} Appendix 3, Section 3.3 (Eq. A-3-1) and Table A-3.1"

CATEGORIES: tuple[tuple[str, str, str, str], ...] = (
    ("b", "B", "12", "16"),
    ("c", "C", "4.4", "10"),     # Eq A-3-5's 4.4 for the root crack, C'', is C's Cf
    ("e_prime", "E'", "0.39", "2.6"),
    ("g", "G", "0.39", "7"),
)
"""(id, stress category, Cf, FTH in ksi) of the Table A-3.1 categories the deck reads:
B (Cases 2.1 and 2.2), C (Case 5.7's toe and its root, C''), E' (Case 1.3 at a radius of
3/8 in or more) and G (Case 8.5)."""

CASES = {
    "b": "Cases 2.1 and 2.2, base metal of bolted lap joints, slip-critical or pretensioned",
    "c": "Case 5.7, a pair of transverse fillet welds at a tension-loaded plate's end, crack at the toe",
    "e_prime": "Case 1.3, a reentrant corner at a cope with a radius of at least 3/8 in",
    "g": "Case 8.5, high-strength bolts in tension, on the tensile stress area",
}

FATIGUE: tuple[_F, ...] = (
    ("aisc360.app3.cycles_min", "20000", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.1: fatigue resistance is determined when the cycles of live load exceed 20,000; "
     f"{CHECKED}"),
    ("aisc360.app3.peak", "0.66", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.1: the maximum stress due to peak cyclic loads is 0.66 Fy; {CHECKED}"),
    ("aisc360.app3.a3_1", "1000", "Pa", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(a), Eq. A-3-1: FSR = 1,000 (Cf / nSR)^0.333 ksi >= FTH; {CHECKED}"),
    ("aisc360.app3.a3_1_exponent", "0.333", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(a), Eqs. A-3-1, A-3-3 and A-3-5: the exponent 0.333; {CHECKED}"),
    ("aisc360.app3.a3_2", "100", "Pa", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(b), Eq. A-3-2: FSR = 100 (1.5 / nSR)^0.167 ksi >= 8 ksi; {CHECKED}"),
    ("aisc360.app3.a3_2_cf", "1.5", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(b), Eq. A-3-2: the constant 1.5 of category F; {CHECKED}"),
    ("aisc360.app3.a3_2_exponent", "0.167", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(b), Eq. A-3-2: the exponent 0.167; {CHECKED}"),
    ("aisc360.app3.a3_2_threshold", "8", "Pa", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(b), Eq. A-3-2: category F's threshold, 8 ksi; {CHECKED}"),
    ("aisc360.app3.a3_6_intercept", "0.06", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(c)(3), Eq. A-3-6: RFIL = (0.06 + 0.72 w / tp) / tp^0.167 <= 1.0, tp in "
     f"inches; {CHECKED}"),
    ("aisc360.app3.a3_6_slope", "0.72", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(c)(3), Eq. A-3-6: the 0.72 of 0.72 w / tp; {CHECKED}"),
    ("aisc360.app3.a3_6_exponent", "0.167", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.3(c)(3), Eq. A-3-6: the exponent 0.167 of tp; {CHECKED}"),
    ("aisc360.app3.a3_7_thread", "0.9743", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.4(b), Eq. A-3-7: At = (pi / 4) (db - 0.9743 / n)^2, n threads per inch; "
     f"{CHECKED}"),
    ("aisc360.app3.s3_4_share", "0.20", "1", SANCTIONED, "AISC",
     f"{AISC} Appendix 3, Section 3.4(b): the stress range in bolts pretensioned to Table J3.1, with only steel in "
     f"the grip, may be taken as the stress on the tensile stress area from 20% of the absolute value of the applied "
     f"cyclic axial load from dead, live and other loads; "
     f"{CHECKED}"),
    *((f"aisc360.app3.cat_{key}.cf", cf, "1", SANCTIONED, "AISC",
       f"{TABLE}, stress category {name} ({CASES[key]}): Cf = {cf}; {CHECKED}") for key, name, cf, _ in CATEGORIES),
    *((f"aisc360.app3.cat_{key}.fth", fth, "Pa", SANCTIONED, "AISC",
       f"{TABLE}, stress category {name} ({CASES[key]}): threshold FTH = {fth} ksi; {CHECKED}")
      for key, name, _, fth in CATEGORIES),
)
"""Appendix 3's numbers, each read by name from petra/models/steel/fatigue.py."""


def fatigue_constants() -> list[Constant]:
    return rows_to_constants(FATIGUE)
