"""A toy benchmark for the tests of bench/exam, and a fake model to sit it.

The four tasks are made up here and copied from no benchmark: each asks for a whole number
in a range, and the grader reads the last whole number of the answer. TOY shows the agent
nothing between attempts, as most benchmarks do. TOY_FEEDBACK shows it the number that was
read, which is not the grade.

Run as a command, this file is the fake model: it reads a prompt on stdin and prints a
reply. tests/test_exam.py says what the reply is.

    python tests/exam_toy.py < PROMPT
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.exam.adapters import Adapter, Grade  # noqa: E402

SECRET = "the-grader-said-this"
"""In every grade's detail. No prompt may ever hold it."""
TASKS = {
    "toy-a": ("How many spokes has the made-up wheel A? Any whole number from 4 to 6 is right.", 4, 6),
    "toy-b": ("How many spokes has the made-up wheel B? Any whole number from 9 to 12 is right.", 9, 12),
    "toy-c": ("How many spokes has the made-up wheel C? Any whole number from 20 to 20 is right.", 20, 20),
    "toy-d": ("How many spokes has the made-up wheel D? Any whole number from 31 to 35 is right.", 31, 35),
}
FORM = " Reply with the number alone on the last line."


class Toy(Adapter):
    name = "toy"
    about = "a made-up question in, a whole number out"

    def fetch(self, folder: Path) -> dict:
        folder.mkdir(parents=True, exist_ok=True)
        return {"version": {}, "files": []}

    def tasks(self, folder: Path) -> list[str]:
        return sorted(TASKS)

    def prompt(self, folder: Path, task: str) -> str:
        return TASKS[task][0] + FORM

    def answer(self, reply: str) -> str | None:
        found = re.findall(r"-?\d+", reply)
        return found[-1] if found else None

    def grade(self, folder: Path, task: str, answer: str | None, timeout: float) -> Grade:
        if answer is None:
            return Grade("no_answer", 0.0, {"said": SECRET})
        _, low, high = TASKS[task]
        return Grade("pass" if low <= int(answer) <= high else "wrong", float(low <= int(answer) <= high), {"said": SECRET})


class ToyFeedback(Toy):
    name = "toyfeedback"

    def feedback(self, folder: Path, task: str, answer: str | None, timeout: float) -> str | None:
        return f"Your number was read as {answer}."


TOY = Toy()
TOY_FEEDBACK = ToyFeedback()

DESIGN = (ROOT / "examples" / "deck" / "lap_pass.petra").read_text(encoding="utf-8")
CARD = (ROOT / "examples" / "deck" / "lap_pass.card").read_text(encoding="utf-8")


def fake(prompt: str) -> str:
    """The fake model's reply. On a first attempt it gives the lower end of the range less
    one, which is wrong, and in the petra arm it hands in a design of examples/deck with
    its card. On a retry it gives the lower end, which is right. A prompt with the word
    SILENT in it gets no number, and one with the word BROKEN gets a design Petra refuses."""
    low = int(re.search(r"from (\d+) to", prompt)[1])
    if "SILENT" in prompt:
        return "I would rather not say."
    if "Your previous reply was" in prompt:
        return f"On reflection:\n{low}"
    if "```petra" not in prompt:
        return f"{low - 1}"
    if "NOTHING" in prompt:
        return f"Petra has nothing to say here.\n{low - 1}"
    design = "this is no design\n" if "BROKEN" in prompt else DESIGN
    return f"My answer:\n{low - 1}\n\n```petra\n{design}```\n\n```card\n{CARD}```\n"


if __name__ == "__main__":
    sys.stdout.write(fake(sys.stdin.read()))
