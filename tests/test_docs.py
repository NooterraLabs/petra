"""The docs' worked examples stay true to the shipped files and to what Petra prints.

README.md marks each sample output with `<!-- sample: COMMAND -->` on the line before its
```text block. COMMAND is either `petra ARGS`, optionally piped through `head -n N` or
`sed -n 'A,Bp;Cp'`, which runs as `python -m petra ARGS` from the repository root; or
`python`, which runs the ```python block above the marker from the repository root. A
`petra` sample also follows a ```bash block that shows its command. Rewrite every sample
from its command with

    python tests/test_docs.py --write
"""
import json
import os
import re
import shlex
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parent.parent
DESIGN = (ROOT / "docs" / "design.md").read_text(encoding="utf-8")
README = ROOT / "README.md"

SAMPLE = re.compile(r"^(?P<indent>[ \t]*)<!-- sample: (?P<command>.+?) -->\n(?P=indent)```text\n(?P<body>.*?)^(?P=indent)```$", re.M | re.S)
FENCE = r"^(?P<indent>[ \t]*)```{}\n(?P<code>.*?)^(?P=indent)```$"
PYTHON = re.compile(FENCE.format("python"), re.M | re.S)
BASH = re.compile(FENCE.format("bash"), re.M | re.S)
VERDICT_EXITS = {0, 1, 2, 5}
"""The exit codes of a verdict, as petra.cli.EXIT_CODES gives them; 3 and 4 are errors."""

# A reader has no shapes workbook, so the samples show the shipped rows.
ENV = {k: v for k, v in os.environ.items() if k != "PETRA_SHAPES_XLSX"}


def json_block_after(heading: str) -> object:
    start = DESIGN.index(heading)
    a = DESIGN.index("```json\n", start) + len("```json\n")
    return json.loads(DESIGN[a:DESIGN.index("\n```", a)])


@dataclass(frozen=True)
class Sample:
    """What one README sample runs: the command its marker names and, for `python`, the
    code of the python block above it."""
    command: str
    code: str | None


def unindent(block: str, indent: str) -> str:
    return "".join(line.removeprefix(indent) + "\n" for line in block.splitlines())


def samples(text: str) -> list[tuple[Sample, re.Match]]:
    found = []
    for m in SAMPLE.finditer(text):
        code = None
        if m["command"] == "python":
            above = list(PYTHON.finditer(text, 0, m.start()))
            if not above:
                raise ValueError("a `sample: python` marker needs a ```python block above it")
            code = unindent(above[-1]["code"], above[-1]["indent"])
        found.append((Sample(m["command"], code), m))
    return found


def stages(command: str) -> list[list[str]]:
    """`petra check X | head -n 4` -> [["petra", "check", "X"], ["head", "-n", "4"]]."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|")
    lexer.whitespace_split = True
    out: list[list[str]] = [[]]
    for token in lexer:
        if token == "|":
            out.append([])
        else:
            out[-1].append(token)
    return out


def filtered(stage: list[str], lines: list[str]) -> list[str]:
    match stage:
        case ["head", "-n", n]:
            return lines[:int(n)]
        case ["sed", "-n", script]:
            spans = []
            for command in script.split(";"):
                m = re.fullmatch(r"(\d+)(?:,(\d+))?p", command)
                if m is None:
                    raise ValueError(f"sed command {command!r} is not `Np` or `A,Bp`")
                spans.append((int(m[1]), int(m[2] or m[1])))
            return [line for i, line in enumerate(lines, 1) for a, b in spans if a <= i <= b]
    raise ValueError(f"a README sample pipes only through `head -n N` or `sed -n 'A,Bp'`, not {shlex.join(stage)!r}")


def output(sample: Sample) -> str:
    """The sample's stdout, after its pipe, with trailing spaces stripped from each line."""
    if sample.code is not None:
        argv, rest, allowed = [sys.executable, "-c", sample.code], [], {0}
    else:
        (program, *args), *rest = stages(sample.command)
        if program != "petra":
            raise ValueError(f"a README sample runs `petra` or `python`, not {program!r}")
        argv, allowed = [sys.executable, "-m", "petra", *args], VERDICT_EXITS
    done = subprocess.run(argv, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=600)
    if done.returncode not in allowed:
        raise RuntimeError(f"README sample {sample.command!r} exited {done.returncode}:\n{done.stderr}")
    lines = done.stdout.splitlines()
    for stage in rest:
        lines = filtered(stage, lines)
    return "".join(line.rstrip() + "\n" for line in lines)


def outputs(text: str) -> dict[Sample, str]:
    wanted = list(dict.fromkeys(s for s, _ in samples(text)))
    with ThreadPoolExecutor(max_workers=max(1, len(wanted))) as pool:
        return dict(zip(wanted, pool.map(output, wanted)))


def body(indent: str, out: str) -> str:
    return "".join(f"{indent}{line}\n" if line else "\n" for line in out.splitlines())


def render(text: str, outs: Mapping[Sample, str]) -> str:
    """`text` with every sample block replaced by its command's output."""
    for sample, m in reversed(samples(text)):
        text = text[:m.start("body")] + body(m["indent"], outs[sample]) + text[m.end("body"):]
    return text


class DesignDoc(unittest.TestCase):
    def test_the_certificate_example_is_the_shipped_certificate(self):
        shipped = json.loads((ROOT / "examples" / "bolt_tension.cert.json").read_text(encoding="utf-8"))
        self.assertEqual(json_block_after("## Certificate JSON format"), shipped,
                         "docs/design.md must show examples/bolt_tension.cert.json verbatim")

    def test_a_drifted_certificate_example_is_caught(self):
        shipped = json.loads((ROOT / "examples" / "bolt_tension.cert.json").read_text(encoding="utf-8"))
        drifted = {**shipped, "statement_hash": "sha256:" + "0" * 64}
        self.assertNotEqual(json_block_after("## Certificate JSON format"), drifted)

    def test_every_example_file_the_doc_names_exists(self):
        named = set(re.findall(r"examples/[\w/]+\.(?:petra|json)", DESIGN))
        self.assertTrue(named, "the doc names example files")
        missing = sorted(p for p in named if not (ROOT / p).exists())
        self.assertEqual(missing, [], "docs/design.md names example files that do not exist")


class ReadmeSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = README.read_text(encoding="utf-8")
        cls.outs = outputs(cls.text)

    def test_every_sample_is_its_commands_output(self):
        found = samples(self.text)
        self.assertGreaterEqual(len(found), 5, "README.md marks its sample outputs")
        for sample, m in found:
            with self.subTest(command=sample.command):
                self.assertEqual(m["body"], body(m["indent"], self.outs[sample]),
                                 f"README.md's sample of `{sample.command}` is stale: run python tests/test_docs.py --write")

    def test_a_drifted_sample_is_caught(self):
        _, m = samples(self.text)[0]
        drifted = self.text[:m.start("body")] + m["indent"] + "PASS\n" + self.text[m.start("body"):]
        self.assertNotEqual(render(drifted, self.outs), drifted)
        self.assertEqual(render(drifted, self.outs), render(self.text, self.outs), "rewriting removes the drift")

    def test_each_petra_sample_follows_the_command_it_shows(self):
        for sample, m in samples(self.text):
            if sample.code is None:
                with self.subTest(command=sample.command):
                    shown = list(BASH.finditer(self.text, 0, m.start()))
                    self.assertTrue(shown, f"a bash block shows `{sample.command}`")
                    commands = [shlex.split(line) for line in shown[-1]["code"].splitlines() if line.strip()]
                    self.assertIn(stages(sample.command)[0], commands,
                                  f"the bash block above the sample of `{sample.command}` shows its command")


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        old = README.read_text(encoding="utf-8")
        new = render(old, outputs(old))
        README.write_text(new, encoding="utf-8", newline="\n")
        print("README.md samples were current" if new == old else "rewrote README.md samples")
    else:
        unittest.main()
