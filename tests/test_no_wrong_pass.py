"""No design of the corpus that must not pass gets a pass, by any way into a check (plan
step 1.1a).

corpus/expected.tsv names 186 designs and the verdict each must get. This walks all of them
through every way into a check: `petra check` as text and as JSON, the server's check tool,
`petra.check` and `petra.check_file`. It holds three things:

- A design that must not pass gets no PASS, no PASS_WAIVED and no MARGINAL from any of them.
- A pass is given only where the kernel worked out the cells from a deck of rules: the
  report says `cells_from` is `rules`.
- A design none of whose parts is of a deck's type reads UNKNOWN with exit code 2 and the
  reason that no deck has its kind of part. The kernel is not asked about it, and it has no
  cell to pass or to fail on.

Written against bfd7b89, where `petra.check_file` still gave the Python checker's own PASS
to 22 designs that must not pass, among them 400 kV on a 750 V cable and a 0.1 mm dimple
declared as a through hole, and where no report gave the reason.

Each design is checked once, by `petra check --json`. The other ways in are run on that one
check: `pipeline.check_text`, which every one of them calls, gives them the result it gave the
first. So the walk costs one check of each design, and a way in that reports another status
than the check gave it, or that does not go through `check_text`, shows. A message names a
design by its path and never prints its text.

Skipped when no kernel is built.
"""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

import petra
from petra import mcp, pipeline, verify
from petra.cli import EXIT_CODES, main
from petra.files import read_pair

ROOT = Path(__file__).resolve().parents[1]
PASSES = ("PASS", "PASS_WAIVED")
CODES = {code: name for name, code in EXIT_CODES.items()}
NO_VERDICT = "NO_VERDICT"
NO_DECK = "no deck of rules has a part of kind "


def corpus() -> list[tuple[str, str]]:
    """Each design of corpus/expected.tsv by its path from the root, with the verdict it must get."""
    rows = []
    for line in (ROOT / "corpus" / "expected.tsv").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            path, expect = line.split("\t")[:2]
            rows.append((path, expect))
    return rows


def cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def one_check():
    """Have pipeline.check_text check each pair once and give every later caller that result."""
    real, done = pipeline.check_text, {}

    def once(card, text, path, **more):
        if (card, text, path) not in done:
            try:
                done[card, text, path] = real(card, text, path, **more), None
            except verify.NoVerdict as exc:
                done[card, text, path] = None, exc
        found, refused = done[card, text, path]
        if refused is not None:
            raise refused
        return found

    with mock.patch.object(pipeline, "check_text", once):
        yield


def by_json(path: str) -> tuple[str, dict | None]:
    """`petra check PATH --json`: the status, which the exit code must give too, and the report."""
    code, out, _ = cli("check", path, "--json")
    if code in (EXIT_CODES["INPUT_ERROR"], EXIT_CODES["INTERNAL_ERROR"]):
        assert out == "", f"{path}: exit code {code} with a report on stdout"
        return ("INPUT_ERROR" if code == EXIT_CODES["INPUT_ERROR"] else NO_VERDICT), None
    report = json.loads(out)
    assert EXIT_CODES[report["status"]] == code, f"{path}: exit code {code} with the status {report['status']}"
    return report["status"], report


def by_text(path: str) -> str:
    code, out, _ = cli("check", path)
    if code in (EXIT_CODES["INPUT_ERROR"], EXIT_CODES["INTERNAL_ERROR"]):
        assert out == "", f"{path}: exit code {code} with a report on stdout"
        return "INPUT_ERROR" if code == EXIT_CODES["INPUT_ERROR"] else NO_VERDICT
    first = out.split("\n", 1)[0]
    said = [word.strip(":") for word in first.split() if word.strip(":") in EXIT_CODES]
    assert said[:1] == [CODES[code]], f"{path}: exit code {code} under a first line that says {said}"
    return CODES[code]


def by_server(path: str) -> str:
    reply = mcp._call({"name": "check", "arguments": {"path": path}})
    if reply["isError"]:
        assert "structuredContent" not in reply, f"{path}: an error with a report"
        return NO_VERDICT if reply["content"][0]["text"].startswith("no verdict") else "INPUT_ERROR"
    return reply["structuredContent"]["status"]


def by_api(path: str) -> str:
    try:
        return petra.check(*read_pair(path), path=path)["status"]
    except verify.NoVerdict:
        return NO_VERDICT


def by_check_file(path: str) -> str:
    try:
        return petra.check_file(path).status
    except verify.NoVerdict:
        return NO_VERDICT
    except (*pipeline.INPUT_ERRORS, OSError):
        return "INPUT_ERROR"


WAYS = {"petra check": by_text, "the server": by_server, "petra.check": by_api, "petra.check_file": by_check_file}


@unittest.skipUnless(verify.binary(), "no petra-verify is built here and PETRA_VERIFY names none")
class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Every design through every way in: its statuses by the name of the way, and its report."""
        cls.rows = corpus()
        cls.said: dict[str, dict[str, str]] = {}
        cls.report: dict[str, dict | None] = {}
        with one_check():
            for path, _ in cls.rows:
                full = str(ROOT / path)
                status, cls.report[path] = by_json(full)
                cls.said[path] = {"petra check --json": status, **{name: way(full) for name, way in WAYS.items()}}

    def test_no_design_that_must_not_pass_gets_a_pass_by_any_way_in(self):
        wrong = [f"{path}: {way} gives {status}, and it must be {expect}" for path, expect in self.rows if expect not in ("PASS", "PASS_WAIVED")
                 for way, status in self.said[path].items() if status in PASSES]
        self.assertEqual(wrong, [])

    def test_every_way_in_gives_one_status(self):
        differ = [f"{path}: {self.said[path]}" for path, _ in self.rows if len(set(self.said[path].values())) != 1]
        self.assertEqual(differ, [])

    def test_a_pass_is_given_only_where_the_kernel_worked_out_the_cells_from_a_deck_of_rules(self):
        passed = [path for path, _ in self.rows if self.said[path]["petra check --json"] in PASSES]
        self.assertGreaterEqual(len(passed), 14, "the laps of the corpus that pass")
        for path in passed:
            report = self.report[path]
            self.assertEqual((report["path"], report["kernel"]["cells_from"], report["kernel"]["verdict"]), ("rules", "rules", "PASS"), path)
            self.assertEqual(report["kernel"]["hashes"]["rules"], report["deck"]["hash"], path)

    def test_a_design_of_a_kind_no_deck_has_reads_unknown_with_that_reason(self):
        """There is nothing to hand the kernel for such a design: no deck of rules, and no cells that Python wrote.
        So it is UNKNOWN, and never a FAIL or a PASS."""
        old = [path for path, _ in self.rows if self.report[path] is not None and self.report[path]["kernel"] is None]
        self.assertGreater(len(old), 60, "most of the corpus is of kinds no deck has")
        for path in old:
            report = self.report[path]
            self.assertEqual((report["status"], report["cells"], report["path"]), ("UNKNOWN", [], "none"), path)
            self.assertTrue(report["reason"].startswith(NO_DECK), f"{path}: {report['reason']!r}")
            self.assertTrue(report["kinds"], path)
        code, out, _ = cli("check", str(ROOT / "corpus" / "cases" / "old" / "circuit_pass.petra"))
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (2, "workshop-lighting-radial: UNKNOWN"))
        self.assertTrue(lines[1].startswith("reason     " + NO_DECK), lines[1])
        self.assertEqual([line for line in lines if "PASS" in line], [], "no line of the report says PASS")

    def test_the_corpus_holds_no_design_that_must_not_pass_and_passes(self):
        """The lines of corpus/expected.tsv themselves: none is marked with a wrong PASS."""
        marked = [line.split("\t")[0] for line in (ROOT / "corpus" / "expected.tsv").read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.startswith("#") and {"PASS", "PASS_WAIVED"} & set(line.split("\t")[2:4])]
        self.assertEqual(marked, [])


if __name__ == "__main__":
    unittest.main()
