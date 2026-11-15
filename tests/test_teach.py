"""Teaching a stranger the language: `petra kinds`, `petra new` and `petra docs`, and the generated
docs/reference.md and petra/templates.py. What they print is read from the shipped decks of rules, as
the grid reads them, and from the examples."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from petra import cli, grid, teach, verify
from petra.lang import parse_design
from petra.lang.parser import parse
from petra.templates import TEMPLATES

ROOT = Path(__file__).resolve().parents[1]
KERNEL = unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def help_text(*argv: str) -> str:
    """What `petra ARGV --help` prints; argparse exits 0 after printing it."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            cli.main([*argv, "--help"])
    except SystemExit as exc:
        if exc.code == 0:
            return out.getvalue()
        raise AssertionError(f"petra {' '.join(argv)} --help exited {exc.code}") from None
    raise AssertionError(f"petra {' '.join(argv)} --help did not exit")


class PetraNew(unittest.TestCase):
    def test_every_type_with_an_example_prints_a_card_and_a_design_of_it(self):
        self.assertEqual(sorted(TEMPLATES), sorted(teach.CANONICAL), "a template for each canonical example")
        for kind in TEMPLATES:
            for name in (None, "renamed"):
                with self.subTest(kind=kind, name=name):
                    named = ("--name", name) if name else ()
                    code, out, err = run("new", kind, *named)
                    self.assertEqual(code, 0, err)
                    code, card, err = run("new", kind, *named, "--card")
                    self.assertEqual(code, 0, err)
                    design = parse_design(card, out, f"{kind}.petra")
                    kinds = [c.kind for c in design.components.values()]
                    self.assertEqual(kinds.count(kind), 1)
                    self.assertIsNotNone(grid.owner(design), "every part is of the deck's types")
                    self.assertEqual(design.waivers, (), "the card signs no waiver")
                    if name:
                        self.assertEqual(design.components[name].kind, kind)

    @KERNEL
    def test_a_renamed_design_reads_unknown_until_its_open_lines_are_signed(self):
        """The example passes on the waivers of its own engineer. The card `petra new` prints signs none, so the five
        lines the deck has no rule for are open (tests/test_kernel_attacks12.py, finding Q)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lap.petra"
            path.write_text(run("new", "lap", "--name", "joint7")[1], encoding="utf-8")
            path.with_suffix(".card").write_text(run("new", "lap", "--name", "joint7", "--card")[1], encoding="utf-8")
            code, out, err = run("check", str(path))
        self.assertEqual(code, cli.EXIT_CODES["UNKNOWN"], err)
        self.assertIn("joint7/lap.block_shear", out)
        self.assertIn("5 open", out)

    def test_rename_leaves_strings_comments_and_dotted_parts(self):
        text = 'petra 0\n# st1 here\nlap st1 {\n  x st1.st1 "st1"\n}\n'
        self.assertEqual(teach.rename(text, "st1", "t"), 'petra 0\n# st1 here\nlap t {\n  x t.st1 "st1"\n}\n')

    def test_an_unknown_type_or_a_bad_name_is_an_input_error(self):
        code, _, err = run("new", "lapp")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("did you mean lap", err)
        code, _, err = run("new", "plate")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"], "a plate has no example of its own")
        self.assertIn("written with the part that joins it", err)
        code, _, err = run("new", "lap", "--name", "x-y")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("is not a name", err)
        code, _, err = run("new", "lap", "--name", "load")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"], "a declaration word is not a part's name")

    def test_the_help_names_every_type_with_an_example(self):
        text = " ".join(help_text("new").split())
        self.assertIn("TYPE the type of part: ", text)
        for kind in TEMPLATES:
            self.assertRegex(text, rf"\b{kind}\b")
        self.assertIn("`petra kinds TYPE`", text)


class PetraKinds(unittest.TestCase):
    def test_with_no_argument_it_prints_each_deck_and_its_types_in_a_few_lines(self):
        code, out, _ = run("kinds")
        self.assertEqual(code, 0)
        for deck in grid.decks():
            self.assertIn(f"deck {deck.name}: {', '.join(deck.types)}", out)
        self.assertLess(len(out.splitlines()), 12)
        self.assertIn("`petra new TYPE`", out)

    def test_every_type_prints_every_line_and_every_mechanism(self):
        code, out, err = run("kinds", "--all")
        self.assertEqual(code, 0, err)
        for deck in grid.decks():
            for kind in deck.types.values():
                self.assertIn(f"{kind.name} <name> {{ one line each }}", out)
                for field in kind.fields.values():
                    self.assertRegex(out, rf"\n    {field.name} ")
            for ask in deck.asks:
                self.assertIn(f"    {ask.mechanism}    ", out)

    def test_a_mechanism_says_its_rule_or_that_it_is_open(self):
        _, out, _ = run("kinds", "lap")
        self.assertIn("rule aisc360-22/lap-spacing-centres, aisc360-22/lap-spacing-clear", out)
        self.assertIn("no rule yet, so its cell is open until the card waives it", out)

    def test_all_with_a_name_is_an_input_error(self):
        code, _, err = run("kinds", "lap", "--all")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("--all prints every type", err)

    def test_the_help_names_the_decks_and_types_it_takes(self):
        text = " ".join(help_text("kinds").split())
        for deck in grid.decks():
            self.assertIn(deck.name, text)
            for kind in deck.types:
                self.assertRegex(text, rf"\b{kind}\b")

    def test_a_deck_or_a_type_prints_only_its_own(self):
        _, lap, _ = run("kinds", "lap")
        self.assertIn("lap <name> {", lap)
        self.assertNotIn("plate <name> {", lap)
        _, deck, _ = run("kinds", grid.decks()[0].name)
        self.assertIn("plate <name> {", deck)
        self.assertIn("lap <name> {", deck)

    def test_the_json_carries_each_field_and_each_mechanism(self):
        code, out, _ = run("kinds", "--json")
        self.assertEqual(code, 0)
        found = json.loads(out)
        self.assertEqual([d["deck"] for d in found["decks"]], [d.name for d in grid.decks()])
        deck = grid.decks()[0]
        self.assertEqual(found["decks"][0]["hash"], deck.hash)
        types = {t["type"]: t for t in found["decks"][0]["types"]}
        self.assertEqual(set(types), set(deck.types))
        self.assertEqual([f["name"] for f in types["lap"]["fields"]], list(deck.types["lap"].fields))
        self.assertEqual([a["mechanism"] for a in types["lap"]["asks"]], [a.mechanism for a in deck.asks if a.type == "lap"])
        self.assertTrue(any(a["rules"] for a in types["lap"]["asks"]) and any(not a["rules"] and not a["excused"] for a in types["lap"]["asks"]))
        self.assertEqual(types["lap"]["example"], teach.CANONICAL["lap"])
        (one,) = json.loads(run("kinds", "lap", "--json")[1])["decks"][0]["types"]
        self.assertEqual(one["type"], "lap")

    def test_an_unknown_name_suggests_and_a_kind_no_deck_has_is_unknown(self):
        code, out, err = run("kinds", "lapp")
        self.assertEqual((code, out), (cli.EXIT_CODES["INPUT_ERROR"], ""))
        self.assertIn("did you mean lap", err)
        for old in ("truss", "shear_tab", "steel"):
            self.assertEqual(run("kinds", old)[0], cli.EXIT_CODES["INPUT_ERROR"], old)
            self.assertEqual(run("kinds", old, "--json")[0], cli.EXIT_CODES["INPUT_ERROR"], old)


class PetraDocs(unittest.TestCase):
    """`petra docs` from the source tree; tests/test_packaging.py runs it from an installed
    wheel and an editable install."""

    FILES = {"readme": ROOT / "README.md", "reference": ROOT / "docs" / "reference.md",
             "api": ROOT / "petra" / "docs" / "api.md", "skill": ROOT / "petra" / "docs" / "skill.md"}

    def test_with_no_name_it_lists_each_document_with_what_it_covers(self):
        code, out, _ = run("docs")
        self.assertEqual(code, 0)
        listed = {line.split()[0]: line for line in out.splitlines()[:-1]}
        self.assertEqual(set(listed), set(self.FILES))
        self.assertTrue(all(len(line.split(maxsplit=1)) == 2 for line in listed.values()))
        self.assertIn("`petra docs NAME`", out.splitlines()[-1])

    def test_each_document_prints_whole(self):
        for name, path in self.FILES.items():
            with self.subTest(name):
                code, out, err = run("docs", name)
                self.assertEqual(code, 0, err)
                self.assertEqual(out, path.read_text(encoding="utf-8"))

    def test_every_document_the_package_ships_prints_by_its_name(self):
        shipped = sorted((ROOT / "petra" / "docs").glob("*.md"))
        self.assertTrue(shipped)
        for path in shipped:
            with self.subTest(path.name):
                self.assertEqual(run("docs", path.stem)[1], path.read_text(encoding="utf-8"))

    def test_an_unknown_name_suggests(self):
        code, out, err = run("docs", "referense")
        self.assertEqual((code, out), (cli.EXIT_CODES["INPUT_ERROR"], ""))
        self.assertIn("did you mean reference", err)

    def test_the_help_names_the_documents(self):
        text = " ".join(help_text("docs").split())
        self.assertIn("NAME the document: readme, reference, api", text)

    def test_petra_help_ends_by_naming_petra_docs(self):
        self.assertIn("`petra docs`", help_text().rstrip("\n").splitlines()[-1])


class Generated(unittest.TestCase):
    def test_the_templates_are_the_examples(self):
        self.assertEqual(teach.render_templates(), teach.TEMPLATE_MODULE.read_text(encoding="utf-8"),
                         "petra/templates.py is stale: run python -m petra.teach --write")

    def test_the_reference_is_fresh(self):
        self.assertEqual(teach.render_reference(), teach.REFERENCE.read_text(encoding="utf-8"),
                         "docs/reference.md is stale: run python -m petra.teach --write")

    def test_the_reference_examples_parse(self):
        design = {"param", "component"}
        card = "petra 0\n" + "\n".join(example for decl, _, example in teach.SNIPPETS if decl != "component") + "\n"
        text = "petra 0\n" + "\n".join(example for decl, _, example in teach.SNIPPETS if decl in design) + "\n"
        self.assertEqual(len(parse(card, "reference.card", True).decls), len(teach.SNIPPETS) - 1 + 3,
                         "one declaration per example of the card's, and four claims")
        self.assertEqual(len(parse(text, "reference.petra", False).decls), len(design))

    def test_the_reference_covers_the_language_and_the_decks(self):
        text = teach.REFERENCE.read_text(encoding="utf-8")
        for decl in ("card", "param", "ambient", "given", "component", "load", "tests", "claim", "waive"):
            self.assertIn(f"### {decl}\n", text)
        for deck in grid.decks():
            self.assertIn(f"### Deck {deck.name}\n", text)
            self.assertIn(deck.hash, text)
            for kind in deck.types.values():
                self.assertIn(f"{kind.name} <name> {{ one line each }}", text)
                for field in kind.fields.values():
                    self.assertRegex(text, rf"\n    {field.name} ")
            for ask in deck.asks:
                self.assertIn(f"    {ask.mechanism}    ", text)
        self.assertIn("| length | `m`, `mm`", text)
        for gone in ("registry list", "certify-family", "MARGINAL", "## Registry", "Domain steel"):
            self.assertNotIn(gone, text)

    def test_the_generated_files_have_no_carriage_return(self):
        for path in (teach.TEMPLATE_MODULE, teach.REFERENCE):
            self.assertNotIn(b"\r", path.read_bytes(), path)


if __name__ == "__main__":
    unittest.main()
