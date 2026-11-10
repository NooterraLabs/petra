"""The shared form of a Companion connection example: a card and a design built from the
example's lines, the strength each check gives, and the comparison with the printed
number. The test modules subclass `Example`; this module is not a test module itself, so
the base class is not collected."""
import unittest
from decimal import Decimal

from petra.lang import parse_design
from petra.models.steel import calc
from petra.registry import build_registry

from tests.test_steel_companion import Published

REGISTRY = build_registry()

ROUNDED = 0.005
"""The Companion rounds each area to three figures before it multiplies (Agv = 2.875 in^2
prints as 2.88, so 0.60 Fy Agv as 86.4 kips, not 86.25), and an ASD value is often the
rounded Rn over Omega: printed values move by up to 1/2 % from the exact ones."""

CARD = """petra 0

card "companion-{tag}" {{
  owner "s.engineer@example.org"
}}

load reaction {{
  on c1 {field} in [0 kip, {load} kip]
  signed "s.engineer@example.org" source "Companion Example {tag}"
}}
"""

DESIGN = """petra 0

{kind} c1 {{
  basis {basis}
{body}}}
"""

BOLTS = "  bolts bolt_group.120 diameter 0.75 inch threads included\n"


class Example(Published):
    """One Companion example: `kind`, `body` (the connection's lines), the LRFD and ASD
    reactions, and the printed numbers: {(mode, check name prefix): (LRFD, ASD[, rel])}
    reproduced, and the same shape for strengths the deck bounds from below."""

    tag = ""
    kind = ""
    body = ""
    loads = ("0", "0")
    printed: dict = {}
    bounded: dict = {}
    moments: tuple[str, ...] = ()       # modes whose printed number is a moment, kip-in
    availables: dict = {}               # printed numbers that are a check's available strength, as printed
    plates = 1                          # identical plates sharing the printed number; the design models one
    field = "shear"                     # the load the reaction case applies

    def values(self, basis: str, mode: str, body: str | None = None):
        load = self.loads[0 if basis == "lrfd" else 1]
        card = CARD.format(tag=self.tag, load=load, field=self.field)
        text = DESIGN.format(kind=self.kind, basis=basis, body=body or self.body)
        d = parse_design(card, text, f"{self.tag}.petra", REGISTRY)
        return calc.values(calc.connection(d, "c1", REGISTRY), d, REGISTRY, mode, "reaction"), float(load)

    def strength(self, basis: str, mode: str, prefix: str, body: str | None = None) -> float:
        found, load = self.values(basis, mode, body)
        hits = [v for v in found if v.what.startswith(prefix) and not v.excused]
        self.assertTrue(hits, f"{self.tag}: no {mode} check starts with {prefix!r}; found {[v.what for v in found]}")
        worst = max(hits, key=lambda v: v.utilisation)
        if mode in self.moments:
            return worst.capacity * self.plates
        return load / worst.utilisation * self.plates

    def available(self, basis: str, mode: str, prefix: str) -> float:
        found, _ = self.values(basis, mode)
        hits = [v for v in found if v.what.startswith(prefix) and not v.excused]
        self.assertTrue(hits, f"{self.tag}: no {mode} check starts with {prefix!r}; found {[v.what for v in found]}")
        return min(v.capacity for v in hits) * self.plates

    def near(self, computed: float, printed: str, what: str, rel: float = ROUNDED) -> None:
        """Within one unit of the printed last digit or `rel` of the printed value."""
        digits = Decimal(printed.replace(",", ""))
        unit = float(Decimal(1).scaleb(digits.as_tuple().exponent))
        allowed = max(unit, rel * float(digits))
        self.assertLessEqual(abs(computed - float(digits)), allowed, f"{what}: computed {computed:.4f}, printed {printed}")

    def test_reproduced(self):
        for (mode, prefix), printed in self.printed.items():
            for i, basis in enumerate(("lrfd", "asd")):
                with self.subTest(mode=mode, check=prefix, basis=basis):
                    rel = printed[2] if len(printed) > 2 else ROUNDED
                    self.near(self.strength(basis, mode, prefix), printed[i], f"{self.tag} {basis} {prefix}", rel)

    def test_available(self):
        for (mode, prefix), printed in self.availables.items():
            for i, basis in enumerate(("lrfd", "asd")):
                with self.subTest(mode=mode, check=prefix, basis=basis):
                    rel = printed[2] if len(printed) > 2 else ROUNDED
                    self.near(self.available(basis, mode, prefix), printed[i], f"{self.tag} {basis} {prefix}", rel)

    def test_bounded(self):
        for (mode, prefix), printed in self.bounded.items():
            for i, basis in enumerate(("lrfd", "asd")):
                with self.subTest(mode=mode, check=prefix, basis=basis):
                    ours = self.strength(basis, mode, prefix)
                    self.assertLessEqual(ours, float(printed[i]), f"{self.tag} {basis} {prefix}: {ours:.1f} > {printed[i]}")


# --- Double angles ------------------------------------------------------------------------------
