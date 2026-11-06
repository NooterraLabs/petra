"""The steel deck held to docs/principles.md by structure (§4 items 2 to 5):
- D2, every builder cites its clause: each check a builder states ends with a citation that
  names a provision the traceability table maps to the check's own mode (tests/test_steel_trace.py
  holds the table to the Specification's Chapters J and K, and every mode to a provision);
- D3, every model has validity rows, or a stated reason it needs none (vocab.UNBOUNDED);
- D4, no defaults: no builder function or dataclass field has a default value, so every
  input is stated where it is used (the grammar's own feature-absent readings are one
  table, lower.ABSENT, and its unconservative ones are required attributes);
- D5, no magic numbers: a builder module's numeric literals are 0, 1 and 2 only, and every
  number a provision prints is a registry row read by name, with its clause and tag.

D5's exceptions are named here, each with its reason: the integers of geometry in the
limits.py functions GEOMETRY lists (section and line properties, pi d^2 / 4, a hexagon's
sqrt 3, plate buckling's 12 (1 - nu^2)), an integer exponent of PowInt (the equation's
tw^3), and vocab's 16-digit source-hash label, the length models/base.py gives every
model label. The 2s are halves and doubles of geometry (d/2, two weld lines, 2 lev).

The citation test reads the checks of a seeded generator sample, ten designs of each of the
11 kinds, which reaches every mode; a check no design of the sample states is not seen."""
import ast
import re
import unittest
from fractions import Fraction
from pathlib import Path

from lola.models.steel import generate as gen
from lola.models.steel import trace
from lola.models.steel.vocab import MODELS, MODES, UNBOUNDED
from lola.registry import build_registry
from lola.registry import steel as deck_rows

REGISTRY = build_registry()
STEEL = Path(__file__).resolve().parents[1] / "lola" / "models" / "steel"
BUILDERS = ("lower", "limits", "checks", "build", "vocab", "domain", "path")
"""The deck's builder modules: what turns a design into obligations. calc, twin, generate,
faults, breaker, trace and package are tooling (a report, an independent twin, the gate's
machinery) and change no verdict."""

GEOMETRY = {
    ("limits", "bolt_area"): "pi d^2 / 4",
    ("limits", "plate_net_modulus"): "a plate's net plastic modulus, t/4 (L^2 - ...)",
    ("limits", "plate_plastic_modulus"): "t L^2 / 4",
    ("limits", "plate_elastic_modulus"): "t L^2 / 6",
    ("limits", "hex_corner"): "a hexagon's corner at F / sqrt 3",
    ("limits", "polar_moment"): "a bolt pattern's polar moment, in twelfths",
    ("limits", "tee_moduli"): "a tee's moments of inertia, in twelfths",
    ("limits", "cope_elastic"): "plate buckling's 12 (1 - nu^2)",
    ("limits", "elastic_weld_line"): "a weld line's section modulus L^2 / 6",
    ("limits", "elastic_weld_c"): "a C-shaped weld's moments of inertia, in twelfths",
    ("vocab", "_source_hash"): "the 16-digit label length of models/base.py",
}
NUMBER = re.compile(r"-?\d+(\.\d+)?(/\d+)?")
ALLOWED = {0, 1, 2}


def _functions(tree: ast.AST):
    """(function name, node) for every top-level function and method, nested ones folded in."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            yield node.name, node


def _literals(module: str) -> list[tuple[int, str, str]]:
    """(line, literal, enclosing function) of each numeric literal outside 0, 1, 2 that no
    exception covers."""
    tree = ast.parse((STEEL / f"{module}.py").read_text(encoding="utf-8"))
    exponents = {id(n.args[1]) for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "PowInt" and len(n.args) == 2}
    owner: dict[int, str] = {}
    for name, fn in _functions(tree):
        for n in ast.walk(fn):
            owner.setdefault(id(n), name)
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Constant) or isinstance(n.value, bool) or id(n) in exponents:
            continue
        if isinstance(n.value, (int, float)):
            number = n.value
        elif isinstance(n.value, str) and NUMBER.fullmatch(n.value):
            number = Fraction(n.value)
        else:
            continue
        where = owner.get(id(n), "<module>")
        if number in ALLOWED or (module, where) in GEOMETRY:
            continue
        out.append((n.lineno, repr(n.value), where))
    return out
CITATION = re.compile(r"\(((?:[^()]|\([^()]*\))*)\)\s*$")
"""A check's closing parenthesis, one level of nesting allowed: "(J2.2b(b))"."""


def provisions(citation: str) -> set[str]:
    """The trace sections a citation names: "J4.2a" -> J4.2a and J4.2; "Manual Eq 10-8" ->
    Manual Part 10; "RCSC 4.1" -> RCSC 4."""
    out: set[str] = set()
    for m in re.finditer(r"\b([JK]\d+\.\d+[a-z]?|[JK]\d+)\b", citation):
        out |= {m.group(1), m.group(1).rstrip("abcdefgh")}
    out |= {f"Manual Part {n}" for n in re.findall(r"Manual (?:Part|Eqs?|Table|Figure) (\d+)", citation)}
    out |= {f"RCSC {n}" for n in re.findall(r"RCSC (\d+)", citation)}
    return out


class EveryBuilderCitesItsClause(unittest.TestCase):
    """D2: the clause a check cites is one the trace table maps to the check's mode."""

    @classmethod
    def setUpClass(cls):
        cls.checks = {(mode, v.what) for g in gen.generate(110, 3, REGISTRY)
                      for (mode, _), v in gen.checks(g.text, REGISTRY).items()}
        cls.modes_of: dict[str, set[str]] = {}
        for p in (*trace.TABLE, *trace.OTHER):
            cls.modes_of.setdefault(p.section, set()).update(p.modes)

    def test_the_sample_reaches_every_mode(self):
        self.assertEqual({mode for mode, _ in self.checks}, set(MODES))

    def test_every_check_cites_a_provision_of_its_mode(self):
        for mode, what in sorted(self.checks):
            with self.subTest(what):
                cited = CITATION.search(what)
                self.assertIsNotNone(cited, "a check ends with its clause in parentheses")
                named = provisions(cited.group(1))
                self.assertTrue(any(mode in self.modes_of.get(s, ()) for s in named),
                                f"{mode}: {sorted(named)} names no provision that maps to it")

    def test_the_citation_reader(self):
        self.assertEqual(provisions("J2.2b(b)"), {"J2.2b", "J2.2"})
        self.assertEqual(provisions("F11, Cb = 1.84, Manual Part 10"), {"Manual Part 10"})
        self.assertEqual(provisions("Manual Eqs 15-8 to 15-18"), {"Manual Part 15"})
        self.assertEqual(provisions("RCSC 4.2"), {"RCSC 4"})


class EveryModelHasValidityRowsOrSaysWhyNot(unittest.TestCase):
    """D3: a model with no row carries its reason, and a model with rows carries none."""

    def test_every_model_has_rows_or_a_reason_and_not_both(self):
        for mode, spec in MODELS.items():
            short = mode.id.removeprefix("steel.")
            with self.subTest(short):
                self.assertNotEqual(bool(spec.rows), short in UNBOUNDED)

    def test_the_reason_is_in_the_models_words(self):
        for short, reason in UNBOUNDED.items():
            with self.subTest(short):
                self.assertTrue(MODELS[MODES[short]].validity.endswith(f"Unbounded: {reason}"))

    def test_every_reason_names_a_mode(self):
        self.assertEqual(set(UNBOUNDED) - set(MODES), set())


class AbsentReadingsHoldForEveryGrade(unittest.TestCase):
    """lower.ABSENT reads an omitted `weathering` line as J3.6(a)'s spacing, which is exact
    only while no grade is weathering steel: J3.6(b)'s tighter limits are for unpainted
    weathering steel (ASTM A588, A242, A709 Grade 50W, A847 and the like). The grades below
    are not. A weathering grade added to the registry makes the omitted line unsafe for it,
    and this test asks for that decision (require the line for it, or read it as "yes")."""

    NOT_WEATHERING = {"A992", "A36", "A572_50"}

    def test_no_grade_is_weathering_steel(self):
        self.assertLessEqual(set(deck_rows.GRADES), self.NOT_WEATHERING,
                             "a new grade: if it is weathering steel, an omitted weathering line no longer means "
                             "J3.6(a) for it")


class NoDefaults(unittest.TestCase):
    """D4: every input is stated where it is used."""

    def test_no_builder_function_has_a_default_argument(self):
        for module in BUILDERS:
            tree = ast.parse((STEEL / f"{module}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                    a = node.args
                    with self.subTest(module=module, function=getattr(node, "name", "lambda"), line=node.lineno):
                        self.assertEqual(a.defaults, [])
                        self.assertTrue(all(d is None for d in a.kw_defaults))

    def test_no_builder_dataclass_field_has_a_default(self):
        for module in BUILDERS:
            tree = ast.parse((STEEL / f"{module}.py").read_text(encoding="utf-8"))
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                for field in cls.body:
                    if isinstance(field, ast.AnnAssign):
                        with self.subTest(module=module, field=f"{cls.name}.{ast.unparse(field.target)}"):
                            self.assertIsNone(field.value)


class NoMagicNumbers(unittest.TestCase):
    """D5: the numbers a provision prints are registry rows, each with its clause and tag."""

    def test_builder_modules_have_no_numeric_literal_but_0_1_and_2(self):
        for module in BUILDERS:
            with self.subTest(module):
                self.assertEqual(_literals(module), [])

    def test_every_geometry_exception_names_a_function_that_exists(self):
        for module, function in GEOMETRY:
            tree = ast.parse((STEEL / f"{module}.py").read_text(encoding="utf-8"))
            self.assertIn(function, {name for name, _ in _functions(tree)}, module)

    def test_every_constant_a_builder_names_is_a_registry_row(self):
        named = set()
        for module in ("limits", "checks"):
            text = (STEEL / f"{module}.py").read_text(encoding="utf-8")
            named |= set(re.findall(r'(?:\bk|ctx\.const)\("([a-z0-9_.]+)"\)', text))
        from lola.models.steel import limits as L
        named |= {n for pair in L.BEARING.values() for n in pair} | {L.STRICT, L.STRICT_RATIO}
        self.assertEqual(sorted(n for n in named if n not in REGISTRY.constants), [])

    def test_every_coefficient_row_is_read(self):
        """A coefficient no builder reads is dead (or misspelled where it is read)."""
        text = "".join((STEEL / f"{m}.py").read_text(encoding="utf-8") for m in ("limits", "checks"))
        for name, *_ in deck_rows.COEFFICIENTS:
            with self.subTest(name):
                self.assertTrue(f'"{name}"' in text or name.rsplit(".", 1)[-1].startswith(("bearing_", "tearout_"))
                                or name.startswith("lola.strict"))

    def test_every_row_carries_its_clause_and_tag(self):
        clause = re.compile(r"Section|Eqs?\.|Table|Figure|Part \d|User Note|Symbols list|LoLa's")
        for name, text, unit, tag, owner, source in (*deck_rows.FACTORS, *deck_rows.COEFFICIENTS):
            with self.subTest(name):
                self.assertRegex(source, clause)
                self.assertIn(tag, (deck_rows.SANCTIONED, deck_rows.JUDGED))
                self.assertIn(unit, ("1", "Pa", "m"))
                # a judged value is LoLa's to answer for; a sanctioned one is its issuer's
                self.assertEqual(owner == deck_rows.MAINTAINERS, tag == deck_rows.JUDGED)
                if tag == deck_rows.SANCTIONED and owner == "AISC":
                    self.assertTrue(source.endswith((deck_rows.CHECKED, deck_rows.QUOTED))
                                    or deck_rows.QUOTED in source, "a sanctioned AISC row says where it was checked")

    def test_the_literal_reader(self):
        self.assertTrue(NUMBER.fullmatch("0.6") and NUMBER.fullmatch("5/8") and not NUMBER.fullmatch("J3.8"))


class AiscSymbolsWithAGlossary(unittest.TestCase):
    """D8: every quantity a builder names is in docs/steel_glossary.md."""

    @classmethod
    def setUpClass(cls):
        text = (STEEL.parents[2] / "docs" / "steel_glossary.md").read_text(encoding="utf-8")
        cls.glossed = {name for line in text.splitlines() if line.startswith("| `")
                       for name in re.findall(r"`([a-z_0-9]+)`", line.split("|")[1])}

    def test_every_limits_parameter_is_glossed(self):
        tree = ast.parse((STEEL / "limits.py").read_text(encoding="utf-8"))
        for fn in tree.body:
            if isinstance(fn, ast.FunctionDef):
                for a in fn.args.args:
                    with self.subTest(function=fn.name, parameter=a.arg):
                        self.assertIn(a.arg, self.glossed)

    def test_every_length_field_is_glossed(self):
        from lola.models.steel.lower import _LENGTHS
        self.assertEqual(sorted(set(_LENGTHS) - self.glossed), [])

    def test_the_glossary_reader(self):
        self.assertTrue({"k", "block_cols", "block_rows", "lb_unbraced", "pitch", "free_edge"} <= self.glossed)


if __name__ == "__main__":
    unittest.main()
