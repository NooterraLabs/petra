"""Teaching a stranger the language: the kind grammars the lowerers read, `petra kinds`,
`petra new`, `petra registry list`, common registry names and "did you mean", and the
generated docs/reference.md and petra/templates.py."""
import contextlib
import dataclasses
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from petra import cli, models
from petra.lang import LolaSyntaxError, LoweringError, parse_design
from petra.lang.parser import parse
from petra.models import circuit, truss
from petra.models.base import ComponentError
from petra.models.steel import lower as steel
from petra.pipeline import lower_components
from petra.registry import OutsideMakeableSet, build_registry
from petra.registry.model import fold
from petra import teach
from petra.templates import TEMPLATES

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = build_registry()


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def lowering_errors(text: str) -> str:
    """The input error a design raises while it lowers, or "" when it lowers."""
    try:
        lower_components(parse_design(text, "t.petra", REGISTRY), REGISTRY)
    except (ComponentError, LolaSyntaxError, LoweringError) as exc:
        return "\n".join(exc.problems) if isinstance(exc, ComponentError) else str(exc)
    return ""


def example(kind: str) -> tuple[str, str]:
    """(component name, text) of the kind's canonical example."""
    return TEMPLATES[kind][1], TEMPLATES[kind][2]


def with_line(kind: str, line: str) -> str:
    name, text = example(kind)
    return text.replace(f"{kind} {name} {{\n", f"{kind} {name} {{\n  {line}\n", 1)


class OneGrammarPerKind(unittest.TestCase):
    def test_a_domain_without_a_grammar_for_a_kind_is_refused(self):
        bare = dataclasses.replace(truss.DOMAIN, grammars={})
        with self.assertRaisesRegex(RuntimeError, "grammar"):
            models._index((bare,))

    def test_the_circuit_grammar_is_its_readers_and_connect(self):
        self.assertEqual(set(circuit.GRAMMAR.names), set(circuit._READERS) | {"connect"})

    def test_the_steel_fields_are_its_parsers(self):
        self.assertEqual(set(steel.FIELDS), set(steel._COMMON))
        lines = {n for spec in steel.KIND_SPECS.values() for n in (*spec.required, *spec.optional)}
        self.assertEqual(lines - {"holes"}, set(steel.FIELDS))

    def test_every_kind_names_every_line_when_one_is_unknown(self):
        for kind, spec in models.KINDS.items():
            with self.subTest(kind):
                problems = lowering_errors(with_line(kind, "bogus_line 1"))
                self.assertIn("bogus_line", problems)
                for name in spec.grammars[kind].names:
                    self.assertIn(name, problems)

    def test_a_missing_steel_line_prints_its_form(self):
        name, text = example("shear_tab")
        problems = lowering_errors(re.sub(r"\n  pitch [^\n]*", "", text))
        self.assertIn("a shear_tab needs pitch: `pitch <length>`", problems)

    def test_a_steel_usage_error_prints_its_form(self):
        problems = lowering_errors(example("shear_tab")[1].replace("  rows 4", "  rows four"))
        self.assertIn("reads `rows <n>`", problems)


class CommonNames(unittest.TestCase):
    def test_the_common_names_resolve(self):
        for name, mid in (("A325", "bolt_group.120"), ("a490", "bolt_group.150"), ("F1852", "bolt_group.120"),
                          ("A36", "steel.A36"), ("A992", "steel.A992"), ("A572 Gr 50", "steel.A572_50"),
                          ("A572_Grade_50", "steel.A572_50"), ("A572_50", "steel.A572_50"), ("E70XX", "electrode.E70"),
                          ("steel.A36", "steel.A36"), ("A325N", "A325N")):
            with self.subTest(name):
                self.assertEqual(REGISTRY.canonical(name), mid)

    def test_each_name_is_one_its_standard_gives(self):
        """AISC 360-22 J3.1 puts A325 and F1852 in Group 120 and A490 and F2280 in Group 150;
        the registry's standard text says so, and every other name is its id's last part."""
        for name, mid in REGISTRY.names.items():
            with self.subTest(name):
                standard = fold(REGISTRY.materials[mid].standard)
                self.assertTrue(fold(name) in standard or fold(name) == fold(mid.rpartition(".")[2]))

    def test_a_design_in_common_names_is_the_design_in_ids(self):
        name, text = example("shear_tab")
        aliased = (text.replace("bolts bolt_group.120", "bolts A325").replace("grade steel.A992", "grade A992")
                   .replace("plate steel.A36", 'plate "A36"').replace("weld electrode.E70", "weld E70XX"))
        self.assertNotIn("steel.A36", aliased)
        reports = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, body in enumerate((text, aliased)):
                path = Path(tmp) / f"d{i}.petra"
                path.write_text(body, encoding="utf-8")
                code, out, err = run("check", "--json", str(path))
                self.assertEqual(code, 0, err)
                report = json.loads(out)
                report.pop("file")
                reports.append(report)
        self.assertEqual(reports[0], reports[1])
        labels = {p["label"] for v in reports[1]["verdicts"] for p in v["footprint"]}
        for mid in ("bolt_group.120", "steel.A992", "steel.A36", "electrode.E70"):
            self.assertTrue(any(f"reg:{mid}." in label for label in labels), mid)

    def test_a_quoted_name_with_spaces_resolves(self):
        text = example("shear_tab")[1].replace("beam W18x50 grade steel.A992", 'beam W18x50 grade "A572 Gr 50"')
        conn = lower_components(parse_design(text, "t.petra", REGISTRY), REGISTRY)["st1"]
        self.assertEqual(conn.attrs["beam"].grade, "steel.A572_50")

    def test_the_thread_suffix_is_explained(self):
        for written, group, threads in (("A325N", "bolt_group.120", "included"), ("A325_X", "bolt_group.120", "excluded"),
                                        ("A490X", "bolt_group.150", "excluded")):
            with self.subTest(written):
                problems = lowering_errors(example("shear_tab")[1].replace("bolts bolt_group.120", f"bolts {written}"))
                self.assertIn("-N means threads included", problems)
                self.assertIn(f"`bolts {group} diameter <length> threads {threads}`", problems)

    def test_a_hyphen_in_a_name_says_to_write_an_underscore(self):
        problems = lowering_errors(example("shear_tab")[1].replace("bolts bolt_group.120", "bolts A325-N"))
        self.assertIn("unexpected character '-' after A325", problems)
        self.assertIn("write _", problems)


class DidYouMean(unittest.TestCase):
    def test_a_registry_lookup_names_the_close_ids(self):
        for lookup, expected in ((lambda: REGISTRY.material("steel.A35"), "did you mean steel.A36"),
                                 (lambda: REGISTRY.material("S355"), "did you mean steel.S355"),
                                 (lambda: REGISTRY.process("zinc_plate"), "did you mean process.zinc_plate"),
                                 (lambda: REGISTRY.environment("indoor"), "did you mean indoor_dry"),
                                 (lambda: REGISTRY.material("qqq"), "`petra registry list` prints every id")):
            with self.subTest(expected):
                with self.assertRaises(OutsideMakeableSet) as caught:
                    lookup()
                self.assertIn(expected, str(caught.exception))

    def test_a_part_lookup_suggests_parts_of_its_kind(self):
        from petra.registry import PartKind
        with self.assertRaises(OutsideMakeableSet) as caught:
            REGISTRY.part("mcb.B17", PartKind.BREAKER)
        self.assertRegex(str(caught.exception), r"did you mean mcb\.B\d+")

    def test_a_design_hears_the_close_id(self):
        text = example("shear_tab")[1]
        for wrong, right in (("plate steel.A36", "plate steel.A35"), ("W18x50", "W18x51")):
            with self.subTest(right):
                problems = lowering_errors(text.replace(wrong, right))
                self.assertIn(f"{right.split()[-1]} is not a registry", problems)
                self.assertIn(f"did you mean {wrong.split()[-1]}", problems)
        problems = lowering_errors(example("joint")[1].replace("aluminium.6061_T6 thickness 10 mm\n",
                                                                "aluminium.6061_T6 thickness 10 mm process zinc_plate\n", 1))
        self.assertIn("did you mean process.zinc_plate", problems)


class PetraNew(unittest.TestCase):
    def test_every_kind_prints_a_design_that_checks_without_an_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in models.KINDS:
                for name in (None, "renamed"):
                    with self.subTest(kind=kind, name=name):
                        code, out, err = run("new", kind, *(("--name", name) if name else ()))
                        self.assertEqual(code, 0, err)
                        path = Path(tmp) / f"{kind}.petra"
                        path.write_text(out, encoding="utf-8")
                        code, _, err = run("check", "--no-solve", str(path))
                        self.assertNotIn(code, (cli.EXIT_CODES["INPUT_ERROR"], cli.EXIT_CODES["INTERNAL_ERROR"]), err)
                        components = parse_design(out, str(path), REGISTRY).components
                        self.assertEqual([c.kind for c in components.values()], [kind])
                        if name:
                            self.assertEqual(list(components), [name])

    def test_a_renamed_design_gets_the_examples_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tab.petra"
            path.write_text(run("new", "shear_tab", "--name", "tab7")[1], encoding="utf-8")
            code, out, err = run("check", str(path))
        self.assertEqual(code, cli.EXIT_CODES["PASS"], err)
        self.assertIn("tab7/steel.block_shear", out)

    def test_rename_leaves_strings_comments_and_dotted_parts(self):
        text = 'petra 0\n# st1 here\nshear_tab st1 {\n  x st1.st1 "st1"\n}\n'
        self.assertEqual(teach.rename(text, "st1", "t"), 'petra 0\n# st1 here\nshear_tab t {\n  x t.st1 "st1"\n}\n')

    def test_an_unknown_kind_or_a_bad_name_is_an_input_error(self):
        code, _, err = run("new", "shear_tb")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("did you mean shear_tab", err)
        code, _, err = run("new", "truss", "--name", "x-y")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("is not a name", err)
        code, _, err = run("new", "truss", "--name", "design")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"], "a declaration word is not a component name")


class PetraKinds(unittest.TestCase):
    def test_every_kind_prints_every_line_with_its_form(self):
        code, out, _ = run("kinds")
        self.assertEqual(code, 0)
        for kind, spec in models.KINDS.items():
            with self.subTest(kind):
                self.assertIn(f"\n{kind} <name> {{", out)
                for f in spec.grammars[kind].fields:
                    self.assertIn(f"    {f.name} {f.form}\n        {f.meaning}", out)

    def test_a_domain_or_a_kind_prints_only_its_own(self):
        code, out, _ = run("kinds", "steel")
        self.assertEqual(code, 0)
        self.assertIn("shear_tab <name>", out)
        self.assertNotIn("truss <name>", out)
        code, out, _ = run("kinds", "hanger")
        self.assertIn("hanger <name>", out)
        self.assertNotIn("shear_tab <name>", out)

    def test_the_json_carries_each_field(self):
        code, out, _ = run("kinds", "--json")
        self.assertEqual(code, 0)
        found = {k["kind"]: k for d in json.loads(out)["domains"] for k in d["kinds"]}
        self.assertEqual(set(found), set(models.KINDS))
        for kind, spec in models.KINDS.items():
            grammar = spec.grammars[kind]
            with self.subTest(kind):
                self.assertEqual([(f["name"], f["required"], f["form"], f["unit"], tuple(f["registry"]), f["meaning"])
                                  for f in found[kind]["fields"]],
                                 [(f.name, f in grammar.required, f.form, f.unit, f.registry, f.meaning)
                                  for f in grammar.fields])
                self.assertEqual(found[kind]["load_fields"], list(grammar.loads))

    def test_an_unknown_name_suggests(self):
        code, _, err = run("kinds", "stel")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("did you mean steel", err)


class RegistryList(unittest.TestCase):
    def test_every_id_is_listed_once_with_a_line(self):
        code, out, _ = run("registry", "list")
        self.assertEqual(code, 0)
        ids = [line.split()[0] for line in out.splitlines()]
        self.assertEqual(len(ids), len(set(ids)))
        for table in (REGISTRY.materials, REGISTRY.parts, REGISTRY.processes, REGISTRY.environments):
            self.assertLessEqual(set(table), set(ids))
        self.assertTrue(all(len(line.split(maxsplit=1)) == 2 for line in out.splitlines()))
        for shape in ("W18x50", "WT9x25", "L4x3_1_2x3_8"):
            self.assertIn(shape, ids)

    def test_a_prefix_matches_ids_and_common_names(self):
        code, out, _ = run("registry", "list", "bolt_group")
        self.assertEqual([line.split()[0] for line in out.splitlines()],
                         ["bolt_group.120", "bolt_group.144", "bolt_group.150", "bolt_group.200", "bolt_group.A307"])
        self.assertIn("also A325, F1852", out)
        self.assertIn("`threads included`", out)
        code, out, _ = run("registry", "list", "a490")
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["bolt_group.150"])

    def test_a_prefix_nothing_starts_with_is_an_input_error(self):
        code, _, err = run("registry", "list", "stel")
        self.assertEqual(code, cli.EXIT_CODES["INPUT_ERROR"])
        self.assertIn("did you mean steel.", err)

    def test_every_w_gives_the_tee_steel_reads_back(self):
        for w in ("W18x50", "W10x45", "W6x8_5", "W5x16"):
            with self.subTest(w):
                self.assertEqual(steel.tee_parent(teach.tee_of(w)), w)


class Generated(unittest.TestCase):
    def test_the_templates_are_the_examples(self):
        self.assertEqual(teach.render_templates(), teach.TEMPLATE_MODULE.read_text(encoding="utf-8"),
                         "petra/templates.py is stale: run python -m petra.teach --write")

    def test_the_reference_is_fresh(self):
        self.assertEqual(teach.render_reference(), teach.REFERENCE.read_text(encoding="utf-8"),
                         "docs/reference.md is stale: run python -m petra.teach --write")

    def test_the_reference_examples_parse(self):
        text = "petra 0\n" + "\n".join(example for _, _, example in teach.SNIPPETS) + "\n"
        decls = parse(text, "reference.petra").decls
        self.assertEqual(len(decls), len(teach.SNIPPETS) + 3, "one declaration per example, and four claims")

    def test_the_reference_covers_the_language(self):
        text = teach.REFERENCE.read_text(encoding="utf-8")
        for decl in ("design", "param", "ambient", "load", "tests", "claim", "waive"):
            self.assertIn(f"### {decl}\n", text)
        for kind, spec in models.KINDS.items():
            self.assertIn(f"#### {kind}\n", text)
            for f in spec.grammars[kind].fields:
                self.assertIn(f"| `{f.name}` |", text)
        for mid in (*REGISTRY.materials, *REGISTRY.parts, *REGISTRY.processes, *REGISTRY.environments):
            self.assertIn(f"\n{mid} ", text)
        self.assertIn("`-N` is `threads included`", text)
        self.assertIn("| length | `m`, `mm`", text)

    def test_the_generated_files_have_no_carriage_return(self):
        for path in (teach.TEMPLATE_MODULE, teach.REFERENCE):
            self.assertNotIn(b"\r", path.read_bytes(), path)


if __name__ == "__main__":
    unittest.main()
